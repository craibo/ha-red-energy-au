"""Tests for backdated hourly statistics from interval usage (issue #64)."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch

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
    aggregate_hourly,
    build_statistics,
    complete_days,
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
