# Daily & Billing Period Service Charge Sensors (Issue #71)

## Problem

The integration exposes electricity/gas usage costs and export credits, and already exposes the account's daily service/supply rate as a diagnostic `RedEnergyRateSensor` (`AUD/day`). It does not expose the actual dollar service-charge amount for a completed day, or accumulated over the current billing period, so users can't reconcile `usage cost + service charge - export credit` against a Red Energy bill without manually multiplying the rate by the correct day count themselves.

## Goals

- Add a **Daily Service Charge** sensor: the service charge for the latest completed `usageDate` (i.e. the daily SC rate, expressed as a monetary amount for exactly one day).
- Add a **Billing Period Service Charge** sensor: the accumulated service charge from the start of the current billing period through the latest completed `usageDate`, inclusive.
- Reuse existing billing-period-start logic (`lastBillDate + 1`, with 30-day fallback) so day counts stay consistent with the rest of the integration's billing-period sensors.
- Fail closed (report unavailable) whenever required inputs are missing, rather than guessing.

## Non-goals

- No "Estimated Usage and Supply Cost" combined sensor (explicitly deferred by the issue).
- No support for non-SC charge types (GreenPower, demand charges, etc.) — only the confirmed daily supply/service charge.
- No historical backdating into HA long-term statistics beyond standard `last_reset` semantics.

## Rate selection

A service charge rate is identified as the entry in `coordinator.get_service_rates(property_id, service_type)` where `rate.get("type") == "SC"` **and** `rate.get("unit") == "day"`. Both conditions must match (not either alone), since `type` and `unit` are independent fields on the payload and neither alone is a reliable-enough signal for "this is the service charge."

- **Zero matches** → both sensors report `native_value = None` (unavailable). This includes gas accounts without a confirmed daily supply charge.
- **Exactly one match** → used directly.
- **More than one match** → the first match in the rates list is used; others are ignored. (No real-world account with multiple SC/day rates has been observed; if one surfaces, this is the place to revisit.)

This applies identically to electricity and gas — neither sensor is `_electricity_only`.

## Coordinator changes (`coordinator.py`)

### `_find_service_charge_rate(property_id, service_type) -> dict | None`
Returns the single matching SC/day rate as described above, or `None`.

### Billing period start — factor out shared helper
`_get_usage_period_dates()` currently inlines the `lastBillDate + 1` / 30-day-fallback logic to compute a `(start_date, end_date)` tuple for fetching usage data, using `datetime.now()` as `end_date`. Extract the start-date resolution into:

```python
def _get_billing_period_start(self, service: dict[str, Any]) -> datetime:
    """Resolve the current billing period's start date (lastBillDate + 1,
    falling back to a 30-day window when lastBillDate is missing/invalid/
    in the future/implausibly old)."""
```

`_get_usage_period_dates()` calls this helper and keeps its own `end_date = datetime.now()` for the usage-fetch window (unchanged behavior). The new service-charge day-count logic below calls the same helper but uses the latest completed `usageDate` as its end boundary instead of `datetime.now()`, since the issue explicitly wants completed days only.

### `get_daily_service_charge(property_id, service_type) -> float | None`
Returns `rate_incl_gst_dollars` from `_find_service_charge_rate(...)`, or `None` if no rate.

### `get_billing_period_service_charge(property_id, service_type) -> float | None`
```
rate = _find_service_charge_rate(property_id, service_type)
if rate is None: return None

latest_usage_date = get_latest_usage_date(property_id, service_type)  # existing method
if latest_usage_date is None: return None

service = get_service_metadata(property_id, service_type)
billing_period_start = _get_billing_period_start(service)
billing_period_end = parse(latest_usage_date)

if billing_period_end < billing_period_start.date(): return None

represented_day_count = (billing_period_end - billing_period_start.date()).days + 1
return rate["rate_incl_gst_dollars"] * represented_day_count
```

`end < start` covers the case where cached/stale usage data predates a just-rolled billing period.

### Excl-GST values
Computed on demand from the rate dict (not persisted as new coordinator state):
```python
service_rate_excl_gst = round(rate["rate_excl_gst_cents"] / 100, 5) if rate.get("rate_excl_gst_cents") is not None else None
```
Same rounding convention as `data_validation.validate_rates()`'s `rate_incl_gst_dollars`. Billing-period excl-GST total is `service_rate_excl_gst * represented_day_count` (no additional rounding applied to the multiple).

## Sensor changes (`sensor.py`)

Both sensors: `device_class = MONETARY`, `native_unit_of_measurement = "AUD"`, `state_class = TOTAL`. Added to the **advanced sensors** block in `async_setup_entry` (gated on `CONF_ENABLE_ADVANCED_SENSORS`), for both electricity and gas services — not `_electricity_only`.

### `RedEnergyDailyServiceChargeSensor` (`SENSOR_TYPE_DAILY_SERVICE_CHARGE = "daily_service_charge"`)
- `native_value`: `coordinator.get_daily_service_charge(...)`
- `last_reset`: `self._get_latest_usage_date_reset()` (existing helper — start of the represented `usageDate`)
- `extra_state_attributes`:
  ```
  usage_date: coordinator.get_latest_usage_date(...)
  service_rate_incl_gst: <rate incl GST>
  service_rate_excl_gst: <rate excl GST>
  represented_day_count: 1
  calculation: "service_rate_incl_gst × 1 day"
  ```
  Returns `None` when the sensor has no backing rate (mirrors `RedEnergyRateSensor` returning `None` attrs when its rate disappears).

### `RedEnergyBillingPeriodServiceChargeSensor` (`SENSOR_TYPE_BILLING_PERIOD_SERVICE_CHARGE = "billing_period_service_charge"`)
- `native_value`: `coordinator.get_billing_period_service_charge(...)`
- `last_reset`: start of the current billing period (new sensor-level helper `_get_billing_period_reset()`, built on the coordinator's `_get_billing_period_start`)
- `extra_state_attributes`:
  ```
  billing_period_start: <date>
  billing_period_end: <latest usage_date>
  latest_usage_date: <same as billing_period_end>
  represented_day_count: <int>
  service_rate_incl_gst: <rate incl GST>
  service_rate_excl_gst: <rate excl GST>
  calculation: "service_rate_incl_gst × represented_day_count days"
  ```
  Returns `None` when `native_value` is `None`.

## `const.py`
Add:
```python
SENSOR_TYPE_DAILY_SERVICE_CHARGE: Final = "daily_service_charge"
SENSOR_TYPE_BILLING_PERIOD_SERVICE_CHARGE: Final = "billing_period_service_charge"
```

## Testing

- **Coordinator unit tests** (new, alongside existing coordinator test file):
  - `_find_service_charge_rate`: zero/one/multiple SC-and-day matches; type-only or unit-only matches are correctly excluded.
  - `get_daily_service_charge`: returns rate or `None`.
  - `get_billing_period_service_charge`: correct day-count math for a normal case (mirroring the issue's 7-day/$12.47015 example), `lastBillDate` missing → 30-day fallback, `latest_usage_date` missing → `None`, `end < start` → `None`.
- **Sensor tests** (new, alongside `test_sensor_rates.py` conventions):
  - `native_value`, `last_reset`, and `extra_state_attributes` for both sensors in the matched-rate and no-rate cases.
  - Confirm both sensors are only created when `CONF_ENABLE_ADVANCED_SENSORS` is enabled, and are created for both electricity and gas services when a matching rate exists.

## Version bump
Per repo convention, bump `manifest.json` `version` (MINOR, new feature) as the first commit on the feature branch.
