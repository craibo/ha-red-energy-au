"""Backdated hourly long-term statistics from Red Energy interval data (issue #64).

Red Energy publishes usage roughly a day late, so the daily sensors' states
are recorded at poll time, not when the energy was used. This module imports
each half-hour interval into Home Assistant's long-term statistics at its own
intervalStart instead, as external statistics (``red_energy:<consumer>_<kind>``)
that the Energy Dashboard can use directly.

Long-term statistics are hourly, so the two half-hours in each UTC hour are
summed. Hours are bucketed in UTC, which keeps this correct for any offset
Red Energy reports (+10:00 NEM time, +11:00 daylight time, +09:30/+10:30 for
South Australia).

Each import continues from the last statistic already in the recorder:
half-hours already in it are skipped and the running ``sum`` carries on from
its sum, so re-polling the same data never double counts, and a write that
never reached the recorder is simply imported again on the next poll. With a
half-hour offset a day boundary falls mid-hour, so the last stored hour can
hold only the earlier day's half; the later day's half-hour is then added to
that row, which is rewritten in place (see aggregate_hourly).

Only complete days (every half-hour present exactly once, usageDate before
today) are imported, and only in an unbroken run of calendar days from the
day after the last imported hour. Import stops at the first day that is
missing or incomplete, so a day Red Energy hasn't finished publishing is
picked up whole on a later poll rather than skipped. A day still missing or
incomplete MISSING_DAY_GRACE_DAYS after it began is given up on, with a
warning, so one day Red Energy never publishes can't stop all statistics
after it; it stays a gap in the statistics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
import logging
from typing import Any

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import DOMAIN, GST_MULTIPLIER

_LOGGER = logging.getLogger(__name__)

# Red Energy's usageDate and intervalStart are in NEM time (AEST, UTC+10,
# no daylight saving). Used to decide what "today" is and for any
# intervalStart that arrives without an offset.
NEM_TIMEZONE = "Australia/Brisbane"

# Half-hours in a complete day: 48 in NEM time, or 46/50 on the days
# daylight saving starts/ends if a day is ever reported in local time.
COMPLETE_DAY_INTERVAL_COUNTS = frozenset({46, 48, 50})

HALF_HOUR = timedelta(minutes=30)

# How long to wait for a missing or incomplete day before skipping it and
# importing the days after it. Red Energy normally publishes a day within a
# day or two, so a day still absent after a week is treated as never coming.
MISSING_DAY_GRACE_DAYS = 7

STAT_CONSUMPTION = "consumption"
STAT_GENERATION = "generation"
STAT_COST = "cost"
STAT_CREDIT = "credit"


@dataclass(frozen=True)
class StatisticSeries:
    """One imported statistic: which interval value it sums and its units."""

    key: str
    label: str
    unit: str
    unit_class: str | None


SERIES: tuple[StatisticSeries, ...] = (
    StatisticSeries(STAT_CONSUMPTION, "Consumption", UnitOfEnergy.KILO_WATT_HOUR, "energy"),
    StatisticSeries(STAT_GENERATION, "Generation", UnitOfEnergy.KILO_WATT_HOUR, "energy"),
    StatisticSeries(STAT_COST, "Consumption cost", "AUD", None),
    StatisticSeries(STAT_CREDIT, "Generation credit", "AUD", None),
)


# A series' last stored row: (start, sum, state). state is None if the
# recorder has none for it.
LastStatistic = tuple[datetime, float, float | None]


def statistic_id(consumer_number: str, key: str) -> str:
    """Return the external statistic id for a consumer and series."""
    return f"{DOMAIN}:{slugify(str(consumer_number))}_{key}"


def nem_timezone() -> tzinfo:
    """Return Red Energy's NEM time zone."""
    tz = dt_util.get_time_zone(NEM_TIMEZONE)
    assert tz is not None
    return tz


def nem_today(now: datetime | None = None) -> date:
    """Return today's date in NEM time."""
    return (now or dt_util.utcnow()).astimezone(nem_timezone()).date()


def interval_value(interval: dict[str, Any], key: str) -> float | None:
    """Return one interval's value for a series, or None if it isn't available.

    Cost is GST-inclusive, like the integration's other cost estimates and
    what the Energy Dashboard expects: consumptionDollarIncGst when Red
    Energy provides it, otherwise ex-GST consumptionDollar uplifted by
    GST_MULTIPLIER. Generation credit has no GST component.
    """
    if key == STAT_CONSUMPTION:
        return interval.get("consumption_kwh")
    if key == STAT_GENERATION:
        return interval.get("generation_kwh")
    if key == STAT_COST:
        incl_gst = interval.get("consumption_dollar_incl_gst")
        if incl_gst is not None:
            return float(incl_gst)
        ex_gst = interval.get("consumption_dollar")
        return None if ex_gst is None else float(ex_gst) * GST_MULTIPLIER
    if key == STAT_CREDIT:
        credit = interval.get("generation_dollar")
        return None if credit is None else abs(float(credit))
    raise ValueError(f"Unknown statistic series: {key}")


def parse_interval_start(value: Any) -> datetime | None:
    """Parse an intervalStart into an aware datetime (NEM time if no offset)."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=nem_timezone())
    return parsed


def _starts_at_midnight(moment: datetime, day: date) -> bool:
    """Return whether moment is 00:00 on day, in moment's own offset."""
    return moment.date() == day and moment.time() == time(0)


def day_is_complete(entry: dict[str, Any]) -> bool:
    """Return whether a usage day has every half-hour exactly once.

    Its intervalStarts must all parse, be unique and exactly 30 minutes
    apart with no gaps, and cover the whole usageDate: the first starts at
    midnight and the last ends at the next day's midnight, each in the offset
    Red Energy reported for that interval. Red Energy reports NEM time
    (+10:00), giving 48 half-hours; a day ever reported in local time across
    a daylight saving change has a different offset at each end and 46 or 50.
    """
    try:
        usage_date = date.fromisoformat(str(entry.get("date")))
    except ValueError:
        return False
    starts = []
    for interval in entry.get("intervals") or []:
        start = parse_interval_start(interval.get("interval_start")) if isinstance(interval, dict) else None
        if start is None:
            return False
        starts.append((dt_util.as_utc(start), start))
    if len(starts) not in COMPLETE_DAY_INTERVAL_COUNTS:
        return False
    starts.sort(key=lambda pair: pair[0])
    if any(b[0] - a[0] != HALF_HOUR for a, b in zip(starts, starts[1:])):
        return False
    first, last = starts[0][1], starts[-1][1]
    return _starts_at_midnight(first, usage_date) and _starts_at_midnight(
        last + HALF_HOUR, usage_date + timedelta(days=1)
    )


def next_import_day(last_start: datetime) -> date:
    """Return the usageDate (NEM time) of the hour after the last imported one."""
    return (last_start + timedelta(hours=1)).astimezone(nem_timezone()).date()


def _describe_days(days: list[date]) -> str:
    if len(days) == 1:
        return days[0].isoformat()
    return f"{days[0].isoformat()} to {days[-1].isoformat()} ({len(days)} days)"


def _days_before(usage_entries: list[dict[str, Any]], today: date) -> dict[date, dict[str, Any]]:
    """Index usage entries by usageDate, keeping only days before today."""
    days: dict[date, dict[str, Any]] = {}
    for entry in usage_entries:
        if not isinstance(entry, dict) or not entry.get("date"):
            continue
        try:
            usage_date = date.fromisoformat(str(entry["date"]))
        except ValueError:
            continue
        if usage_date < today:
            days[usage_date] = entry
    return days


def complete_days(
    usage_entries: list[dict[str, Any]],
    today: date,
    next_day: date | None = None,
    consumer_number: str = "",
    skip_missing: bool = True,
) -> list[dict[str, Any]]:
    """Return the usage days to import, oldest first.

    Only days before today (NEM time) count. next_day is the first day not
    yet imported (None when nothing has been, which starts at the earliest
    complete day). Complete days before it are returned too, so a series
    that is behind can catch up, but they never hold up newer days.

    From next_day on, days must be complete (see day_is_complete) and
    consecutive. The run stops at the first missing or incomplete day so it
    can be imported whole once Red Energy publishes it, instead of a later
    day moving the last imported hour past it for good. Once that day is
    MISSING_DAY_GRACE_DAYS old and a later complete day exists, it is skipped
    with a warning and stays a gap in the statistics. skip_missing=False
    never skips (used when the fetch for those days failed).
    """
    days = _days_before(usage_entries, today)
    complete = sorted(day for day, entry in days.items() if day_is_complete(entry))
    if not complete:
        return []
    if next_day is None:
        next_day = complete[0]
    complete_set = set(complete)

    result = [days[day] for day in complete if day < next_day]
    skipped: list[date] = []
    day = next_day
    while day <= complete[-1]:
        if day in complete_set:
            if skipped:
                _LOGGER.warning(
                    "No complete Red Energy usage for consumer %s on %s after waiting %d days - "
                    "skipping it, so the imported statistics will have a gap there",
                    consumer_number, _describe_days(skipped), MISSING_DAY_GRACE_DAYS,
                )
                skipped = []
            result.append(days[day])
        elif skip_missing and (today - day).days >= MISSING_DAY_GRACE_DAYS:
            skipped.append(day)
        else:
            _LOGGER.debug(
                "Usage for %s is %s - not importing it or later days yet",
                day, "incomplete" if day in days else "missing",
            )
            break
        day += timedelta(days=1)
    return result


def is_imported(start: datetime, last_start: datetime | None) -> bool:
    """Return whether the half-hour starting at start is already in the recorder.

    Imports are always whole days, so the stored data ends at a day boundary
    inside or at the end of the last stored hour (last_start). The half-hour
    at last_start + 30 minutes is in that row unless a day starts there (a
    half-hour offset such as +09:30), in which case the row holds only the
    earlier day's half and this one is still to import.
    """
    if last_start is None:
        return False
    if start <= last_start:
        return True
    if start == last_start + HALF_HOUR:
        return start.time() != time(0)
    return False


def aggregate_hourly(
    days: list[dict[str, Any]], key: str, last_start: datetime | None = None
) -> dict[datetime, float]:
    """Sum half-hour values into UTC hour buckets for one series.

    With last_start, only half-hours not yet imported (see is_imported) are
    summed, so the result can include last_start's hour itself, holding just
    the half-hour to add to that stored row.

    Stops at the first day missing a value for this series (e.g. no
    per-interval pricing), so no hour is ever imported with a partial total.
    """
    hourly: dict[datetime, float] = {}
    for entry in days:
        day_values: list[tuple[datetime, float]] = []
        for interval in entry.get("intervals") or []:
            start = parse_interval_start(interval.get("interval_start"))
            value = interval_value(interval, key)
            if start is None or value is None:
                return hourly
            day_values.append((start, float(value)))
        for start, value in day_values:
            if is_imported(start, last_start):
                continue
            hour = dt_util.as_utc(start).replace(minute=0, second=0, microsecond=0)
            hourly[hour] = hourly.get(hour, 0.0) + value
    return hourly


def build_statistics(
    hourly: dict[datetime, float],
    last_start: datetime | None,
    last_sum: float,
    last_state: float | None = None,
) -> list[dict[str, Any]]:
    """Turn hourly totals into StatisticData rows continuing an existing sum.

    Hours before last_start are already in the recorder and skipped, which
    is what makes re-importing the same data idempotent. An hourly value for
    last_start itself is the half-hour still missing from that stored row
    (see aggregate_hourly): with the row's last_state it is added to the row,
    rewritten with the same start so the recorder replaces it. Without
    last_state that hour is skipped.
    """
    rows = []
    running_sum = last_sum
    for hour in sorted(hourly):
        state = hourly[hour]
        if last_start is not None and hour <= last_start:
            if hour < last_start or last_state is None:
                continue
            state += last_state
        running_sum += hourly[hour]
        rows.append({
            "start": hour,
            "state": round(state, 6),
            "sum": round(running_sum, 6),
        })
    return rows


def fetch_start_date(
    last_statistics: dict[str, LastStatistic | None],
    today: date,
    backfill_days: int,
) -> date:
    """Return the first usageDate the imported series still need.

    Until consumption has been imported, that's the full backfill window.
    After that it's the day after the oldest series' last imported hour (NEM
    time). Series that don't exist yet (generation on an account without
    solar, cost when Red Energy gives no per-interval pricing) don't force a
    backfill fetch on every poll - they start from whatever data is fetched.
    Never earlier than the backfill window, so a long outage can't request
    years of data.
    """
    earliest = today - timedelta(days=backfill_days)
    if last_statistics.get(STAT_CONSUMPTION) is None:
        return earliest
    needed = [next_import_day(last[0]) for last in last_statistics.values() if last is not None]
    return max(earliest, min(needed))


async def async_get_last_statistics(
    hass: HomeAssistant, consumer_number: str
) -> dict[str, LastStatistic | None]:
    """Return each series' last imported (start, sum, state), or None if it has none."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import get_last_statistics

    result: dict[str, LastStatistic | None] = {}
    for series in SERIES:
        stat_id = statistic_id(consumer_number, series.key)
        last = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, stat_id, True, {"sum", "state"}
        )
        rows = last.get(stat_id) or []
        if rows:
            row = rows[0]
            state = row.get("state")
            result[series.key] = (
                dt_util.utc_from_timestamp(row["start"]),
                float(row.get("sum") or 0.0),
                None if state is None else float(state),
            )
        else:
            result[series.key] = None
    return result


async def async_import_statistics(
    hass: HomeAssistant,
    consumer_number: str,
    usage_entries: list[dict[str, Any]],
    last_statistics: dict[str, LastStatistic | None],
    today: date,
    skip_missing: bool = True,
) -> dict[str, int]:
    """Import new complete hours for each series; return hours added per series.

    The run of days continues from consumption's last imported hour, the
    series that is written for every imported day; any series further along
    skips the hours it already has. skip_missing is passed to complete_days.
    """
    from homeassistant.components.recorder.models import StatisticMeanType
    from homeassistant.components.recorder.statistics import async_add_external_statistics

    consumption_last = last_statistics.get(STAT_CONSUMPTION)
    next_day = None if consumption_last is None else next_import_day(consumption_last[0])
    days = complete_days(usage_entries, today, next_day, consumer_number, skip_missing)
    imported: dict[str, int] = {}
    for series in SERIES:
        last = last_statistics.get(series.key)
        last_start, last_sum, last_state = last if last else (None, 0.0, None)
        hourly = aggregate_hourly(days, series.key, last_start)
        # Don't create an all-zero generation/credit series for accounts
        # without solar - it would just clutter the Energy Dashboard picker.
        if last is None and series.key in (STAT_GENERATION, STAT_CREDIT) and not any(hourly.values()):
            continue
        rows = build_statistics(hourly, last_start, last_sum, last_state)
        if not rows:
            continue
        metadata = {
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
            "name": f"Red Energy {consumer_number} {series.label}",
            "source": DOMAIN,
            "statistic_id": statistic_id(consumer_number, series.key),
            "unit_class": series.unit_class,
            "unit_of_measurement": series.unit,
        }
        async_add_external_statistics(hass, metadata, rows)  # type: ignore[arg-type]
        imported[series.key] = len(rows)
    return imported
