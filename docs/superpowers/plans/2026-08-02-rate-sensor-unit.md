# Rate Sensor Unit Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `RedEnergyRateSensor`'s unit of measurement from the currency-only `"AUD"` to a rate-denominated unit (`"AUD/kWh"` for electricity, `"AUD/MJ"` for gas), and its state class from unset to `MEASUREMENT`, since Home Assistant's `monetary` device class requires an ISO 4217 currency-code-only unit and cannot represent a rate — the two are mutually exclusive, so `device_class: monetary` must be removed from this sensor.

**Architecture:** A single-file, single-class change to `RedEnergyRateSensor` in `sensor.py`: drop `_attr_device_class`, branch `_attr_native_unit_of_measurement` on `service_type` (electricity → `"AUD/kWh"`, gas → `"AUD/MJ"`), and add `_attr_state_class = SensorStateClass.MEASUREMENT`. No other sensor, coordinator method, or API field changes. The sensor's numeric value (`native_value`, reading `rate_incl_gst_dollars`) is unchanged — this plan changes presentation only, per the request.

**Tech Stack:** Python 3.13/3.14, pytest, Home Assistant custom integration conventions.

## Global Constraints

- Do not change `native_value`'s logic or the value it returns — only `_attr_device_class`, `_attr_native_unit_of_measurement`, and `_attr_state_class` on `RedEnergyRateSensor`.
- Do not touch any other sensor class, `coordinator.py`, `api.py`, or `data_validation.py`.
- This is a breaking change for existing installations: any dashboard card, automation, or Energy Dashboard cost-tracking configuration referencing these entities by their old `monetary` device class or `AUD` unit will need reconfiguring after upgrade (removing `device_class: monetary` changes how the entity is categorized and displayed in the UI, and HA's Recorder may treat the unit change as requiring statistics reset for this entity — this is expected and out of scope to mitigate, since the user explicitly requested this change knowing it affects only rate sensors, not usage/cost totals).
- Because `RedEnergyRateSensor` no longer has a `device_class`, `unit_of_measurement` becomes a free-form string with no HA-enforced validation — `"AUD/kWh"` and `"AUD/MJ"` are plain strings, not any built-in `UnitOf*` constant (there is no such constant for a compound currency-per-energy unit in Home Assistant's unit system).
- Follow existing codebase conventions: `if service_type == SERVICE_TYPE_ELECTRICITY: ... elif service_type == SERVICE_TYPE_GAS: ...` branching, matching the pattern already used in `RedEnergyDailyImportUsageSensor` and other dual-service sensors in this file.
- Manifest version bump: this is a `fix`/breaking presentation change to an existing sensor, not a new feature — bump PATCH per this repo's semantic versioning convention if the branch doesn't already carry a MINOR/MAJOR bump for unrelated reasons. Check `custom_components/red_energy/manifest.json`'s current version at branch-creation time and bump accordingly (this plan does not hardcode the resulting version number since it depends on what's already on `main` when the branch is cut).
- `flake8 custom_components --count --select=E9,F63,F7,F82` and `mypy custom_components/red_energy --ignore-missing-imports` should stay clean but are not installed in this dev environment (confirmed pre-existing gap across the whole repo; both are `continue-on-error: true` in CI). Do not treat their absence as a new issue.

---

### Task 1: Change rate sensor unit, device class, and state class

**Files:**
- Modify: `custom_components/red_energy/sensor.py` (the `RedEnergyRateSensor` class, currently at line 797)
- Modify: `tests/test_sensor_rates.py`

**Interfaces:**
- Consumes: `service_type: str` (already passed into `RedEnergyRateSensor.__init__` — no interface change, this task only changes what the constructor does with the value it already has), `SERVICE_TYPE_ELECTRICITY`/`SERVICE_TYPE_GAS` (already imported in `sensor.py`).
- Produces: no new public interface. `RedEnergyRateSensor` instances now have `_attr_device_class = None` (unset), `_attr_native_unit_of_measurement = "AUD/kWh"` for electricity services or `"AUD/MJ"` for gas services, and `_attr_state_class = SensorStateClass.MEASUREMENT`.

- [ ] **Step 1: Update the failing test for the changed device class/unit/state class**

In `tests/test_sensor_rates.py`, replace the existing `test_rate_sensor_native_value_and_attributes` test (lines 181-199) with:

```python
def test_rate_sensor_native_value_and_attributes():
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyRateSensor(
        coordinator, config_entry, "2000002", SERVICE_TYPE_ELECTRICITY, ELECTRICITY_RATES[0]
    )

    assert sensor.native_value == pytest.approx(0.27005)
    assert sensor._attr_name == "Rate Peak"
    assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.device_class is None
    assert sensor.native_unit_of_measurement == "AUD/kWh"
    assert sensor.state_class == SensorStateClass.MEASUREMENT

    attrs = sensor.extra_state_attributes
    assert attrs["rate_code"] == "80008279798P"
    assert attrs["type"] == "PR"
    assert attrs["unit"] == "kWh"
    assert "rate_incl_gst_dollars" not in attrs
```

Note: assert against the public `device_class`/`native_unit_of_measurement`/`state_class` properties, not the private `_attr_device_class`/etc. fields directly. `SensorEntity`'s `_attr_*` names are backed by descriptors in this HA version, and accessing `_attr_device_class` directly raises `AttributeError` when it was never assigned in `__init__` (as is the case here now that `device_class` is removed) rather than returning `None` - the public property is the documented, stable way to read a sensor's effective value and correctly returns `None` for an unset device_class.

Then add a new test immediately after it, for the gas case:

```python
def test_rate_sensor_gas_unit_is_aud_per_mj():
    coordinator = _coordinator(GAS_SERVICE_METADATA, SERVICE_TYPE_GAS)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyRateSensor(
        coordinator, config_entry, "2000002", SERVICE_TYPE_GAS, GAS_TIERED_RATES[0]
    )

    assert sensor.device_class is None
    assert sensor.native_unit_of_measurement == "AUD/MJ"
    assert sensor.state_class == SensorStateClass.MEASUREMENT
```

Add `SensorStateClass` to the existing import block at the top of `tests/test_sensor_rates.py`. The file currently imports:

```python
from homeassistant.helpers.entity import EntityCategory
```

Change this to:

```python
from homeassistant.components.sensor import SensorStateClass
from homeassistant.helpers.entity import EntityCategory
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sensor_rates.py -v`
Expected: FAIL on `test_rate_sensor_native_value_and_attributes` (`assert sensor.device_class is None` fails, since it's currently `SensorDeviceClass.MONETARY`) and `test_rate_sensor_gas_unit_is_aud_per_mj` (unit mismatch: currently `"AUD"`, not `"AUD/MJ"`).

- [ ] **Step 3: Implement the sensor change**

In `custom_components/red_energy/sensor.py`, in `RedEnergyRateSensor.__init__` (starts at line 808), replace:

```python
        self._attr_name = f"Rate {self._rate_desc}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_icon = "mdi:currency-usd"
```

with:

```python
        self._attr_name = f"Rate {self._rate_desc}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:currency-usd"
        self._attr_state_class = SensorStateClass.MEASUREMENT

        # Home Assistant's monetary device class requires an ISO 4217
        # currency-code-only unit (e.g. "AUD") and cannot represent a rate
        # like "AUD/kWh" - the two are mutually exclusive, so this sensor
        # has no device_class and uses a plain custom unit string instead.
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_native_unit_of_measurement = "AUD/kWh"
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_native_unit_of_measurement = "AUD/MJ"
```

Note: `RedEnergyRateSensor.__init__` already receives `service_type` as a parameter (it's passed to `super().__init__(...)` on the line just above this block) - no signature change needed, just use the existing local variable.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sensor_rates.py -v`
Expected: PASS (all tests in the file, including the 2 touched/added in this task).

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, all existing tests plus the new one, with zero regressions. No other test file references `RedEnergyRateSensor`'s device class or unit (confirmed by grepping the test suite before writing this plan - only `tests/test_sensor_rates.py` asserts on these fields), so no other test file should need changes.

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/sensor.py tests/test_sensor_rates.py
git commit -m "fix: use rate-denominated unit for tariff rate sensors

Home Assistant's monetary device class requires an ISO 4217
currency-code-only unit and cannot represent a rate like AUD/kWh -
rate sensors now use device_class-less MEASUREMENT sensors with
AUD/kWh (electricity) or AUD/MJ (gas) units instead."
```

---

## What This Plan Does Not Cover (deliberately)

- **GST-inclusive vs. exclusive display basis** (the other half of issue #67's request) — this plan only changes the unit/device_class/state_class presentation, not which underlying value (`rate_incl_gst_dollars` vs. an ex-GST equivalent) is reported. That's a separate, larger change (needs a new options-flow setting or additional sensors, per the issue's own "don't change existing state" caveat) and is out of scope here.
- **Demand charge sensors, GreenPower distinguishing "available" vs. "billed", or any other sensor type mentioned in issue #67** — this plan is scoped narrowly to `RedEnergyRateSensor`'s unit/device_class, per the explicit instruction given for this plan.
- **Any Energy Dashboard or Recorder migration for the unit change** — HA's Recorder may need to reset statistics for these entities after the unit changes (going from a `monetary`-device-classed entity to a plain `MEASUREMENT` one is a meaningful reclassification). This plan does not add migration code for that; it's flagged as an expected consequence in the Global Constraints, not solved.
