# CL2/TOU Derived Sensors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the CL2/TOU inference engine (merged in #65) into the coordinator and add the derived sensors described in issue #61 — Inferred CL2 Energy, Corrected Peak/Shoulder/Off-peak Import, Inferred CL2 Cost, and Reconstructed Import Cost — for accounts whose plan has an identifiable CL2 rate.

**Architecture:** One new coordinator method aggregates `infer_cl2_interval()` results across every interval in a service's usage period, using `resolve_rate_roles()` (both from `cl2_inference.py`, merged in #65) to resolve the account's rates once per aggregation call. Six new sensor classes read from this aggregation, all gated behind the existing advanced-sensors toggle and only created when the account's plan has an unambiguous CL2 rate — accounts without controlled load never see these entities, matching the existing pattern for solar/gas-only sensors.

**Tech Stack:** Python 3.13/3.14, pytest, Home Assistant custom integration conventions (plain dicts, no dataclasses).

## Global Constraints

- No existing sensor, coordinator method, or API/validation field changes meaning. This plan only adds new code.
- Follow existing codebase conventions: plain `dict[str, Any]` returns, not dataclasses.
- All new tests live in `tests/` at the repo root, flat layout (matches the existing test suite).
- **Known limitation, must be documented, not solved**: the integration only ever has access to `currentPlan.rates` (today's plan rates) — there is no historical rate-change data anywhere in the API or codebase. All inference in this plan uses the account's *current* rates for every interval, including intervals from earlier in the billing period. If a plan's rates changed mid-period, inference for days before that change will be measurably wrong. This must be stated in the new sensors' diagnostic attributes (a `rates_source` or similar attribute noting "current plan rates, not historical") and is intentionally not solved by this plan — solving it would require Red Energy exposing rate-change history, which nothing in the current API model provides.
- CL2 sensors are gated by whether `resolve_rate_roles()` returns `"CL2"` in its `unresolved_roles` list for that account's rates — if unresolved (no CL2 rate, or an ambiguous match), none of the six new sensors are created for that account at all. This must be re-evaluated at every `async_setup_entry` call (not cached across HA restarts), since `coordinator.get_service_rates()` reflects whatever the API returns each session.
- New sensors are electricity-only (`_electricity_only = True`) and live in the advanced-sensors block (`CONF_ENABLE_ADVANCED_SENSORS` option), matching `RedEnergyCarbonEmissionSensor`/`RedEnergyMaxDemandSensor`'s existing pattern in `sensor.py`.
- `flake8 custom_components --count --select=E9,F63,F7,F82` and `mypy custom_components/red_energy --ignore-missing-imports` should stay clean for touched files (both `continue-on-error: true` in CI; not installed in this dev environment — a confirmed pre-existing gap, do not treat as a new issue if you can't run them).

---

### Task 1: Coordinator aggregation method

**Files:**
- Modify: `custom_components/red_energy/coordinator.py`
- Test: `tests/test_coordinator_cl2_aggregation.py` (new file)

**Interfaces:**
- Consumes: `custom_components.red_energy.cl2_inference.infer_cl2_interval(interval, rates_incl_gst, cl2_rate_incl_gst, *, tolerance_kwh=0.01) -> dict[str, Any]` and `custom_components.red_energy.cl2_inference.resolve_rate_roles(rates: list[dict[str, Any]]) -> dict[str, Any]` (both merged in #65, already on `main`). Also consumes `self.get_service_usage(property_id, service_type)` and `self.get_service_rates(property_id, service_type)` (existing coordinator methods).
- Produces: `get_cl2_inference(self, property_id: str, service_type: str) -> dict[str, Any] | None` — a new coordinator method. Returns `None` when the service has no usage data, or when `resolve_rate_roles()` cannot resolve a CL2 rate for it (i.e. `"CL2"` appears in `unresolved_roles`). Otherwise returns a dict with exactly these keys, which Task 2's sensors read directly:
  - `"cl2_energy_kwh"`: `float` — sum of `cl2_kwh` across every accepted interval in the period
  - `"corrected_peak_kwh"`: `float` — sum of `tou_kwh` across accepted intervals where `tariff_component == "PEAK"`
  - `"corrected_shoulder_kwh"`: `float` — sum of `tou_kwh` across accepted intervals where `tariff_component == "SHOULDER"`
  - `"corrected_offpeak_kwh"`: `float` — sum of `tou_kwh` across accepted intervals where `tariff_component == "OFFPEAK"`
  - `"cl2_cost"`: `float` — sum of `(cl2_kwh * cl2_rate_incl_gst)` across accepted intervals (the CL2 portion of `reconstructed_cost`)
  - `"reconstructed_import_cost"`: `float` — sum of `reconstructed_cost` across accepted intervals
  - `"api_import_cost"`: `float` — sum of `api_cost` across accepted intervals (for comparison/diagnostics against the raw daily cost sensors)
  - `"reconciliation_difference"`: `float` — `reconstructed_import_cost - api_import_cost`
  - `"accepted_interval_count"`: `int`
  - `"rejected_interval_count"`: `int`
  - `"rejection_reasons"`: `dict[str, int]` — counts of each distinct `reason` value seen among rejected intervals (e.g. `{"pricing_not_reliable": 3}`)
  - `"rates_used"`: `dict[str, float]` — the `rates_incl_gst` dict plus `"CL2"` key holding `cl2_rate_incl_gst`, i.e. `{**rates_incl_gst, "CL2": cl2_rate_incl_gst}`, for diagnostic display
  - `"rates_source"`: `str` — the literal string `"current plan rates (no historical rate data available)"`

  All float values rounded to 3 decimal places for energy (`cl2_energy_kwh`, `corrected_peak_kwh`, `corrected_shoulder_kwh`, `corrected_offpeak_kwh`) matching the existing daily/total usage sensors' precision (see `_normalize_usage_entry`'s `round(..., 3)` calls in `api.py`), and 2 decimal places for cost (`cl2_cost`, `reconstructed_import_cost`, `api_import_cost`, `reconciliation_difference`), matching the existing cost sensors' precision (see `round(import_cost, 2)` in `api.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_coordinator_cl2_aggregation.py`:

```python
"""Tests for coordinator.get_cl2_inference() - aggregates CL2/TOU inference
across a service's usage period using cl2_inference.infer_cl2_interval()
and resolve_rate_roles() (merged in #65)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY

RATES = [
    {"rate_code": "P1", "rate_desc": "Peak", "rate_incl_gst_dollars": 0.45760},
    {"rate_code": "S1", "rate_desc": "Shoulder", "rate_incl_gst_dollars": 0.41745},
    {"rate_code": "O1", "rate_desc": "Off-peak", "rate_incl_gst_dollars": 0.32483},
    {"rate_code": "C1", "rate_desc": "CL2", "rate_incl_gst_dollars": 0.18425},
]

RATES_NO_CL2 = [
    {"rate_code": "P1", "rate_desc": "Peak", "rate_incl_gst_dollars": 0.45760},
]


def _shoulder_interval(consumption_kwh=1.702, cost=0.4007, pricing_available=True, pricing_reliable=True):
    return {
        "interval_start": "2026-07-23T21:00:00+10:00",
        "consumption_kwh": consumption_kwh,
        "consumption_dollar_incl_gst": cost,
        "tariff_component": "SHOULDER",
        "pricing_available": pricing_available,
        "pricing_reliable": pricing_reliable,
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
            selected_accounts=["prop-001"],
            services=["electricity"],
        )
    coord.api = AsyncMock()
    coord.api._access_token = "test_token"
    return coord


def _set_service_data(coordinator, usage_entries, rates):
    coordinator.data = {
        "usage_data": {
            "prop-001": {
                "property": {"services": [{"type": "electricity", "rates": rates}]},
                "services": {
                    "electricity": {
                        "consumer_number": "elec-123",
                        "last_updated": "2026-07-24T03:00:00",
                        "usage_data": {
                            "from_date": "2026-07-01",
                            "to_date": "2026-07-24",
                            "usage_data": usage_entries,
                        },
                    }
                },
            }
        }
    }


def test_returns_none_when_no_usage_data(coordinator):
    _set_service_data(coordinator, [], RATES)
    assert coordinator.get_cl2_inference("prop-001", SERVICE_TYPE_ELECTRICITY) is None


def test_returns_none_when_cl2_rate_unresolved(coordinator):
    _set_service_data(
        coordinator,
        [{"date": "2026-07-23", "intervals": [_shoulder_interval()]}],
        RATES_NO_CL2,
    )
    assert coordinator.get_cl2_inference("prop-001", SERVICE_TYPE_ELECTRICITY) is None


def test_aggregates_single_accepted_interval(coordinator):
    _set_service_data(
        coordinator,
        [{"date": "2026-07-23", "intervals": [_shoulder_interval()]}],
        RATES,
    )
    result = coordinator.get_cl2_inference("prop-001", SERVICE_TYPE_ELECTRICITY)

    assert result is not None
    assert result["cl2_energy_kwh"] == pytest.approx(1.328, abs=0.01)
    assert result["corrected_shoulder_kwh"] == pytest.approx(0.374, abs=0.01)
    assert result["corrected_peak_kwh"] == 0.0
    assert result["corrected_offpeak_kwh"] == 0.0
    assert result["accepted_interval_count"] == 1
    assert result["rejected_interval_count"] == 0
    assert result["rejection_reasons"] == {}
    assert result["rates_used"] == {
        "PEAK": pytest.approx(0.45760),
        "SHOULDER": pytest.approx(0.41745),
        "OFFPEAK": pytest.approx(0.32483),
        "CL2": pytest.approx(0.18425),
    }
    assert result["rates_source"] == "current plan rates (no historical rate data available)"
    assert result["reconciliation_difference"] == pytest.approx(0.0, abs=0.001)


def test_aggregates_across_multiple_days_and_tariff_periods(coordinator):
    peak_interval = {
        "interval_start": "2026-07-23T08:00:00+10:00",
        "consumption_kwh": 1.0,
        "consumption_dollar_incl_gst": 1.0 * 0.45760,  # pure TOU, no CL2
        "tariff_component": "PEAK",
        "pricing_available": True,
        "pricing_reliable": True,
    }
    offpeak_interval = {
        "interval_start": "2026-07-24T02:00:00+10:00",
        "consumption_kwh": 1.0,
        "consumption_dollar_incl_gst": 1.0 * 0.18425,  # pure CL2, no TOU
        "tariff_component": "OFFPEAK",
        "pricing_available": True,
        "pricing_reliable": True,
    }
    _set_service_data(
        coordinator,
        [
            {"date": "2026-07-23", "intervals": [peak_interval, _shoulder_interval()]},
            {"date": "2026-07-24", "intervals": [offpeak_interval]},
        ],
        RATES,
    )
    result = coordinator.get_cl2_inference("prop-001", SERVICE_TYPE_ELECTRICITY)

    assert result["corrected_peak_kwh"] == pytest.approx(1.0, abs=1e-3)
    assert result["corrected_offpeak_kwh"] == pytest.approx(0.0, abs=1e-3)
    assert result["cl2_energy_kwh"] == pytest.approx(1.0 + 1.328, abs=0.01)
    assert result["accepted_interval_count"] == 3


def test_counts_rejected_intervals_by_reason(coordinator):
    _set_service_data(
        coordinator,
        [
            {
                "date": "2026-07-23",
                "intervals": [
                    _shoulder_interval(),
                    _shoulder_interval(pricing_reliable=False),
                    _shoulder_interval(pricing_available=False),
                ],
            }
        ],
        RATES,
    )
    result = coordinator.get_cl2_inference("prop-001", SERVICE_TYPE_ELECTRICITY)

    assert result["accepted_interval_count"] == 1
    assert result["rejected_interval_count"] == 2
    assert result["rejection_reasons"] == {
        "pricing_not_reliable": 1,
        "pricing_not_available": 1,
    }


def test_skips_daily_entries_without_intervals_key(coordinator):
    """A day entry from before #65 merged (or any entry missing the
    "intervals" key) must be skipped, not raise."""
    _set_service_data(
        coordinator,
        [
            {"date": "2026-07-22"},  # no "intervals" key at all
            {"date": "2026-07-23", "intervals": [_shoulder_interval()]},
        ],
        RATES,
    )
    result = coordinator.get_cl2_inference("prop-001", SERVICE_TYPE_ELECTRICITY)
    assert result["accepted_interval_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_coordinator_cl2_aggregation.py -v`
Expected: FAIL — `AttributeError: 'RedEnergyDataCoordinator' object has no attribute 'get_cl2_inference'`

- [ ] **Step 3: Implement `get_cl2_inference`**

In `custom_components/red_energy/coordinator.py`, add the import at the top of the file alongside the existing imports:

```python
from .cl2_inference import infer_cl2_interval, resolve_rate_roles
```

Add the new method to `RedEnergyDataCoordinator`, placed after `get_service_rates` (around line 605, right before `_get_latest_usage_entry`):

```python
    def get_cl2_inference(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Aggregate CL2/TOU inference across a service's usage period.

        Returns None when there's no usage data, or when the account's plan
        rates don't have an unambiguous CL2 rate (resolve_rate_roles()
        couldn't resolve "CL2") - most accounts have no controlled load, so
        this is the normal case for them, not an error.

        Uses the account's *current* plan rates for every interval in the
        period, including days earlier in the billing cycle - there is no
        historical rate-change data available anywhere in the API, so a
        mid-period rate change will skew inference for days before it. This
        is a known, documented limitation, not something this method can
        detect or correct for.
        """
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None

        daily_entries = service_data["usage_data"].get("usage_data", [])
        if not daily_entries:
            return None

        rates = self.get_service_rates(property_id, service_type)
        role_resolution = resolve_rate_roles(rates)
        if "CL2" in role_resolution["unresolved_roles"]:
            return None

        rates_incl_gst = role_resolution["rates_incl_gst"]
        cl2_rate_incl_gst = role_resolution["cl2_rate_incl_gst"]

        cl2_energy_kwh = 0.0
        corrected_peak_kwh = 0.0
        corrected_shoulder_kwh = 0.0
        corrected_offpeak_kwh = 0.0
        cl2_cost = 0.0
        reconstructed_import_cost = 0.0
        api_import_cost = 0.0
        accepted_interval_count = 0
        rejected_interval_count = 0
        rejection_reasons: dict[str, int] = {}

        for daily_entry in daily_entries:
            intervals = daily_entry.get("intervals", [])
            if not isinstance(intervals, list):
                continue

            for interval in intervals:
                result = infer_cl2_interval(interval, rates_incl_gst, cl2_rate_incl_gst)

                if not result["accepted"]:
                    rejected_interval_count += 1
                    reason = result["reason"] or "unknown"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    continue

                accepted_interval_count += 1
                cl2_energy_kwh += result["cl2_kwh"]
                cl2_cost += result["cl2_kwh"] * cl2_rate_incl_gst
                reconstructed_import_cost += result["reconstructed_cost"]
                api_import_cost += result["api_cost"]

                tariff_component = interval.get("tariff_component")
                if tariff_component == "PEAK":
                    corrected_peak_kwh += result["tou_kwh"]
                elif tariff_component == "SHOULDER":
                    corrected_shoulder_kwh += result["tou_kwh"]
                elif tariff_component == "OFFPEAK":
                    corrected_offpeak_kwh += result["tou_kwh"]

        return {
            "cl2_energy_kwh": round(cl2_energy_kwh, 3),
            "corrected_peak_kwh": round(corrected_peak_kwh, 3),
            "corrected_shoulder_kwh": round(corrected_shoulder_kwh, 3),
            "corrected_offpeak_kwh": round(corrected_offpeak_kwh, 3),
            "cl2_cost": round(cl2_cost, 2),
            "reconstructed_import_cost": round(reconstructed_import_cost, 2),
            "api_import_cost": round(api_import_cost, 2),
            "reconciliation_difference": round(reconstructed_import_cost - api_import_cost, 2),
            "accepted_interval_count": accepted_interval_count,
            "rejected_interval_count": rejected_interval_count,
            "rejection_reasons": rejection_reasons,
            "rates_used": {**rates_incl_gst, "CL2": cl2_rate_incl_gst},
            "rates_source": "current plan rates (no historical rate data available)",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_coordinator_cl2_aggregation.py -v`
Expected: PASS (6/6)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, all 252 existing tests plus 6 new ones.

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/coordinator.py tests/test_coordinator_cl2_aggregation.py
git commit -m "feat: aggregate CL2/TOU inference across a service's usage period"
```

---

### Task 2: New sensor type constants

**Files:**
- Modify: `custom_components/red_energy/const.py`

**Interfaces:**
- Consumes: nothing.
- Produces: 6 new `Final` string constants, used by Task 3's sensor classes as their `sensor_type` argument to `RedEnergyBaseSensor.__init__` (which builds `unique_id` and the default entity name from this string — see `sensor.py:225-245`).

- [ ] **Step 1: Add the constants**

In `custom_components/red_energy/const.py`, add immediately after the existing `SENSOR_TYPE_CARBON_EMISSION: Final = "carbon_emission_tonne"` line (line 60):

```python
SENSOR_TYPE_CARBON_EMISSION: Final = "carbon_emission_tonne"

# CL2 (Controlled Load 2) / TOU inference sensors - only created for
# accounts whose plan has an unambiguous CL2 rate (see issue #61)
SENSOR_TYPE_CL2_ENERGY: Final = "cl2_inferred_energy"
SENSOR_TYPE_CORRECTED_PEAK_IMPORT: Final = "corrected_peak_import"
SENSOR_TYPE_CORRECTED_SHOULDER_IMPORT: Final = "corrected_shoulder_import"
SENSOR_TYPE_CORRECTED_OFFPEAK_IMPORT: Final = "corrected_offpeak_import"
SENSOR_TYPE_CL2_COST: Final = "cl2_inferred_cost"
SENSOR_TYPE_RECONSTRUCTED_IMPORT_COST: Final = "reconstructed_import_cost"
```

(This replaces the single existing `SENSOR_TYPE_CARBON_EMISSION` line with the same line followed by the 6 new ones — the existing line is unchanged, just followed by new content.)

- [ ] **Step 2: Verify the file still imports cleanly**

Run: `.venv/bin/python -c "from custom_components.red_energy import const; print(const.SENSOR_TYPE_CL2_ENERGY)"`
Expected: prints `cl2_inferred_energy`, no error.

- [ ] **Step 3: Commit**

```bash
git add custom_components/red_energy/const.py
git commit -m "feat: add sensor type constants for CL2/TOU derived sensors"
```

---

### Task 3: Derived sensor classes

**Files:**
- Modify: `custom_components/red_energy/sensor.py`
- Test: `tests/test_sensor_cl2.py` (new file)

**Interfaces:**
- Consumes: `coordinator.get_cl2_inference(property_id, service_type) -> dict[str, Any] | None` (Task 1), the 6 constants from Task 2, and the existing `RedEnergyBaseSensor` base class / `_electricity_only` flag / `RedEnergyCarbonEmissionSensor` pattern already in `sensor.py`.
- Produces: 6 new sensor classes — `RedEnergyCl2EnergySensor`, `RedEnergyCorrectedPeakImportSensor`, `RedEnergyCorrectedShoulderImportSensor`, `RedEnergyCorrectedOffpeakImportSensor`, `RedEnergyCl2CostSensor`, `RedEnergyReconstructedImportCostSensor` — for Task 4 (the `async_setup_entry` wiring) to instantiate.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sensor_cl2.py`:

```python
"""Tests for the CL2/TOU derived sensors (issue #61)."""
from unittest.mock import MagicMock

import pytest

from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import (
    RedEnergyCl2CostSensor,
    RedEnergyCl2EnergySensor,
    RedEnergyCorrectedOffpeakImportSensor,
    RedEnergyCorrectedPeakImportSensor,
    RedEnergyCorrectedShoulderImportSensor,
    RedEnergyReconstructedImportCostSensor,
)

CL2_DATA = {
    "cl2_energy_kwh": 15.35,
    "corrected_peak_kwh": 3.2,
    "corrected_shoulder_kwh": 0.374,
    "corrected_offpeak_kwh": 1.1,
    "cl2_cost": 2.83,
    "reconstructed_import_cost": 19.09,
    "api_import_cost": 19.10,
    "reconciliation_difference": -0.01,
    "accepted_interval_count": 47,
    "rejected_interval_count": 1,
    "rejection_reasons": {"pricing_not_reliable": 1},
    "rates_used": {"PEAK": 0.4576, "SHOULDER": 0.41745, "OFFPEAK": 0.32483, "CL2": 0.18425},
    "rates_source": "current plan rates (no historical rate data available)",
}


def _coordinator(cl2_data=CL2_DATA):
    coordinator = MagicMock()
    coordinator.get_cl2_inference = MagicMock(return_value=cl2_data)
    return coordinator


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


@pytest.mark.parametrize(
    "sensor_cls,value_key",
    [
        (RedEnergyCl2EnergySensor, "cl2_energy_kwh"),
        (RedEnergyCorrectedPeakImportSensor, "corrected_peak_kwh"),
        (RedEnergyCorrectedShoulderImportSensor, "corrected_shoulder_kwh"),
        (RedEnergyCorrectedOffpeakImportSensor, "corrected_offpeak_kwh"),
        (RedEnergyCl2CostSensor, "cl2_cost"),
        (RedEnergyReconstructedImportCostSensor, "reconstructed_import_cost"),
    ],
)
def test_native_value_reads_from_coordinator(sensor_cls, value_key):
    coordinator = _coordinator()
    sensor = sensor_cls(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor.native_value == CL2_DATA[value_key]


@pytest.mark.parametrize(
    "sensor_cls",
    [
        RedEnergyCl2EnergySensor,
        RedEnergyCorrectedPeakImportSensor,
        RedEnergyCorrectedShoulderImportSensor,
        RedEnergyCorrectedOffpeakImportSensor,
        RedEnergyCl2CostSensor,
        RedEnergyReconstructedImportCostSensor,
    ],
)
def test_native_value_none_when_coordinator_returns_none(sensor_cls):
    coordinator = _coordinator(cl2_data=None)
    sensor = sensor_cls(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor.native_value is None


@pytest.mark.parametrize(
    "sensor_cls",
    [
        RedEnergyCl2EnergySensor,
        RedEnergyCorrectedPeakImportSensor,
        RedEnergyCorrectedShoulderImportSensor,
        RedEnergyCorrectedOffpeakImportSensor,
        RedEnergyCl2CostSensor,
        RedEnergyReconstructedImportCostSensor,
    ],
)
def test_all_cl2_sensors_are_electricity_only(sensor_cls):
    coordinator = _coordinator()
    sensor = sensor_cls(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor._electricity_only is True


def test_cl2_energy_sensor_exposes_diagnostic_attributes():
    coordinator = _coordinator()
    sensor = RedEnergyCl2EnergySensor(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    attrs = sensor.extra_state_attributes

    assert attrs["accepted_interval_count"] == 47
    assert attrs["rejected_interval_count"] == 1
    assert attrs["rejection_reasons"] == {"pricing_not_reliable": 1}
    assert attrs["rates_used"] == CL2_DATA["rates_used"]
    assert attrs["rates_source"] == "current plan rates (no historical rate data available)"


def test_reconstructed_import_cost_sensor_exposes_reconciliation_difference():
    coordinator = _coordinator()
    sensor = RedEnergyReconstructedImportCostSensor(
        coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY
    )
    attrs = sensor.extra_state_attributes

    assert attrs["reconciliation_difference"] == -0.01
    assert attrs["api_import_cost"] == 19.10


def test_diagnostic_attributes_none_when_coordinator_returns_none():
    coordinator = _coordinator(cl2_data=None)
    sensor = RedEnergyCl2EnergySensor(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor.extra_state_attributes is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sensor_cl2.py -v`
Expected: FAIL — `ImportError: cannot import name 'RedEnergyCl2EnergySensor'`

- [ ] **Step 3: Implement the 6 sensor classes**

In `custom_components/red_energy/sensor.py`, add the import for the new constants alongside the existing sensor-type imports near the top of the file (find the existing `from .const import (` block and add these 6 names to it):

```python
    SENSOR_TYPE_CL2_ENERGY,
    SENSOR_TYPE_CORRECTED_PEAK_IMPORT,
    SENSOR_TYPE_CORRECTED_SHOULDER_IMPORT,
    SENSOR_TYPE_CORRECTED_OFFPEAK_IMPORT,
    SENSOR_TYPE_CL2_COST,
    SENSOR_TYPE_RECONSTRUCTED_IMPORT_COST,
```

Add the 6 new sensor classes at the end of `sensor.py`, after the existing `RedEnergyCarbonEmissionSensor` class (and its `extra_state_attributes` method):

```python
class RedEnergyCl2EnergySensor(RedEnergyBaseSensor):
    """Red Energy inferred CL2 (Controlled Load 2) energy sensor.

    Only created for accounts whose plan has an unambiguous CL2 rate (see
    coordinator.get_cl2_inference() and cl2_inference.resolve_rate_roles()).
    Inference uses the account's current plan rates for the whole period -
    see rates_source in extra_state_attributes for that caveat.
    """

    _electricity_only = True

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the CL2 energy sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_CL2_ENERGY)

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = "mdi:water-boiler"

    @property
    def native_value(self) -> float | None:
        """Return the inferred CL2 energy for the period."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        return data.get("cl2_energy_kwh") if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return diagnostic attributes describing inference quality."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        if not data:
            return None

        return {
            "accepted_interval_count": data.get("accepted_interval_count"),
            "rejected_interval_count": data.get("rejected_interval_count"),
            "rejection_reasons": data.get("rejection_reasons"),
            "rates_used": data.get("rates_used"),
            "rates_source": data.get("rates_source"),
            "description": "Inferred controlled-load energy, algebraically separated from blended TOU+CL2 interval data",
        }


class RedEnergyCorrectedPeakImportSensor(RedEnergyBaseSensor):
    """Red Energy corrected Peak import sensor (CL2 energy excluded)."""

    _electricity_only = True

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the corrected Peak import sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_CORRECTED_PEAK_IMPORT)

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def native_value(self) -> float | None:
        """Return corrected Peak import energy with CL2 removed."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        return data.get("corrected_peak_kwh") if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return diagnostic attributes describing inference quality."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        if not data:
            return None

        return {
            "accepted_interval_count": data.get("accepted_interval_count"),
            "rejected_interval_count": data.get("rejected_interval_count"),
            "rates_source": data.get("rates_source"),
            "description": "Peak-period grid import with inferred CL2 energy excluded",
        }


class RedEnergyCorrectedShoulderImportSensor(RedEnergyBaseSensor):
    """Red Energy corrected Shoulder import sensor (CL2 energy excluded)."""

    _electricity_only = True

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the corrected Shoulder import sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_CORRECTED_SHOULDER_IMPORT)

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def native_value(self) -> float | None:
        """Return corrected Shoulder import energy with CL2 removed."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        return data.get("corrected_shoulder_kwh") if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return diagnostic attributes describing inference quality."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        if not data:
            return None

        return {
            "accepted_interval_count": data.get("accepted_interval_count"),
            "rejected_interval_count": data.get("rejected_interval_count"),
            "rates_source": data.get("rates_source"),
            "description": "Shoulder-period grid import with inferred CL2 energy excluded",
        }


class RedEnergyCorrectedOffpeakImportSensor(RedEnergyBaseSensor):
    """Red Energy corrected Off-peak import sensor (CL2 energy excluded)."""

    _electricity_only = True

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the corrected Off-peak import sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_CORRECTED_OFFPEAK_IMPORT)

        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def native_value(self) -> float | None:
        """Return corrected Off-peak import energy with CL2 removed."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        return data.get("corrected_offpeak_kwh") if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return diagnostic attributes describing inference quality."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        if not data:
            return None

        return {
            "accepted_interval_count": data.get("accepted_interval_count"),
            "rejected_interval_count": data.get("rejected_interval_count"),
            "rates_source": data.get("rates_source"),
            "description": "Off-peak-period grid import with inferred CL2 energy excluded",
        }


class RedEnergyCl2CostSensor(RedEnergyBaseSensor):
    """Red Energy inferred CL2 cost sensor."""

    _electricity_only = True

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the CL2 cost sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_CL2_COST)

        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_icon = "mdi:water-boiler"

    @property
    def native_value(self) -> float | None:
        """Return the inferred CL2 cost for the period."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        return data.get("cl2_cost") if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return diagnostic attributes describing inference quality."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        if not data:
            return None

        return {
            "gst_inclusive": True,
            "rates_used": data.get("rates_used"),
            "rates_source": data.get("rates_source"),
            "description": "Inferred cost of controlled-load energy within the blended interval cost",
        }


class RedEnergyReconstructedImportCostSensor(RedEnergyBaseSensor):
    """Red Energy reconstructed import cost sensor (TOU + CL2 portions summed from inference)."""

    _electricity_only = True

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the reconstructed import cost sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_RECONSTRUCTED_IMPORT_COST)

        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"

    @property
    def native_value(self) -> float | None:
        """Return the reconstructed import cost for the period."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        return data.get("reconstructed_import_cost") if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return diagnostic attributes describing reconciliation against the API's own cost."""
        data = self.coordinator.get_cl2_inference(self._property_id, self._service_type)
        if not data:
            return None

        return {
            "gst_inclusive": True,
            "api_import_cost": data.get("api_import_cost"),
            "reconciliation_difference": data.get("reconciliation_difference"),
            "accepted_interval_count": data.get("accepted_interval_count"),
            "rejected_interval_count": data.get("rejected_interval_count"),
            "rates_source": data.get("rates_source"),
            "description": "Import cost reconstructed from inferred TOU and CL2 components, for comparison against the API's own daily cost",
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sensor_cl2.py -v`
Expected: PASS (all tests: 6 native-value tests + 6 none-when-no-data tests + 6 electricity-only tests + 3 attribute tests = 21)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, all prior tests plus the new ones from Tasks 1 and 3.

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/sensor.py tests/test_sensor_cl2.py
git commit -m "feat: add CL2/TOU derived sensor classes"
```

---

### Task 4: Wire sensors into `async_setup_entry`

**Files:**
- Modify: `custom_components/red_energy/sensor.py`
- Test: `tests/test_sensor_cl2_setup.py` (new file)

**Interfaces:**
- Consumes: `coordinator.get_service_rates(property_id, service_type)` (existing), `resolve_rate_roles()` (from `cl2_inference.py`, merged in #65), the 6 sensor classes from Task 3, and the existing `async_setup_entry` function body (lines 57-206 of `sensor.py` as of this plan's writing).
- Produces: the 6 new sensors appear in the entity list built by `async_setup_entry`, but only for electricity services on accounts where `resolve_rate_roles(coordinator.get_service_rates(account_id, service_type))` does not have `"CL2"` in `unresolved_roles`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sensor_cl2_setup.py`:

```python
"""Tests for CL2/TOU derived sensor creation gating in async_setup_entry."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.red_energy.const import DOMAIN, CONF_ENABLE_ADVANCED_SENSORS
from custom_components.red_energy.sensor import async_setup_entry, RedEnergyCl2EnergySensor

RATES_WITH_CL2 = [
    {"rate_code": "P1", "rate_desc": "Peak", "rate_incl_gst_dollars": 0.4576},
    {"rate_code": "S1", "rate_desc": "Shoulder", "rate_incl_gst_dollars": 0.41745},
    {"rate_code": "O1", "rate_desc": "Off-peak", "rate_incl_gst_dollars": 0.32483},
    {"rate_code": "C1", "rate_desc": "CL2", "rate_incl_gst_dollars": 0.18425},
]

RATES_WITHOUT_CL2 = [
    {"rate_code": "P1", "rate_desc": "Peak", "rate_incl_gst_dollars": 0.4576},
]


def _make_coordinator(rates):
    coordinator = MagicMock()
    coordinator.get_service_metadata = MagicMock(
        return_value={"meterType": "SMART", "rates": rates}
    )
    coordinator.get_service_rates = MagicMock(return_value=rates)
    coordinator.last_update_success = True
    coordinator.data = {"usage_data": {"prop-001": {}}}
    return coordinator


def _make_config_entry(advanced_enabled=True):
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {CONF_ENABLE_ADVANCED_SENSORS: advanced_enabled}
    return entry


def _make_hass(coordinator, config_entry):
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            config_entry.entry_id: {
                "coordinator": coordinator,
                "selected_accounts": ["prop-001"],
                "services": ["electricity"],
            }
        }
    }
    return hass


@pytest.mark.asyncio
async def test_cl2_sensors_created_when_cl2_rate_resolves():
    coordinator = _make_coordinator(RATES_WITH_CL2)
    config_entry = _make_config_entry(advanced_enabled=True)
    hass = _make_hass(coordinator, config_entry)

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    cl2_energy_sensors = [e for e in added_entities if isinstance(e, RedEnergyCl2EnergySensor)]
    assert len(cl2_energy_sensors) == 1


@pytest.mark.asyncio
async def test_cl2_sensors_not_created_when_no_cl2_rate():
    coordinator = _make_coordinator(RATES_WITHOUT_CL2)
    config_entry = _make_config_entry(advanced_enabled=True)
    hass = _make_hass(coordinator, config_entry)

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    cl2_energy_sensors = [e for e in added_entities if isinstance(e, RedEnergyCl2EnergySensor)]
    assert len(cl2_energy_sensors) == 0


@pytest.mark.asyncio
async def test_cl2_sensors_not_created_when_advanced_sensors_disabled():
    coordinator = _make_coordinator(RATES_WITH_CL2)
    config_entry = _make_config_entry(advanced_enabled=False)
    hass = _make_hass(coordinator, config_entry)

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    cl2_energy_sensors = [e for e in added_entities if isinstance(e, RedEnergyCl2EnergySensor)]
    assert len(cl2_energy_sensors) == 0
```

This mock shape (`get_service_metadata`/`get_service_rates` as flat `MagicMock(return_value=...)`, `hass.data`/`async_add_entities` capturing the added entities list) has been verified directly against the real `async_setup_entry` — it correctly creates `RedEnergyCarbonEmissionSensor` (an existing advanced sensor) under the same mock setup, confirming the fixture is compatible with the function's actual code path, not just a guess at its shape.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_sensor_cl2_setup.py -v`
Expected: FAIL — `AssertionError: assert 0 == 1` on `test_cl2_sensors_created_when_cl2_rate_resolves` (no CL2 sensors created yet since `async_setup_entry` doesn't know about them).

- [ ] **Step 3: Wire the sensors into `async_setup_entry`**

In `custom_components/red_energy/sensor.py`, add the import for `resolve_rate_roles` and the 6 new sensor classes near the top of the file (add to existing import blocks rather than creating new ones):

```python
from .cl2_inference import resolve_rate_roles
```

Inside `async_setup_entry`, within the `for service_type in services:` loop, after the existing advanced-sensors block (the `if advanced_sensors_enabled:` block ending around line 155) and before the `if is_basic_meter:` block, add:

```python
            # CL2/TOU derived sensors - only for accounts whose plan has an
            # unambiguous CL2 rate (see cl2_inference.resolve_rate_roles).
            # Gated on advanced_sensors_enabled like the other advanced
            # sensors above, since this is a niche, account-specific feature.
            if advanced_sensors_enabled and service_type == SERVICE_TYPE_ELECTRICITY:
                role_resolution = resolve_rate_roles(coordinator.get_service_rates(account_id, service_type))
                if "CL2" not in role_resolution["unresolved_roles"]:
                    service_entities.extend([
                        RedEnergyCl2EnergySensor(coordinator, config_entry, account_id, service_type),
                        RedEnergyCorrectedPeakImportSensor(coordinator, config_entry, account_id, service_type),
                        RedEnergyCorrectedShoulderImportSensor(coordinator, config_entry, account_id, service_type),
                        RedEnergyCorrectedOffpeakImportSensor(coordinator, config_entry, account_id, service_type),
                        RedEnergyCl2CostSensor(coordinator, config_entry, account_id, service_type),
                        RedEnergyReconstructedImportCostSensor(coordinator, config_entry, account_id, service_type),
                    ])
```

Note: this block is placed after the existing gas/electricity-only filtering setup but the `_electricity_only = True` flag on all 6 classes means the later `if service_type != SERVICE_TYPE_ELECTRICITY:` filter (existing code, around line 165) would strip them anyway even without the explicit `service_type == SERVICE_TYPE_ELECTRICITY` guard here — the explicit guard is kept for clarity and to avoid calling `resolve_rate_roles` needlessly for gas services, not because the electricity-only filter is insufficient on its own.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sensor_cl2_setup.py -v`
Expected: PASS (3/3)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, all prior tests (Tasks 1-3) plus the new 3 from this task, with zero regressions to the pre-existing suite.

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/sensor.py tests/test_sensor_cl2_setup.py
git commit -m "feat: wire CL2/TOU sensors into entity setup, gated on resolved CL2 rate"
```

---

## What This Plan Does Not Cover (deliberately)

- **Historical tariff versioning** — explicitly out of scope per the Global Constraints section above. Inference always uses current plan rates; the `rates_source` attribute documents this rather than pretending it's solved.
- **Backdating Energy Dashboard statistics** to `usageDate`/`intervalStart` — tracked separately in issue #64, unrelated to this plan's scope.
- **Config-flow/options-flow changes** — no new user-facing setup steps are added; CL2 sensor creation is fully automatic based on whether the account's plan rates resolve a CL2 role.
- **Validating inference accuracy against @LoznOz's real account data** — this plan implements the engine and sensors faithfully per the merged `cl2_inference.py` module (already validated against real data in #65's plan), but does not itself re-run that validation. Once merged, the natural next step is asking @LoznOz (or another CL2 customer) to test against their live account and report back on issue #61.
