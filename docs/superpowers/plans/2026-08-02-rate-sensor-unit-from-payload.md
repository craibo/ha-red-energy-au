# Rate Sensor Unit From Payload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `RedEnergyRateSensor`'s unit of measurement to be derived from each rate's own `unit` field in the API payload, instead of being hardcoded by `service_type`. The prior fix (PR #68, v1.16.1) hardcoded `AUD/kWh` for every electricity rate and `AUD/MJ` for every gas rate — incorrect for non-energy rates on the same service, such as a daily supply/service charge (denominated per day, not per kWh/MJ).

**Architecture:** Single change to `RedEnergyRateSensor.__init__` in `sensor.py`: replace the `service_type`-based branch with a lookup at the rate's own `unit` field (already present in the `rate: dict[str, Any]` parameter already passed into `__init__`, already validated and passed straight through by `validate_rates()` in `data_validation.py`). The currency is always `AUD` per this integration's Australian retailer scope, so the compound unit is always `f"AUD/{rate_unit}"` when `rate_unit` is present, falling back to plain `"AUD"` when the API didn't supply a `unit` for that rate (this is a defensive fallback for an already-possible `None` case in the existing validated data model — `validate_rates()` never defaults this field, so a real payload can genuinely omit it).

**Tech Stack:** Python 3.13/3.14, pytest, Home Assistant custom integration conventions.

## Global Constraints

- Use the rate's `unit` field **verbatim** — no casing normalization, no string transformation. If the API returns `"kWh"`, the sensor unit is `"AUD/kWh"`; if the API returns `"day"`, it's `"AUD/day"`. Do not lowercase, titlecase, or otherwise rewrite the string.
- Do not change `native_value`'s logic or the value it returns — this plan only changes `_attr_native_unit_of_measurement`.
- Do not touch `_attr_device_class` (already removed in #68) or `_attr_state_class` (already `MEASUREMENT` since #68) — those are correct as-is.
- Do not touch any other sensor class, `coordinator.py`, `api.py`, or `data_validation.py`. The `unit` field is already validated and present on every rate dict; this plan only changes how `sensor.py` reads it.
- Follow existing codebase conventions: plain dict access via `.get()`, matching how `_find_rate()` and other rate-field reads already work in this class.
- Because `unit` can be missing (per `data_validation.py`'s `validate_rates()`, which never applies a default to this field), the sensor must not construct an incorrect unit string like `"AUD/None"` when it's absent — fall back to plain `"AUD"` in that case.
- This is a `fix` correcting a regression from PR #68 (v1.16.1) — bump PATCH per this repo's semantic versioning convention. Check `custom_components/red_energy/manifest.json`'s current version at branch-creation time and bump accordingly (this plan does not hardcode the resulting version number since it depends on what's on `main` when the branch is cut).
- `flake8 custom_components --count --select=E9,F63,F7,F82` and `mypy custom_components/red_energy --ignore-missing-imports` should stay clean but are not installed in this dev environment (confirmed pre-existing gap across the whole repo; both `continue-on-error: true` in CI). Do not treat their absence as a new issue.

---

### Task 1: Derive rate sensor unit from the rate's own `unit` field

**Files:**
- Modify: `custom_components/red_energy/sensor.py` (the `RedEnergyRateSensor` class, currently at line 797)
- Modify: `tests/test_sensor_rates.py`

**Interfaces:**
- Consumes: `rate: dict[str, Any]` (already a parameter of `RedEnergyRateSensor.__init__` — the `unit` key on it, already validated and passed through unchanged by `data_validation.py`'s `validate_rates()`, e.g. `rate.get("unit")` returning `"kWh"`, `"MJ"`, `"day"`, or `None`).
- Produces: no new public interface. `_attr_native_unit_of_measurement` is now `f"AUD/{rate['unit']}"` when `rate['unit']` is truthy, else plain `"AUD"`.

- [ ] **Step 1: Update the existing tests and add new ones for the payload-driven unit**

In `tests/test_sensor_rates.py`, the existing `ELECTRICITY_RATES` fixture (lines 16-39) already has `"unit": "kWh"` on both entries, and `GAS_TIERED_RATES` (lines 42-65) already has `"unit": "MJ"` on both — these don't need to change, since the new logic reading `rate["unit"]` produces the same result for them as the old `service_type`-based logic did (`kWh`→`AUD/kWh`, `MJ`→`AUD/MJ`). Add a new fixture for a supply/service-charge-style rate, with a `"day"` unit, immediately after the existing `GAS_TIERED_RATES` list (after line 65):

```python
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

RATE_WITH_MISSING_UNIT = {
    "rate_code": "80008279798X",
    "rate_desc": "Unknown Unit Rate",
    "rate_incl_gst_dollars": 0.1,
    "type": "PR",
    "rate_excl_gst_cents": 9.09,
    "discounted_rate_excl_gst_in_cents": 9.09,
    "discounted_rate_incl_gst_in_cents": 10.0,
    "unit": None,
    "unit_step_desc": None,
}
```

Then find the existing `test_rate_sensor_native_value_and_attributes` test (added in #68, asserts `sensor.native_unit_of_measurement == "AUD/kWh"` for the Peak rate) and the `test_rate_sensor_gas_unit_is_aud_per_mj` test (asserts `"AUD/MJ"` for a gas rate) — leave both exactly as they are; they should still pass unmodified since Peak's `unit` is `"kWh"` and the gas rate's `unit` is `"MJ"`, matching the new payload-driven logic's output for those inputs.

Add two new tests immediately after `test_rate_sensor_gas_unit_is_aud_per_mj`:

```python
def test_rate_sensor_supply_charge_unit_is_aud_per_day():
    """A rate whose unit is "day" (e.g. a daily supply/service charge) must
    get "AUD/day", not the service-type-based AUD/kWh or AUD/MJ that a
    prior fix incorrectly hardcoded for every rate on the service."""
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyRateSensor(
        coordinator, config_entry, "2000002", SERVICE_TYPE_ELECTRICITY, SUPPLY_CHARGE_RATE
    )

    assert sensor.native_unit_of_measurement == "AUD/day"


def test_rate_sensor_falls_back_to_plain_aud_when_unit_missing():
    """A rate with no unit field (validate_rates() never defaults this
    field, so a real payload can omit it) must fall back to plain "AUD"
    rather than constructing "AUD/None"."""
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyRateSensor(
        coordinator, config_entry, "2000002", SERVICE_TYPE_ELECTRICITY, RATE_WITH_MISSING_UNIT
    )

    assert sensor.native_unit_of_measurement == "AUD"
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `.venv/bin/python -m pytest tests/test_sensor_rates.py -v`
Expected: `test_rate_sensor_supply_charge_unit_is_aud_per_day` FAILS (`AUD/kWh` != `AUD/day`, since the current code hardcodes electricity rates to `kWh` regardless of the rate's own unit) and `test_rate_sensor_falls_back_to_plain_aud_when_unit_missing` FAILS the same way (`AUD/kWh` != `AUD`). The two pre-existing tests (`test_rate_sensor_native_value_and_attributes`, `test_rate_sensor_gas_unit_is_aud_per_mj`) continue to PASS, since their fixtures' `unit` values happen to match what the old service_type-based logic already produced.

- [ ] **Step 3: Implement the fix**

In `custom_components/red_energy/sensor.py`, in `RedEnergyRateSensor.__init__`, replace:

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
        # The denominator comes from the rate's own "unit" field (kWh, MJ,
        # day, etc. - service_type alone doesn't distinguish an energy
        # rate from a per-day supply/service charge on the same service),
        # used verbatim since it's already the exact string the retailer's
        # own payload uses. The currency is always AUD for this integration.
        rate_unit = rate.get("unit")
        if rate_unit:
            self._attr_native_unit_of_measurement = f"AUD/{rate_unit}"
        else:
            self._attr_native_unit_of_measurement = "AUD"
```

Note: `service_type` is no longer read in this block, but remains a required constructor parameter used earlier in `__init__` (passed to `super().__init__(...)`) and by `_find_rate()`/`native_value` elsewhere in the class — do not remove it from the signature.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sensor_rates.py -v`
Expected: PASS (all tests in the file, including the 2 new ones and the 2 pre-existing unit tests from #68).

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, all existing tests plus the 2 new ones, zero regressions. No other test file references `RedEnergyRateSensor`'s unit (confirmed by grep before writing this plan - only `tests/test_sensor_rates.py` asserts on it).

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/sensor.py tests/test_sensor_rates.py
git commit -m "fix: derive rate sensor unit from the rate's own unit field

The previous fix (#68) hardcoded AUD/kWh for every electricity rate
and AUD/MJ for every gas rate, which is wrong for non-energy rates on
the same service - e.g. a daily supply/service charge is AUD/day, not
AUD/kWh. The unit now comes from each rate's own unit field in the
API payload, used verbatim, falling back to plain AUD when a rate has
no unit."
```

---

## What This Plan Does Not Cover (deliberately)

- **GST-inclusive vs. exclusive display basis** (the other half of issue #67's request) — unchanged from the prior plan's scope note; still out of scope here.
- **Casing/string normalization of the `unit` field** — per explicit instruction, the API's `unit` string is used exactly as returned, not normalized.
- **Demand charge units (`AUD/kW`, `AUD/kVA`, etc.)** — if the API's `unit` field for a demand-tariff rate is itself something like `"kW"`, this plan's fix already produces the correct `"AUD/kW"` automatically (same mechanism, no special-casing needed) - but this plan does not add a dedicated test fixture/verification for that specific rate type, since no real payload sample for a demand-tariff rate exists in this repo's test fixtures to base one on.
