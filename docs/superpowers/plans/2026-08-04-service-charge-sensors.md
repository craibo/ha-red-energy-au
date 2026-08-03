# Service Charge Sensors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new advanced sensors — Daily Service Charge and Billing Period Service Charge — that turn the account's existing `AUD/day` supply-charge rate into directly usable monetary totals for the latest completed day and the current billing period.

**Architecture:** Two new coordinator methods (`get_daily_service_charge`, `get_billing_period_service_charge`) plus a shared rate-lookup helper (`_find_service_charge_rate`) and a shared billing-period-start helper (`_get_billing_period_start`, factored out of the existing `_get_usage_period_dates`) live in `coordinator.py`. Two new thin sensor classes in `sensor.py` read those coordinator methods, following the exact pattern of the existing `RedEnergyTotalImportCostSensor` / `RedEnergyDailyImportCostSensor`. Both sensors are added to the advanced-sensors block in `async_setup_entry`, for both electricity and gas.

**Tech Stack:** Python 3.13/3.14, Home Assistant `DataUpdateCoordinator`/`SensorEntity`, pytest + pytest-asyncio.

## Global Constraints

- Never use real personal data anywhere (code, tests, fixtures, commits) — use fake account numbers / dates like the existing fixtures already do.
- Follow semantic commit prefixes (`feat:`, `fix:`, `chore:`, `docs:`, `test:`); no test-plan mentions, no Claude/AI attribution, in commit messages.
- Every new/changed sensor behavior needs a corresponding test — this repo's convention (see `CLAUDE.md`: "When adding sensors, update both `sensor.py` and the corresponding sensor tests").
- Rate selection: a service-charge rate is one where `rate.get("type") == "SC"` **and** `rate.get("unit") == "day"` — both conditions required. Zero matches → sensors unavailable (`None`). Multiple matches → use the first in list order, ignore the rest.
- Billing-period day count uses `latest_usage_date` (via `get_latest_usage_date`) as the end boundary, **not** `datetime.now()`. If `latest_usage_date` is `None`, or the computed end is before the billing period start, the billing-period sensor reports `None`.
- Billing period start reuses the existing `lastBillDate + 1` / 30-day-fallback logic (already implemented in `_get_usage_period_dates`) via a new shared helper — do not duplicate that logic.
- Excl-GST dollar values are computed as `round(rate_excl_gst_cents / 100, 5)`, matching `data_validation.validate_rates()`'s existing `rate_incl_gst_dollars` rounding convention. No additional rounding is applied when multiplying by day count.
- Both new sensors are **advanced sensors** (created only when `CONF_ENABLE_ADVANCED_SENSORS` is enabled), for **both** electricity and gas — neither is `_electricity_only`.
- Both sensors: `device_class = SensorDeviceClass.MONETARY`, `native_unit_of_measurement = "AUD"`, `state_class = SensorStateClass.TOTAL`.

---

## File Structure

- **Modify:** `custom_components/red_energy/coordinator.py` — add `_find_service_charge_rate`, `_get_billing_period_start` (extracted from `_get_usage_period_dates`), `get_daily_service_charge`, `get_billing_period_service_charge`.
- **Modify:** `custom_components/red_energy/const.py` — add `SENSOR_TYPE_DAILY_SERVICE_CHARGE`, `SENSOR_TYPE_BILLING_PERIOD_SERVICE_CHARGE`.
- **Modify:** `custom_components/red_energy/sensor.py` — add `RedEnergyDailyServiceChargeSensor`, `RedEnergyBillingPeriodServiceChargeSensor` classes; wire both into the advanced-sensors block of `async_setup_entry`; add import lines.
- **Create:** `tests/test_service_charge_sensors.py` — coordinator method tests + sensor tests, following the fixture conventions of `tests/test_issue_62_fixes.py` (usage/date shape) and `tests/test_sensor_rates.py` (rates/metadata shape).

---

### Task 1: Extract `_get_billing_period_start` helper in coordinator.py

**Files:**
- Modify: `custom_components/red_energy/coordinator.py:74-108` (`_get_usage_period_dates`)
- Test: `tests/test_issue_62_fixes.py` (existing `TestBillingPeriodBoundary` tests must still pass unchanged — this task must not change `_get_usage_period_dates` behavior)

**Interfaces:**
- Produces: `RedEnergyDataCoordinator._get_billing_period_start(self, service: dict[str, Any]) -> datetime` — returns the resolved billing period start (a `datetime`, midnight-naive, same as today's `start_date`), applying the `lastBillDate + 1` / 30-day-fallback logic. Takes no `end_date` parameter; the 30-day fallback and the "in the future" / ">90 days old" warnings are computed relative to `datetime.now()` internally, exactly as today.

- [ ] **Step 1: Write the failing test — confirm current behavior is preserved via the helper**

Add to `tests/test_issue_62_fixes.py`, inside `class TestBillingPeriodBoundary`:

```python
    def test_get_billing_period_start_matches_get_usage_period_dates(self, coordinator):
        last_bill_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        service = {"lastBillDate": last_bill_date}

        start_from_helper = coordinator._get_billing_period_start(service)
        start_from_period_dates, _ = coordinator._get_usage_period_dates(service)

        assert start_from_helper.date() == start_from_period_dates.date()

    def test_get_billing_period_start_falls_back_to_30_days_when_missing(self, coordinator):
        start = coordinator._get_billing_period_start({})
        assert (datetime.now() - start).days == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_issue_62_fixes.py -k "billing_period_start" -v`
Expected: FAIL with `AttributeError: 'RedEnergyDataCoordinator' object has no attribute '_get_billing_period_start'`

- [ ] **Step 3: Extract the helper**

In `custom_components/red_energy/coordinator.py`, replace the body of `_get_usage_period_dates` (lines 74-108) with:

```python
    def _get_billing_period_start(self, service: dict[str, Any]) -> datetime:
        """Resolve the current billing period's start date.

        lastBillDate is the final day of the *previous* billing period, so
        the new period's usage starts the following day - otherwise that
        day's usage/cost is double-counted across both periods. Falls back
        to a 30-day window when lastBillDate is missing, invalid, in the
        future, or implausibly old (>90 days).
        """
        end_date = datetime.now()
        start_date = None

        last_bill_date = service.get("lastBillDate")
        if last_bill_date:
            try:
                start_date = datetime.strptime(last_bill_date, "%Y-%m-%d") + timedelta(days=1)

                if start_date > end_date:
                    _LOGGER.warning("lastBillDate %s is in the future, falling back to 30-day period", last_bill_date)
                    start_date = None
                elif (end_date - start_date).days > 90:
                    _LOGGER.warning("lastBillDate %s is >90 days old (%d days), this may be a long billing period",
                                  last_bill_date, (end_date - start_date).days)
                else:
                    _LOGGER.info("Using billing period: %s to %s (%d days)",
                               start_date.strftime('%Y-%m-%d'),
                               end_date.strftime('%Y-%m-%d'),
                               (end_date - start_date).days)

            except (ValueError, TypeError) as err:
                _LOGGER.warning("Invalid lastBillDate format '%s': %s, falling back to 30-day period", last_bill_date, err)
                start_date = None

        if start_date is None:
            start_date = end_date - timedelta(days=30)
            _LOGGER.info("Using 30-day fallback period: %s to %s",
                       start_date.strftime('%Y-%m-%d'),
                       end_date.strftime('%Y-%m-%d'))

        return start_date

    def _get_usage_period_dates(self, service: dict[str, Any]) -> tuple[datetime, datetime]:
        end_date = datetime.now()
        start_date = self._get_billing_period_start(service)
        return start_date, end_date
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_issue_62_fixes.py -k "TestBillingPeriodBoundary" -v`
Expected: PASS (all 4 tests: the 2 existing plus the 2 new ones)

- [ ] **Step 5: Run the full existing suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: PASS (same pass count as before this change, plus the 2 new tests)

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/coordinator.py tests/test_issue_62_fixes.py
git commit -m "refactor: extract billing period start into shared coordinator helper"
```

---

### Task 2: Add `_find_service_charge_rate` and `get_daily_service_charge` to coordinator.py

**Files:**
- Modify: `custom_components/red_energy/coordinator.py` — add methods after `get_service_rates` (currently at line 600-606)
- Test: `tests/test_service_charge_sensors.py` (new file)

**Interfaces:**
- Consumes: `self.get_service_rates(property_id, service_type) -> list[dict]` (existing, coordinator.py:600)
- Produces:
  - `RedEnergyDataCoordinator._find_service_charge_rate(self, property_id: str, service_type: str) -> dict[str, Any] | None`
  - `RedEnergyDataCoordinator.get_daily_service_charge(self, property_id: str, service_type: str) -> float | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_service_charge_sensors.py`:

```python
"""Tests for Daily Service Charge and Billing Period Service Charge sensors (issue #71)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import (
    RedEnergyDailyServiceChargeSensor,
    RedEnergyBillingPeriodServiceChargeSensor,
)

SUPPLY_CHARGE_RATE = {
    "rate_code": "80008279798S",
    "rate_desc": "Daily Supply Charge",
    "rate_incl_gst_dollars": 1.78145,
    "type": "SC",
    "rate_excl_gst_cents": 161.95,
    "discounted_rate_excl_gst_in_cents": 161.95,
    "discounted_rate_incl_gst_in_cents": 178.145,
    "unit": "day",
    "unit_step_desc": None,
}

ENERGY_RATE = {
    "rate_code": "80008279798P",
    "rate_desc": "Peak",
    "rate_incl_gst_dollars": 0.27005,
    "type": "PR",
    "rate_excl_gst_cents": 24.55,
    "discounted_rate_excl_gst_in_cents": 24.55,
    "discounted_rate_incl_gst_in_cents": 27.005,
    "unit": "kWh",
    "unit_step_desc": None,
}

SECOND_SUPPLY_CHARGE_RATE = {
    "rate_code": "80008279798S2",
    "rate_desc": "Second Daily Supply Charge",
    "rate_incl_gst_dollars": 0.5,
    "type": "SC",
    "rate_excl_gst_cents": 45.45,
    "discounted_rate_excl_gst_in_cents": 45.45,
    "discounted_rate_incl_gst_in_cents": 50.0,
    "unit": "day",
    "unit_step_desc": None,
}


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    return hass


@pytest.fixture
def coordinator(mock_hass):
    with patch(
        "custom_components.red_energy.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        coord = RedEnergyDataCoordinator(
            hass=mock_hass,
            username="test_user",
            password="test_pass",
            selected_accounts=["2000002"],
            services=["electricity"],
        )
    coord.api = AsyncMock()
    coord.api._access_token = "test_token"
    return coord


def _set_coordinator_data(coordinator, rates, usage_entries=None, last_bill_date=None):
    """Build coordinator.data with both the property.services (metadata/rates)
    and top-level services (usage) shapes get_service_metadata/get_service_usage expect."""
    service_metadata = {
        "type": SERVICE_TYPE_ELECTRICITY,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": rates,
    }
    if last_bill_date is not None:
        service_metadata["lastBillDate"] = last_bill_date

    services_usage = {}
    if usage_entries is not None:
        services_usage[SERVICE_TYPE_ELECTRICITY] = {
            "consumer_number": "elec-1",
            "last_updated": "2024-01-30T10:00:00",
            "usage_data": {
                "from_date": "2024-01-01",
                "to_date": "2024-01-30",
                "usage_data": usage_entries,
            },
        }

    coordinator.data = {
        "usage_data": {
            "2000002": {
                "property": {
                    "name": "Test property",
                    "address": {},
                    "services": [service_metadata],
                },
                "services": services_usage,
            },
        }
    }


class TestFindServiceChargeRate:
    def test_returns_none_when_no_rates(self, coordinator):
        _set_coordinator_data(coordinator, [])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_no_sc_day_rate(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_finds_the_sc_day_rate_among_others(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE, SUPPLY_CHARGE_RATE])
        result = coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == SUPPLY_CHARGE_RATE

    def test_uses_first_match_when_multiple_sc_day_rates(self, coordinator):
        _set_coordinator_data(coordinator, [SUPPLY_CHARGE_RATE, SECOND_SUPPLY_CHARGE_RATE])
        result = coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == SUPPLY_CHARGE_RATE

    def test_type_sc_without_day_unit_does_not_match(self, coordinator):
        rate = {**SUPPLY_CHARGE_RATE, "unit": "kWh"}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_day_unit_without_type_sc_does_not_match(self, coordinator):
        rate = {**SUPPLY_CHARGE_RATE, "type": "PR"}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None


class TestGetDailyServiceCharge:
    def test_returns_rate_incl_gst_dollars(self, coordinator):
        _set_coordinator_data(coordinator, [SUPPLY_CHARGE_RATE])
        assert coordinator.get_daily_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) == pytest.approx(1.78145)

    def test_returns_none_when_no_matching_rate(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE])
        assert coordinator.get_daily_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_charge_sensors.py -k "TestFindServiceChargeRate or TestGetDailyServiceCharge" -v`
Expected: FAIL with `AttributeError: 'RedEnergyDataCoordinator' object has no attribute '_find_service_charge_rate'` (the `RedEnergyDailyServiceChargeSensor`/`RedEnergyBillingPeriodServiceChargeSensor` import at the top of the file will also fail at collection time — that's expected and resolved in Task 4)

For this step only, temporarily comment out the `from custom_components.red_energy.sensor import (...)` block at the top of the test file (both sensor names) so the coordinator tests can run in isolation; restore it in Task 4 Step 1.

- [ ] **Step 3: Implement `_find_service_charge_rate` and `get_daily_service_charge`**

In `custom_components/red_energy/coordinator.py`, add immediately after `get_service_rates` (after line 606):

```python
    def _find_service_charge_rate(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Find the daily service/supply charge rate for a property and service.

        Identified by type == "SC" and unit == "day" together - neither
        field alone reliably distinguishes the service charge from other
        rates on the same plan. If more than one rate matches, the first
        in list order is used.
        """
        rates = self.get_service_rates(property_id, service_type)
        return next(
            (r for r in rates if r.get("type") == "SC" and r.get("unit") == "day"),
            None,
        )

    def get_daily_service_charge(self, property_id: str, service_type: str) -> float | None:
        """Get the daily service/supply charge amount, GST-inclusive."""
        rate = self._find_service_charge_rate(property_id, service_type)
        return rate.get("rate_incl_gst_dollars") if rate else None
```

- [ ] **Step 4: Restore the sensor import and re-run (will still fail at collection - expected until Task 4)**

Leave the sensor import commented out for now; run only the coordinator-focused tests:

Run: `pytest tests/test_service_charge_sensors.py -k "TestFindServiceChargeRate or TestGetDailyServiceCharge" -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add custom_components/red_energy/coordinator.py tests/test_service_charge_sensors.py
git commit -m "feat: add service charge rate lookup to coordinator"
```

---

### Task 3: Add `get_billing_period_service_charge` to coordinator.py

**Files:**
- Modify: `custom_components/red_energy/coordinator.py` — add method after `get_daily_service_charge`
- Test: `tests/test_service_charge_sensors.py`

**Interfaces:**
- Consumes:
  - `self._find_service_charge_rate(property_id, service_type) -> dict | None` (Task 2)
  - `self.get_latest_usage_date(property_id, service_type) -> str | None` (existing, coordinator.py:716)
  - `self.get_service_metadata(property_id, service_type) -> dict | None` (existing, coordinator.py:584)
  - `self._get_billing_period_start(service: dict) -> datetime` (Task 1)
- Produces: `RedEnergyDataCoordinator.get_billing_period_service_charge(self, property_id: str, service_type: str) -> float | None`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_service_charge_sensors.py`:

```python
class TestGetBillingPeriodServiceCharge:
    def test_seven_day_period_matches_issue_example(self, coordinator):
        last_bill_date = "2025-07-25"
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date=last_bill_date,
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == pytest.approx(7 * 1.78145)

    def test_returns_none_when_no_matching_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [ENERGY_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_no_usage_data(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_latest_usage_date_before_period_start(self, coordinator):
        """Stale/cached usage predating a just-rolled billing period must not produce a negative day count."""
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-07-20", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_falls_back_to_30_day_period_when_last_bill_date_missing(self, coordinator):
        today = datetime.now()
        latest_usage_date = today.strftime("%Y-%m-%d")
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": latest_usage_date, "import_usage": 10.0}],
            last_bill_date=None,
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        expected_days = (today.date() - (today - timedelta(days=30)).date()).days + 1
        assert result == pytest.approx(expected_days * 1.78145)

    def test_single_day_period_counts_as_one_day(self, coordinator):
        """lastBillDate + 1 == latest usageDate must count as exactly 1 day, not 0."""
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-07-26", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == pytest.approx(1 * 1.78145)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_charge_sensors.py -k "TestGetBillingPeriodServiceCharge" -v`
Expected: FAIL with `AttributeError: 'RedEnergyDataCoordinator' object has no attribute 'get_billing_period_service_charge'`

- [ ] **Step 3: Implement `get_billing_period_service_charge`**

In `custom_components/red_energy/coordinator.py`, add immediately after `get_daily_service_charge`:

```python
    def get_billing_period_service_charge(self, property_id: str, service_type: str) -> float | None:
        """Get the accumulated service charge from the billing period start
        through the latest completed usageDate, inclusive.

        Uses the latest completed usageDate as the period end - not
        datetime.now() - so a day with no confirmed usage data yet is
        never counted as a represented day.
        """
        rate = self._find_service_charge_rate(property_id, service_type)
        if rate is None:
            return None

        latest_usage_date_str = self.get_latest_usage_date(property_id, service_type)
        if not latest_usage_date_str:
            return None

        try:
            billing_period_end = datetime.strptime(latest_usage_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

        service_metadata = self.get_service_metadata(property_id, service_type) or {}
        billing_period_start = self._get_billing_period_start(service_metadata).date()

        if billing_period_end < billing_period_start:
            return None

        represented_day_count = (billing_period_end - billing_period_start).days + 1
        return rate["rate_incl_gst_dollars"] * represented_day_count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_charge_sensors.py -k "TestGetBillingPeriodServiceCharge" -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run full coordinator-related suite for regressions**

Run: `pytest tests/test_issue_62_fixes.py tests/test_service_charge_sensors.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/coordinator.py tests/test_service_charge_sensors.py
git commit -m "feat: add billing period service charge calculation to coordinator"
```

---

### Task 4: Add sensor type constants and sensor classes to sensor.py

**Files:**
- Modify: `custom_components/red_energy/const.py` — add 2 new constants after line 92 (`SENSOR_TYPE_RATE_PREFIX`)
- Modify: `custom_components/red_energy/sensor.py` — add imports, 2 new sensor classes, wire into `async_setup_entry`
- Test: `tests/test_service_charge_sensors.py` (restore the sensor import, add sensor-level tests)

**Interfaces:**
- Consumes:
  - `coordinator.get_daily_service_charge(property_id, service_type) -> float | None` (Task 2)
  - `coordinator.get_billing_period_service_charge(property_id, service_type) -> float | None` (Task 3)
  - `coordinator._find_service_charge_rate(property_id, service_type) -> dict | None` (Task 2, used directly by sensors for excl-GST/day-count attributes)
  - `coordinator.get_latest_usage_date(property_id, service_type) -> str | None` (existing)
  - `coordinator.get_service_metadata(property_id, service_type) -> dict | None` (existing)
  - `RedEnergyBaseSensor._get_latest_usage_date_reset(self) -> datetime | None` (existing, sensor.py:326)
- Produces:
  - `RedEnergyDailyServiceChargeSensor(coordinator, config_entry, property_id, service_type)` class
  - `RedEnergyBillingPeriodServiceChargeSensor(coordinator, config_entry, property_id, service_type)` class

- [ ] **Step 1: Add sensor type constants**

In `custom_components/red_energy/const.py`, immediately after `SENSOR_TYPE_RATE_PREFIX: Final = "rate"` (line 92), add:

```python
SENSOR_TYPE_DAILY_SERVICE_CHARGE: Final = "daily_service_charge"
SENSOR_TYPE_BILLING_PERIOD_SERVICE_CHARGE: Final = "billing_period_service_charge"
```

- [ ] **Step 2: Restore and extend the test file's sensor import and write failing sensor tests**

In `tests/test_service_charge_sensors.py`, restore the import at the top (undo the Task 2 Step 2 comment-out):

```python
from custom_components.red_energy.sensor import (
    RedEnergyDailyServiceChargeSensor,
    RedEnergyBillingPeriodServiceChargeSensor,
)
```

Add at the end of the file:

```python
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


class TestDailyServiceChargeSensor:
    def test_native_value_and_metadata(self, coordinator):
        _set_coordinator_data(coordinator, [SUPPLY_CHARGE_RATE])
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value == pytest.approx(1.78145)
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class == SensorStateClass.TOTAL

    def test_native_value_none_when_no_rate(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE])
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None

    def test_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
        )
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        attrs = sensor.extra_state_attributes
        assert attrs["usage_date"] == "2025-08-01"
        assert attrs["service_rate_incl_gst"] == pytest.approx(1.78145)
        assert attrs["service_rate_excl_gst"] == pytest.approx(1.6195)
        assert attrs["represented_day_count"] == 1
        assert "calculation" in attrs

    def test_last_reset_is_latest_usage_date(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
        )
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.last_reset.date().isoformat() == "2025-08-01"


class TestBillingPeriodServiceChargeSensor:
    def test_native_value_and_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value == pytest.approx(7 * 1.78145)
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class == SensorStateClass.TOTAL

        attrs = sensor.extra_state_attributes
        assert attrs["billing_period_start"] == "2025-07-26"
        assert attrs["billing_period_end"] == "2025-08-01"
        assert attrs["latest_usage_date"] == "2025-08-01"
        assert attrs["represented_day_count"] == 7
        assert attrs["service_rate_incl_gst"] == pytest.approx(1.78145)
        assert attrs["service_rate_excl_gst"] == pytest.approx(1.6195)
        assert "calculation" in attrs

    def test_native_value_none_when_no_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [ENERGY_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None

    def test_last_reset_is_billing_period_start(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.last_reset.date().isoformat() == "2025-07-26"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_service_charge_sensors.py -k "SensorTest or SensorSensor or DailyServiceChargeSensor or BillingPeriodServiceChargeSensor" -v`
Expected: FAIL with `ImportError: cannot import name 'RedEnergyDailyServiceChargeSensor'`

- [ ] **Step 4: Add imports in sensor.py**

In `custom_components/red_energy/sensor.py`, in the `from .const import (...)` block (lines 23-54), add these two lines in alphabetical position (after `SENSOR_TYPE_BILLING_FREQUENCY`, before `SENSOR_TYPE_CHARGE_CLASS`):

```python
    SENSOR_TYPE_BILLING_PERIOD_SERVICE_CHARGE,
```

and after `SENSOR_TYPE_DAILY_AVERAGE` (before `SENSOR_TYPE_DISTRIBUTOR`):

```python
    SENSOR_TYPE_DAILY_SERVICE_CHARGE,
```

- [ ] **Step 5: Implement the two sensor classes**

In `custom_components/red_energy/sensor.py`, add immediately after the `RedEnergyRateSensor` class (after line 868, before `class RedEnergyAddressSensor`):

```python
class RedEnergyDailyServiceChargeSensor(RedEnergyBaseSensor):
    """Red Energy daily service/supply charge sensor.

    Represents the service charge for the latest completed usageDate,
    derived from the plan's daily supply-charge rate (type "SC", unit
    "day"). Unavailable when the plan has no such rate.
    """

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the daily service charge sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_DAILY_SERVICE_CHARGE)

        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:currency-usd"

    @property
    def last_reset(self) -> datetime | None:
        """Return the start of the represented usageDate so HA statistics don't sum across days."""
        return self._get_latest_usage_date_reset()

    @property
    def native_value(self) -> float | None:
        """Return the daily service charge, GST-inclusive."""
        return self.coordinator.get_daily_service_charge(self._property_id, self._service_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the rate basis and calculation for the daily service charge."""
        rate = self.coordinator._find_service_charge_rate(self._property_id, self._service_type)
        if rate is None:
            return None

        rate_incl_gst = rate.get("rate_incl_gst_dollars")
        rate_excl_gst_cents = rate.get("rate_excl_gst_cents")
        rate_excl_gst = round(rate_excl_gst_cents / 100, 5) if rate_excl_gst_cents is not None else None

        return {
            "usage_date": self.coordinator.get_latest_usage_date(self._property_id, self._service_type),
            "service_rate_incl_gst": rate_incl_gst,
            "service_rate_excl_gst": rate_excl_gst,
            "represented_day_count": 1,
            "calculation": "service_rate_incl_gst × 1 day",
        }


class RedEnergyBillingPeriodServiceChargeSensor(RedEnergyBaseSensor):
    """Red Energy billing period service/supply charge sensor.

    Represents the accumulated service charge from the start of the
    current billing period through the latest completed usageDate,
    inclusive. Unavailable when the plan has no daily supply-charge
    rate, or when the represented day count cannot be determined.
    """

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the billing period service charge sensor."""
        super().__init__(
            coordinator, config_entry, property_id, service_type, SENSOR_TYPE_BILLING_PERIOD_SERVICE_CHARGE
        )

        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:currency-usd"

    def _billing_period_start_date(self) -> datetime | None:
        service_metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type) or {}
        return self.coordinator._get_billing_period_start(service_metadata)

    @property
    def last_reset(self) -> datetime | None:
        """Return the billing period start date so HA statistics reset correctly."""
        start_date = self._billing_period_start_date()
        if start_date is None:
            return None
        return dt_util.as_utc(start_date)

    @property
    def native_value(self) -> float | None:
        """Return the accumulated billing period service charge, GST-inclusive."""
        return self.coordinator.get_billing_period_service_charge(self._property_id, self._service_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the rate basis, day count, and calculation for the billing period service charge."""
        if self.native_value is None:
            return None

        rate = self.coordinator._find_service_charge_rate(self._property_id, self._service_type)
        latest_usage_date = self.coordinator.get_latest_usage_date(self._property_id, self._service_type)
        billing_period_start = self._billing_period_start_date()

        rate_incl_gst = rate.get("rate_incl_gst_dollars") if rate else None
        rate_excl_gst_cents = rate.get("rate_excl_gst_cents") if rate else None
        rate_excl_gst = round(rate_excl_gst_cents / 100, 5) if rate_excl_gst_cents is not None else None

        represented_day_count = None
        if billing_period_start is not None and latest_usage_date:
            end_date = datetime.strptime(latest_usage_date, "%Y-%m-%d").date()
            represented_day_count = (end_date - billing_period_start.date()).days + 1

        return {
            "billing_period_start": billing_period_start.strftime("%Y-%m-%d") if billing_period_start else None,
            "billing_period_end": latest_usage_date,
            "latest_usage_date": latest_usage_date,
            "represented_day_count": represented_day_count,
            "service_rate_incl_gst": rate_incl_gst,
            "service_rate_excl_gst": rate_excl_gst,
            "calculation": f"service_rate_incl_gst × {represented_day_count} days",
        }


```

- [ ] **Step 6: Wire both sensors into the advanced-sensors block**

In `custom_components/red_energy/sensor.py`, inside `async_setup_entry`, in the `if advanced_sensors_enabled:` block (around line 143-162), add to the list:

```python
                    RedEnergyCarbonEmissionSensor(coordinator, config_entry, account_id, service_type),
                    # NEW: Service/supply charge sensors
                    RedEnergyDailyServiceChargeSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyBillingPeriodServiceChargeSensor(coordinator, config_entry, account_id, service_type),
                ])
```

(i.e. insert the two new lines directly before the closing `])` of that list, right after the existing `RedEnergyCarbonEmissionSensor` line.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_service_charge_sensors.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 8: Run the full test suite for regressions**

Run: `pytest tests/ -v`
Expected: PASS (all tests, previous count + all new tests added in this plan)

- [ ] **Step 9: Run flake8 and mypy**

Run: `flake8 custom_components --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: 0 errors

Run: `mypy custom_components/red_energy --ignore-missing-imports`
Expected: no new errors introduced by the changed files (pre-existing errors elsewhere are not this task's concern)

- [ ] **Step 10: Commit**

```bash
git add custom_components/red_energy/const.py custom_components/red_energy/sensor.py tests/test_service_charge_sensors.py
git commit -m "feat: add daily and billing period service charge sensors (#71)"
```

---

### Task 5: Verify entity setup test coverage for advanced-sensor gating

**Files:**
- Test: `tests/test_service_charge_sensors.py` (add `async_setup_entry`-level tests, following `tests/test_sensor_rates.py`'s `_coordinator()` mock pattern)

**Interfaces:**
- Consumes: `async_setup_entry(hass, config_entry, async_add_entities)` (existing, sensor.py:64)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_service_charge_sensors.py`:

```python
from custom_components.red_energy.const import DOMAIN
from custom_components.red_energy.sensor import async_setup_entry


def _mock_coordinator_for_setup(rates, service_type=SERVICE_TYPE_ELECTRICITY, property_id="2000002"):
    coordinator = MagicMock()
    service_metadata = {
        "type": service_type,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": rates,
    }
    coordinator.data = {
        "usage_data": {
            property_id: {
                "property": {"name": "Test property", "address": {}, "services": [service_metadata]},
                "services": {},
            },
        }
    }
    coordinator.last_update_success = True
    coordinator.get_property_data = MagicMock(
        side_effect=lambda pid: coordinator.data["usage_data"].get(str(pid))
    )

    def get_service_metadata(prop_id, svc_type):
        property_data = coordinator.data["usage_data"].get(str(prop_id))
        if not property_data:
            return None
        services = property_data["property"].get("services", [])
        return next((s for s in services if s.get("type") == svc_type), None)

    coordinator.get_service_metadata = MagicMock(side_effect=get_service_metadata)

    def get_service_rates(prop_id, svc_type):
        metadata = get_service_metadata(prop_id, svc_type)
        return metadata.get("rates", []) if metadata else []

    coordinator.get_service_rates = MagicMock(side_effect=get_service_rates)
    coordinator.get_service_usage = MagicMock(return_value=None)
    return coordinator


@pytest.mark.asyncio
async def test_service_charge_sensors_not_created_when_advanced_disabled():
    coordinator = _mock_coordinator_for_setup([SUPPLY_CHARGE_RATE])
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["2000002"],
                "services": [SERVICE_TYPE_ELECTRICITY],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))
    await async_setup_entry(hass, config_entry, async_add_entities)

    charge_sensors = [
        e for e in added_entities
        if isinstance(e, (RedEnergyDailyServiceChargeSensor, RedEnergyBillingPeriodServiceChargeSensor))
    ]
    assert charge_sensors == []


@pytest.mark.asyncio
async def test_service_charge_sensors_created_for_electricity_and_gas_when_advanced_enabled():
    from custom_components.red_energy.const import CONF_ENABLE_ADVANCED_SENSORS, SERVICE_TYPE_GAS

    coordinator = _mock_coordinator_for_setup([SUPPLY_CHARGE_RATE], service_type=SERVICE_TYPE_ELECTRICITY)
    gas_coordinator_data = coordinator.data["usage_data"]["2000002"]["property"]["services"]
    gas_coordinator_data.append({**gas_coordinator_data[0], "type": SERVICE_TYPE_GAS})

    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {CONF_ENABLE_ADVANCED_SENSORS: True}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["2000002"],
                "services": [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))
    await async_setup_entry(hass, config_entry, async_add_entities)

    daily_charge_sensors = [e for e in added_entities if isinstance(e, RedEnergyDailyServiceChargeSensor)]
    billing_charge_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyBillingPeriodServiceChargeSensor)
    ]
    assert len(daily_charge_sensors) == 2
    assert len(billing_charge_sensors) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_charge_sensors.py -k "async_setup_entry or advanced_disabled or advanced_enabled" -v`
Expected: FAIL if Task 4 Step 6 was skipped or mis-wired (0 sensors created instead of 2); if Task 4 was completed correctly, this may already PASS - in that case this task documents/locks in the behavior rather than driving it.

- [ ] **Step 3: If failing, fix the wiring in `async_setup_entry`**

Re-check Task 4 Step 6 was applied correctly (both sensor constructors present in the `if advanced_sensors_enabled:` list, correctly indented as part of `service_entities.extend([...])`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_service_charge_sensors.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Run the full test suite one final time**

Run: `pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add tests/test_service_charge_sensors.py
git commit -m "test: verify service charge sensor setup gating and multi-service creation"
```

---

## Post-implementation

- Update the CHANGELOG/release notes per the repo's `creating-pre-releases` skill when ready to cut a release (not part of this plan — a separate step once the branch is reviewed).
- Manifest version was already bumped to `1.17.0` on this branch prior to this plan's work.
