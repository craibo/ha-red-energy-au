"""Tests for backdated hourly statistics from interval usage (issue #64)."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch

import logging

import pytest

from custom_components.red_energy import statistics as red_statistics
from custom_components.red_energy.api import RedEnergyAPI
from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.data_validation import validate_usage_entry
from custom_components.red_energy.statistics import (
    STAT_CONSUMPTION,
    STAT_COST,
    STAT_CREDIT,
    STAT_GENERATION,
    MISSING_DAY_GRACE_DAYS,
    aggregate_hourly,
    build_statistics,
    complete_days,
    day_is_complete,
    fetch_start_date,
    statistic_id,
)

UTC = timezone.utc
TODAY = date(2026, 7, 10)


def _raw_day(usage_date, offset="+10:00", kwh=0.5, gen=0.0, dollar=0.1, gen_dollar=0.0, start_hour=0):
    """Build a raw /usage/interval day: 48 half-hours from local midnight at `offset`."""
    sign = 1 if offset[0] == "+" else -1
    hours, minutes = (int(p) for p in offset[1:].split(":"))
    tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
    midnight = datetime.combine(usage_date, datetime.min.time(), tzinfo=tz) + timedelta(hours=start_hour)
    half_hours = []
    for i in range(48):
        interval = {
            "intervalStart": (midnight + timedelta(minutes=30 * i)).isoformat(),
            "primaryConsumptionTariffComponent": "OFFPEAK",
            "consumptionKwh": kwh(i) if callable(kwh) else kwh,
            "generationKwh": gen,
        }
        if dollar is not None:
            interval["consumptionDollar"] = dollar
        if gen_dollar is not None:
            interval["generationDollar"] = gen_dollar
        half_hours.append(interval)
    return {"usageDate": usage_date.isoformat(), "halfHours": half_hours}


def _sydney_day(usage_date):
    """Build a raw day whose half-hours are in Australia/Sydney local time (DST-aware)."""
    sydney = ZoneInfo("Australia/Sydney")
    start = datetime.combine(usage_date, datetime.min.time(), tzinfo=sydney).astimezone(UTC)
    end = datetime.combine(usage_date + timedelta(days=1), datetime.min.time(), tzinfo=sydney).astimezone(UTC)
    half_hours = []
    while start < end:
        half_hours.append({
            "intervalStart": start.astimezone(sydney).isoformat(),
            "consumptionKwh": 0.5,
            "generationKwh": 0.0,
            "consumptionDollar": 0.1,
            "generationDollar": 0.0,
        })
        start += timedelta(minutes=30)
    return {"usageDate": usage_date.isoformat(), "halfHours": half_hours}


def _entry(raw_day):
    """Run a raw day through the real API normalizer and validator."""
    api = RedEnergyAPI(MagicMock())
    return validate_usage_entry(api._normalize_usage_entry(raw_day))


def _days(*dates, **kwargs):
    return [_entry(_raw_day(d, **kwargs)) for d in dates]


def _no_stats():
    return {key: None for key in (STAT_CONSUMPTION, STAT_COST, STAT_GENERATION, STAT_CREDIT)}


def _end_of(usage_date):
    """The last hour (UTC) of a +10:00 usage day: 23:00 AEST is 13:00 UTC."""
    return datetime.combine(usage_date, datetime.min.time(), tzinfo=UTC) + timedelta(hours=13)


def _dates(days):
    return [e["date"] for e in days]


class TestAggregation:
    def test_two_half_hours_sum_into_one_utc_hour(self):
        entries = _days(date(2026, 7, 8), kwh=lambda i: i / 10)
        hourly = aggregate_hourly(entries, STAT_CONSUMPTION)

        assert len(hourly) == 24
        # 2026-07-08 00:00+10:00 is 2026-07-07 14:00 UTC: intervals 0 and 1
        first = datetime(2026, 7, 7, 14, tzinfo=UTC)
        assert hourly[first] == pytest.approx(0.0 + 0.1)
        assert hourly[first + timedelta(hours=23)] == pytest.approx(4.6 + 4.7)
        assert sum(hourly.values()) == pytest.approx(sum(i / 10 for i in range(48)))

    def test_cost_is_gst_inclusive(self):
        hourly = aggregate_hourly(_days(date(2026, 7, 8), dollar=0.1), STAT_COST)
        assert hourly[datetime(2026, 7, 7, 14, tzinfo=UTC)] == pytest.approx(0.2 * 1.10)

    def test_cost_prefers_incl_gst_field(self):
        raw = _raw_day(date(2026, 7, 8), dollar=0.1)
        for interval in raw["halfHours"]:
            interval["consumptionDollarIncGst"] = 0.12
        hourly = aggregate_hourly([_entry(raw)], STAT_COST)
        assert hourly[datetime(2026, 7, 7, 14, tzinfo=UTC)] == pytest.approx(0.24)

    def test_credit_is_positive(self):
        hourly = aggregate_hourly(_days(date(2026, 7, 8), gen=1.0, gen_dollar=-0.05), STAT_CREDIT)
        assert hourly[datetime(2026, 7, 7, 14, tzinfo=UTC)] == pytest.approx(0.10)

    def test_missing_interval_pricing_produces_no_cost(self):
        entries = _days(date(2026, 7, 8), dollar=None)
        assert aggregate_hourly(entries, STAT_COST) == {}
        assert len(aggregate_hourly(entries, STAT_CONSUMPTION)) == 24


class TestTimezones:
    def test_aedt_offset_lands_on_correct_utc_hours(self):
        """Intervals reported in daylight time (+11:00) map to the right UTC hour."""
        hourly = aggregate_hourly(_days(date(2026, 1, 15), offset="+11:00"), STAT_CONSUMPTION)
        assert min(hourly) == datetime(2026, 1, 14, 13, tzinfo=UTC)
        assert max(hourly) == datetime(2026, 1, 15, 12, tzinfo=UTC)
        assert all(v == pytest.approx(1.0) for v in hourly.values())

    def test_half_hour_offset_buckets_by_utc_hour(self):
        """South Australian offsets (+09:30) still produce whole UTC hours."""
        hourly = aggregate_hourly(_days(date(2026, 7, 8), offset="+09:30"), STAT_CONSUMPTION)
        # 00:00+09:30 is 14:30 UTC, so the first and last UTC hours get one half-hour each
        assert len(hourly) == 25
        assert hourly[datetime(2026, 7, 7, 14, tzinfo=UTC)] == pytest.approx(0.5)
        assert hourly[datetime(2026, 7, 8, 14, tzinfo=UTC)] == pytest.approx(0.5)
        assert sum(hourly.values()) == pytest.approx(24.0)

    @pytest.mark.parametrize(
        ("usage_date", "interval_count"),
        [(date(2026, 10, 4), 46), (date(2026, 4, 5), 50)],
        ids=["aedt-starts", "aedt-ends"],
    )
    def test_sydney_dst_day_is_complete_and_tiles_utc(self, usage_date, interval_count):
        """A day reported in Australia/Sydney local time across a DST change.

        The short (46) and long (50) days must still count as complete, and
        together with their neighbours cover every UTC hour exactly once.
        """
        days = [usage_date - timedelta(days=1), usage_date, usage_date + timedelta(days=1)]
        entries = [_entry(_sydney_day(d)) for d in days]
        assert len(entries[1]["intervals"]) == interval_count
        assert len(complete_days(entries, date(2026, 12, 1))) == 3

        hourly = aggregate_hourly(entries, STAT_CONSUMPTION)
        hours = sorted(hourly)
        assert all(b - a == timedelta(hours=1) for a, b in zip(hours, hours[1:]))
        assert all(v == pytest.approx(1.0) for v in hourly.values())
        assert sum(hourly.values()) == pytest.approx(0.5 * (48 + interval_count + 48))

    def test_offsetless_interval_start_is_nem_time(self):
        raw = _raw_day(date(2026, 7, 8))
        for interval in raw["halfHours"]:
            interval["intervalStart"] = interval["intervalStart"][:-6]
        hourly = aggregate_hourly([_entry(raw)], STAT_CONSUMPTION)
        assert min(hourly) == datetime(2026, 7, 7, 14, tzinfo=UTC)

    def test_nem_today_uses_aest(self):
        # 2026-07-09 14:30 UTC is 2026-07-10 00:30 AEST
        assert red_statistics.nem_today(datetime(2026, 7, 9, 14, 30, tzinfo=UTC)) == date(2026, 7, 10)


class TestCompleteDays:
    def test_excludes_today_and_sorts(self):
        entries = _days(date(2026, 7, 10), date(2026, 7, 8), date(2026, 7, 9))
        assert [e["date"] for e in complete_days(entries, TODAY)] == ["2026-07-08", "2026-07-09"]

    def test_partial_day_of_47_is_incomplete(self):
        entries = _days(date(2026, 7, 8))
        entries[0]["intervals"] = entries[0]["intervals"][:47]
        assert complete_days(entries, TODAY) == []

    def test_stops_at_first_incomplete_day(self):
        entries = _days(date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9))
        entries[1]["intervals"] = entries[1]["intervals"][:20]
        assert [e["date"] for e in complete_days(entries, TODAY)] == ["2026-07-07"]


class TestDayIsComplete:
    """A day is complete only with every half-hour exactly once, covering usageDate."""

    def test_full_nem_day(self):
        assert day_is_complete(_days(date(2026, 7, 8))[0])

    @pytest.mark.parametrize("extra", [1, 2], ids=["49-intervals", "50-intervals"])
    def test_duplicate_interval(self, extra):
        """A repeated half-hour is rejected, even when the count lands on 50."""
        raw = _raw_day(date(2026, 7, 8))
        raw["halfHours"] += [dict(raw["halfHours"][10]) for _ in range(extra)]
        entry = _entry(raw)
        assert len(entry["intervals"]) == 48 + extra
        assert not day_is_complete(entry)

    def test_missing_half_hour_replaced_by_duplicate(self):
        """Count is still 48, but 05:00 is missing and 04:30 appears twice."""
        raw = _raw_day(date(2026, 7, 8))
        raw["halfHours"][10] = dict(raw["halfHours"][9])
        entry = _entry(raw)
        assert len(entry["intervals"]) == 48
        assert not day_is_complete(entry)

    def test_gap_inside_day(self):
        """48 unique intervals, but one is off the half-hour grid, leaving a gap."""
        raw = _raw_day(date(2026, 7, 8))
        raw["halfHours"][20]["intervalStart"] = "2026-07-08T10:15:00+10:00"
        assert not day_is_complete(_entry(raw))

    def test_day_not_starting_at_midnight(self):
        """48 contiguous half-hours shifted by an hour don't cover the usageDate."""
        assert not day_is_complete(_days(date(2026, 7, 8), start_hour=1)[0])

    def test_intervals_for_another_date(self):
        raw = _raw_day(date(2026, 7, 7))
        raw["usageDate"] = "2026-07-08"
        assert not day_is_complete(_entry(raw))

    def test_unordered_intervals_are_fine(self):
        raw = _raw_day(date(2026, 7, 8))
        raw["halfHours"].reverse()
        assert day_is_complete(_entry(raw))

    def test_offsetless_nem_day(self):
        raw = _raw_day(date(2026, 7, 8))
        for interval in raw["halfHours"]:
            interval["intervalStart"] = interval["intervalStart"][:-6]
        assert day_is_complete(_entry(raw))

    @pytest.mark.parametrize(
        ("usage_date", "interval_count"),
        [(date(2026, 10, 4), 46), (date(2026, 4, 5), 50)],
        ids=["aedt-starts", "aedt-ends"],
    )
    def test_dst_local_time_day_accepted_when_contiguous(self, usage_date, interval_count):
        """Local-time DST days: 46/50 half-hours, different offsets at each end."""
        entry = _entry(_sydney_day(usage_date))
        assert len(entry["intervals"]) == interval_count
        assert day_is_complete(entry)

    def test_dst_long_day_with_duplicate_rejected(self):
        """50 intervals on the long day, but one repeated instead of the extra hour."""
        raw = _sydney_day(date(2026, 4, 5))
        raw["halfHours"][30] = dict(raw["halfHours"][29])
        assert not day_is_complete(_entry(raw))


class TestConsecutiveDays:
    """Days after the last imported hour must be consecutive (missing days)."""

    def test_first_run_starts_at_earliest_complete_day(self):
        entries = _days(date(2026, 7, 5), date(2026, 7, 6), date(2026, 7, 7))
        entries[0]["intervals"] = entries[0]["intervals"][:30]  # edge of Red's window
        assert _dates(complete_days(entries, TODAY)) == ["2026-07-06", "2026-07-07"]

    def test_missing_recent_day_stops_import(self):
        """8 Jul missing: 9 Jul must not be imported past it."""
        entries = _days(date(2026, 7, 7), date(2026, 7, 9))
        assert _dates(complete_days(entries, TODAY, date(2026, 7, 7))) == ["2026-07-07"]

    def test_missing_day_imported_once_it_appears(self):
        entries = _days(date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9))
        assert _dates(complete_days(entries, TODAY, date(2026, 7, 8))) == ["2026-07-07", "2026-07-08", "2026-07-09"]

    def test_next_day_absent_stops_import(self):
        """The cursor's next day isn't in the data at all: nothing new."""
        entries = _days(date(2026, 7, 6), date(2026, 7, 9))
        assert _dates(complete_days(entries, TODAY, date(2026, 7, 7))) == ["2026-07-06"]

    def test_old_incomplete_day_does_not_hold_up_new_days(self):
        """A day before the cursor that is incomplete doesn't block later days."""
        entries = _days(date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 9))
        entries[0]["intervals"] = entries[0]["intervals"][:30]
        assert _dates(complete_days(entries, TODAY, date(2026, 7, 9))) == ["2026-07-08", "2026-07-09"]

    def test_missing_day_skipped_with_warning_after_grace(self, caplog):
        today = date(2026, 7, 20)
        missing = today - timedelta(days=MISSING_DAY_GRACE_DAYS)
        entries = _days(missing - timedelta(days=1), missing + timedelta(days=1))
        with caplog.at_level(logging.WARNING, logger=red_statistics.__name__):
            days = complete_days(entries, today, missing, consumer_number="1000001")
        assert _dates(days) == [(missing - timedelta(days=1)).isoformat(), (missing + timedelta(days=1)).isoformat()]
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "1000001" in warnings[0] and missing.isoformat() in warnings[0]

    def test_missing_day_waited_for_inside_grace(self, caplog):
        today = date(2026, 7, 20)
        missing = today - timedelta(days=MISSING_DAY_GRACE_DAYS - 1)
        entries = _days(missing + timedelta(days=1))
        with caplog.at_level(logging.WARNING, logger=red_statistics.__name__):
            assert complete_days(entries, today, missing, consumer_number="1000001") == []
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_old_incomplete_day_skipped_after_grace(self):
        today = date(2026, 7, 20)
        entries = _days(date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3))
        entries[1]["intervals"] = entries[1]["intervals"][:47]
        assert _dates(complete_days(entries, today, date(2026, 7, 1))) == ["2026-07-01", "2026-07-03"]

    def test_several_missing_days_reported_as_one_range(self, caplog):
        entries = _days(date(2026, 7, 1), date(2026, 7, 5))
        with caplog.at_level(logging.WARNING, logger=red_statistics.__name__):
            days = complete_days(entries, date(2026, 7, 20), date(2026, 7, 2), consumer_number="1000001")
        assert _dates(days) == ["2026-07-01", "2026-07-05"]
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and "2026-07-02 to 2026-07-04 (3 days)" in warnings[0]

    def test_no_skip_or_warning_without_a_later_day(self, caplog):
        entries = _days(date(2026, 7, 1))
        with caplog.at_level(logging.WARNING, logger=red_statistics.__name__):
            assert _dates(complete_days(entries, date(2026, 7, 20), date(2026, 7, 2))) == ["2026-07-01"]
        assert not caplog.records

    def test_never_skips_when_skip_missing_is_false(self):
        entries = _days(date(2026, 7, 1), date(2026, 7, 3))
        days = complete_days(entries, date(2026, 7, 20), date(2026, 7, 2), skip_missing=False)
        assert _dates(days) == ["2026-07-01"]


class FakeRecorder:
    """Stands in for the recorder: stores imported rows, optionally losing a write."""

    def __init__(self):
        self.rows = {}
        self.lose_writes = False

    def add(self, hass, metadata, rows):
        if not self.lose_writes:
            self.rows.setdefault(metadata["statistic_id"], []).extend(rows)

    def last(self):
        result = {}
        for key in (STAT_CONSUMPTION, STAT_COST, STAT_GENERATION, STAT_CREDIT):
            rows = self.rows.get(statistic_id("1000001", key))
            result[key] = (rows[-1]["start"], rows[-1]["sum"]) if rows else None
        return result

    async def poll(self, entries, today=TODAY):
        with patch(
            "homeassistant.components.recorder.statistics.async_add_external_statistics", side_effect=self.add
        ):
            return await red_statistics.async_import_statistics(MagicMock(), "1000001", entries, self.last(), today)


class TestPollSequences:
    """Several polls against a fake recorder, as the coordinator runs them."""

    @pytest.mark.asyncio
    async def test_lost_write_is_reimported_with_continuous_sum(self):
        recorder = FakeRecorder()
        day1 = _days(date(2026, 7, 7), kwh=0.25)
        both = day1 + _days(date(2026, 7, 8), kwh=0.75)

        await recorder.poll(day1, today=date(2026, 7, 8))
        recorder.lose_writes = True  # e.g. HA stopped before the recorder committed
        assert await recorder.poll(both, today=date(2026, 7, 9)) == {STAT_CONSUMPTION: 24, STAT_COST: 24}
        recorder.lose_writes = False
        assert await recorder.poll(both, today=date(2026, 7, 9)) == {STAT_CONSUMPTION: 24, STAT_COST: 24}
        # Re-polling once more adds nothing
        assert await recorder.poll(both, today=date(2026, 7, 9)) == {}

        rows = recorder.rows[statistic_id("1000001", STAT_CONSUMPTION)]
        starts = [r["start"] for r in rows]
        assert len(rows) == 48 and len(set(starts)) == 48
        assert all(b - a == timedelta(hours=1) for a, b in zip(starts, starts[1:]))
        assert rows[23]["sum"] == pytest.approx(12.0)
        assert rows[24]["sum"] == pytest.approx(12.0 + 1.5)
        assert rows[-1]["sum"] == pytest.approx(12.0 + 36.0)

    @pytest.mark.asyncio
    async def test_missing_day_stops_then_imports_when_it_appears(self):
        recorder = FakeRecorder()
        await recorder.poll(_days(date(2026, 7, 6)))
        assert recorder.last()[STAT_CONSUMPTION][0] == _end_of(date(2026, 7, 6))

        # Red omits 7 Jul: 8 Jul must not move the cursor past it
        assert await recorder.poll(_days(date(2026, 7, 6), date(2026, 7, 8))) == {}
        assert recorder.last()[STAT_CONSUMPTION][0] == _end_of(date(2026, 7, 6))

        # 7 Jul arrives: both days import, contiguous, nothing lost
        await recorder.poll(_days(date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8)))
        rows = recorder.rows[statistic_id("1000001", STAT_CONSUMPTION)]
        assert len(rows) == 72
        assert rows[-1]["start"] == _end_of(date(2026, 7, 8))
        assert rows[-1]["sum"] == pytest.approx(72.0)

    @pytest.mark.asyncio
    async def test_missing_day_skipped_after_grace(self, caplog):
        recorder = FakeRecorder()
        await recorder.poll(_days(date(2026, 7, 1)), today=date(2026, 7, 2))
        entries = _days(date(2026, 7, 1), date(2026, 7, 3))

        assert await recorder.poll(entries, today=date(2026, 7, 4)) == {}
        with caplog.at_level(logging.WARNING, logger=red_statistics.__name__):
            imported = await recorder.poll(entries, today=date(2026, 7, 2) + timedelta(days=MISSING_DAY_GRACE_DAYS))
        assert imported == {STAT_CONSUMPTION: 24, STAT_COST: 24}
        assert any("2026-07-02" in r.getMessage() for r in caplog.records)
        rows = recorder.rows[statistic_id("1000001", STAT_CONSUMPTION)]
        assert rows[24]["start"] == _end_of(date(2026, 7, 2)) + timedelta(hours=1)  # gap is a gap
        assert rows[24]["sum"] == pytest.approx(24.0 + 1.0)

    @pytest.mark.asyncio
    async def test_first_run_starts_at_earliest_complete_day(self):
        recorder = FakeRecorder()
        entries = _days(date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8))
        entries[0]["intervals"] = entries[0]["intervals"][1:]
        await recorder.poll(entries)
        rows = recorder.rows[statistic_id("1000001", STAT_CONSUMPTION)]
        assert rows[0]["start"] == datetime(2026, 7, 6, 14, tzinfo=UTC)  # 00:00 AEST 7 Jul
        assert len(rows) == 48


class TestBuildStatistics:
    def test_running_sum_from_zero(self):
        hourly = {datetime(2026, 7, 7, 14, tzinfo=UTC): 1.0, datetime(2026, 7, 7, 15, tzinfo=UTC): 2.0}
        rows = build_statistics(hourly, None, 0.0)
        assert [r["sum"] for r in rows] == [1.0, 3.0]
        assert [r["state"] for r in rows] == [1.0, 2.0]

    def test_reimport_is_idempotent(self):
        """Hours already in the recorder are skipped on a re-poll."""
        hourly = aggregate_hourly(_days(date(2026, 7, 8)), STAT_CONSUMPTION)
        first = build_statistics(hourly, None, 0.0)
        last = first[-1]
        assert build_statistics(hourly, last["start"], last["sum"]) == []

    def test_sum_continues_across_polls(self):
        """A second poll with a new day continues the first poll's sum exactly."""
        day1 = _days(date(2026, 7, 8), kwh=0.25)
        both = day1 + _days(date(2026, 7, 9), kwh=0.75)

        first = build_statistics(aggregate_hourly(day1, STAT_CONSUMPTION), None, 0.0)
        last = first[-1]
        second = build_statistics(aggregate_hourly(both, STAT_CONSUMPTION), last["start"], last["sum"])

        assert len(first) == 24 and len(second) == 24
        assert second[0]["start"] == last["start"] + timedelta(hours=1)
        assert second[0]["sum"] == pytest.approx(12.0 + 1.5)
        assert second[-1]["sum"] == pytest.approx(12.0 + 36.0)

        # Same result as importing both days in one go
        single = build_statistics(aggregate_hourly(both, STAT_CONSUMPTION), None, 0.0)
        assert single[-1]["sum"] == pytest.approx(second[-1]["sum"])


class TestFetchStartDate:
    def test_backfills_when_no_consumption_statistics(self):
        last = {key: None for key in (STAT_CONSUMPTION, STAT_COST, STAT_GENERATION, STAT_CREDIT)}
        assert fetch_start_date(last, TODAY, 90) == TODAY - timedelta(days=90)

    def test_resumes_after_oldest_existing_series(self):
        last = {
            STAT_CONSUMPTION: (datetime(2026, 7, 8, 13, tzinfo=UTC), 10.0),  # 23:00 AEST 8 Jul
            STAT_COST: (datetime(2026, 7, 6, 13, tzinfo=UTC), 5.0),
            STAT_GENERATION: None,  # no solar: must not force a backfill
            STAT_CREDIT: None,
        }
        assert fetch_start_date(last, TODAY, 90) == date(2026, 7, 7)

    def test_clamped_to_backfill_window(self):
        last = {STAT_CONSUMPTION: (datetime(2025, 1, 1, tzinfo=UTC), 1.0)}
        assert fetch_start_date(last, TODAY, 90) == TODAY - timedelta(days=90)


class TestAsyncImport:
    @pytest.mark.asyncio
    async def test_imports_external_statistics_with_metadata(self):
        entries = _days(date(2026, 7, 8), date(2026, 7, 9))
        last = {key: None for key in (STAT_CONSUMPTION, STAT_COST, STAT_GENERATION, STAT_CREDIT)}
        with patch(
            "homeassistant.components.recorder.statistics.async_add_external_statistics"
        ) as add:
            imported = await red_statistics.async_import_statistics(MagicMock(), "1000001", entries, last, TODAY)

        # No solar export: generation/credit series aren't created
        assert imported == {STAT_CONSUMPTION: 48, STAT_COST: 48}
        metadata, rows = add.call_args_list[0].args[1:]
        assert metadata["statistic_id"] == "red_energy:1000001_consumption"
        assert metadata["source"] == "red_energy"
        assert metadata["unit_of_measurement"] == "kWh"
        assert metadata["unit_class"] == "energy"
        assert metadata["has_sum"] is True
        assert rows[-1]["sum"] == pytest.approx(48.0)
        assert add.call_args_list[1].args[1]["unit_of_measurement"] == "AUD"

    @pytest.mark.asyncio
    async def test_existing_statistics_continue(self):
        entries = _days(date(2026, 7, 8), date(2026, 7, 9), gen=0.1, gen_dollar=-0.01)
        last_start = datetime(2026, 7, 8, 13, tzinfo=UTC)  # end of 8 Jul AEST
        last = {
            STAT_CONSUMPTION: (last_start, 100.0),
            STAT_COST: (last_start, 50.0),
            STAT_GENERATION: (last_start, 2.0),
            STAT_CREDIT: (last_start, 1.0),
        }
        with patch(
            "homeassistant.components.recorder.statistics.async_add_external_statistics"
        ) as add:
            imported = await red_statistics.async_import_statistics(MagicMock(), "1000001", entries, last, TODAY)

        assert imported == {key: 24 for key in last}
        consumption_rows = add.call_args_list[0].args[2]
        assert consumption_rows[0]["start"] == last_start + timedelta(hours=1)
        assert consumption_rows[-1]["sum"] == pytest.approx(124.0)

    @pytest.mark.asyncio
    async def test_rows_pass_recorder_validation(self):
        """Run HA's own async_add_external_statistics checks (id, source, unit_class, hour alignment)."""
        entries = _days(date(2026, 7, 8), offset="+09:30", gen=0.1, gen_dollar=-0.01)
        last = {key: None for key in (STAT_CONSUMPTION, STAT_COST, STAT_GENERATION, STAT_CREDIT)}
        instance = MagicMock()
        with patch("homeassistant.components.recorder.statistics.get_instance", return_value=instance):
            await red_statistics.async_import_statistics(MagicMock(), "1000001", entries, last, TODAY)
        assert instance.async_import_statistics.call_count == 4

    def test_statistic_id_is_valid(self):
        from homeassistant.core import valid_entity_id
        sid = statistic_id("1000001", STAT_CONSUMPTION)
        assert sid == "red_energy:1000001_consumption"
        assert valid_entity_id(sid.replace(":", "."))


@pytest.fixture
def coordinator():
    hass = MagicMock()
    hass.config.components = {"recorder"}
    with patch(
        "custom_components.red_energy.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        coordinator = RedEnergyDataCoordinator(
            hass=hass,
            username="test_user",
            password="test_pass",
            selected_accounts=["1000001"],
            services=["electricity"],
        )
    coordinator.api = AsyncMock()
    return coordinator


def _usage_data(start_date):
    return {
        "1000001": {
            "property": {},
            "services": {
                "electricity": {
                    "consumer_number": "1000001",
                    "usage_data": {"usage_data": []},
                    "start_date": start_date.isoformat(),
                },
            },
        },
    }


class TestCoordinatorImport:
    @pytest.mark.asyncio
    async def test_first_run_fetches_backfill_window(self, coordinator):
        coordinator.api.get_usage_data = AsyncMock(return_value={"consumer_number": "1000001", "usage_data": []})
        no_stats = {key: None for key in (STAT_CONSUMPTION, STAT_COST, STAT_GENERATION, STAT_CREDIT)}
        with patch.object(red_statistics, "nem_today", return_value=TODAY), patch.object(
            red_statistics, "async_get_last_statistics", AsyncMock(return_value=no_stats)
        ), patch.object(red_statistics, "async_import_statistics", AsyncMock(return_value={})) as do_import:
            await coordinator._async_import_statistics(_usage_data(datetime(2026, 7, 1)))

        from_date, to_date = coordinator.api.get_usage_data.call_args.args[1:]
        assert from_date.date() == TODAY - timedelta(days=90)
        assert to_date.date() == date(2026, 6, 30)
        do_import.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_backfill_fetch_never_skips_days(self, coordinator):
        """Days absent only because the extra fetch failed aren't given up on."""
        coordinator.api.get_usage_data = AsyncMock(return_value={"error": "boom"})
        last = {STAT_CONSUMPTION: (datetime(2026, 6, 1, 13, tzinfo=UTC), 1.0)}
        with patch.object(red_statistics, "nem_today", return_value=TODAY), patch.object(
            red_statistics, "async_get_last_statistics", AsyncMock(return_value=last)
        ), patch.object(red_statistics, "async_import_statistics", AsyncMock(return_value={})) as do_import:
            await coordinator._async_import_statistics(_usage_data(datetime(2026, 7, 1)))

        assert do_import.await_args.args[-1] is False

    @pytest.mark.asyncio
    async def test_no_extra_fetch_when_billing_period_covers_it(self, coordinator):
        last = {STAT_CONSUMPTION: (datetime(2026, 7, 8, 13, tzinfo=UTC), 1.0)}
        with patch.object(red_statistics, "nem_today", return_value=TODAY), patch.object(
            red_statistics, "async_get_last_statistics", AsyncMock(return_value=last)
        ), patch.object(red_statistics, "async_import_statistics", AsyncMock(return_value={})):
            await coordinator._async_import_statistics(_usage_data(datetime(2026, 7, 1)))

        coordinator.api.get_usage_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_never_raises(self, coordinator):
        with patch.object(
            red_statistics, "async_get_last_statistics", AsyncMock(side_effect=RuntimeError("db"))
        ):
            await coordinator._async_import_statistics(_usage_data(datetime(2026, 7, 1)))

    @pytest.mark.asyncio
    async def test_skipped_without_recorder(self, coordinator):
        coordinator.hass.config.components = set()
        with patch.object(red_statistics, "async_get_last_statistics", AsyncMock()) as get_last:
            await coordinator._async_import_statistics(_usage_data(datetime(2026, 7, 1)))
        get_last.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_when_option_disabled(self, coordinator):
        coordinator.config_entry = MagicMock(options={"import_statistics": False})
        with patch.object(red_statistics, "async_get_last_statistics", AsyncMock()) as get_last:
            await coordinator._async_import_statistics(_usage_data(datetime(2026, 7, 1)))
        get_last.assert_not_called()
