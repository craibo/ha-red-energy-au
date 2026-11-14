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

Each import continues from the last statistic already in the recorder: hours
at or before it are skipped and the running ``sum`` carries on from its sum,
so re-polling the same data never double counts. Only complete days (every
half-hour present, usageDate before today) are imported, and import stops at
the first incomplete day, so a day Red Energy hasn't finished publishing is
picked up whole on a later poll rather than skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
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


def complete_days(usage_entries: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Return the leading run of complete days, oldest first.

    A day is complete when its usageDate is before today (NEM time) and all
    its half-hours (48, or 46/50 on a daylight saving change) carry a
    parseable intervalStart. The run stops at the first
    incomplete day so it can be imported whole once Red Energy fills it in.
    """
    days: dict[str, dict[str, Any]] = {}
    for entry in usage_entries:
        if isinstance(entry, dict) and entry.get("date"):
            days[entry["date"]] = entry

    result = []
    for day in sorted(days):
        entry = days[day]
        try:
            usage_date = date.fromisoformat(day)
        except ValueError:
            break
        if usage_date >= today:
            break
        intervals = entry.get("intervals") or []
        starts = [parse_interval_start(i.get("interval_start")) for i in intervals if isinstance(i, dict)]
        if len(starts) not in COMPLETE_DAY_INTERVAL_COUNTS or any(s is None for s in starts):
            _LOGGER.debug("Usage for %s is incomplete (%d intervals) - not importing it yet", day, len(starts))
            break
        result.append(entry)
    return result


def aggregate_hourly(days: list[dict[str, Any]], key: str) -> dict[datetime, float]:
    """Sum half-hour values into UTC hour buckets for one series.

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
            hour = dt_util.as_utc(start).replace(minute=0, second=0, microsecond=0)
            hourly[hour] = hourly.get(hour, 0.0) + value
    return hourly


def build_statistics(
    hourly: dict[datetime, float],
    last_start: datetime | None,
    last_sum: float,
) -> list[dict[str, Any]]:
    """Turn hourly totals into StatisticData rows continuing an existing sum.

    Hours at or before last_start are already in the recorder and skipped,
    which is what makes re-importing the same data idempotent.
    """
    rows = []
    running_sum = last_sum
    for hour in sorted(hourly):
        if last_start is not None and hour <= last_start:
            continue
        running_sum += hourly[hour]
        rows.append({
            "start": hour,
            "state": round(hourly[hour], 6),
            "sum": round(running_sum, 6),
        })
    return rows


def fetch_start_date(
    last_statistics: dict[str, tuple[datetime, float] | None],
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
    needed = [
        (last[0] + timedelta(hours=1)).astimezone(nem_timezone()).date()
        for last in last_statistics.values()
        if last is not None
    ]
    return max(earliest, min(needed))


async def async_get_last_statistics(
    hass: HomeAssistant, consumer_number: str
) -> dict[str, tuple[datetime, float] | None]:
    """Return each series' last imported (start, sum), or None if it has none."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import get_last_statistics

    result: dict[str, tuple[datetime, float] | None] = {}
    for series in SERIES:
        stat_id = statistic_id(consumer_number, series.key)
        last = await get_instance(hass).async_add_executor_job(
            get_last_statistics, hass, 1, stat_id, True, {"sum"}
        )
        rows = last.get(stat_id) or []
        if rows:
            row = rows[0]
            result[series.key] = (dt_util.utc_from_timestamp(row["start"]), float(row.get("sum") or 0.0))
        else:
            result[series.key] = None
    return result


async def async_import_statistics(
    hass: HomeAssistant,
    consumer_number: str,
    usage_entries: list[dict[str, Any]],
    last_statistics: dict[str, tuple[datetime, float] | None],
    today: date,
) -> dict[str, int]:
    """Import new complete hours for each series; return hours added per series."""
    from homeassistant.components.recorder.models import StatisticMeanType
    from homeassistant.components.recorder.statistics import async_add_external_statistics

    days = complete_days(usage_entries, today)
    imported: dict[str, int] = {}
    for series in SERIES:
        last = last_statistics.get(series.key)
        last_start, last_sum = last if last else (None, 0.0)
        hourly = aggregate_hourly(days, series.key)
        # Don't create an all-zero generation/credit series for accounts
        # without solar - it would just clutter the Energy Dashboard picker.
        if last is None and series.key in (STAT_GENERATION, STAT_CREDIT) and not any(hourly.values()):
            continue
        rows = build_statistics(hourly, last_start, last_sum)
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
