# CL2/TOU Inference Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the standalone inference engine that separates blended TOU+Controlled-Load-2 (CL2) interval energy into its TOU and CL2 components, using per-interval pricing data and plan tariff rates — with no coordinator wiring or user-facing sensors yet.

**Architecture:** A new, dependency-free module (`cl2_inference.py`) implements the algebraic inference formula from issue #61 as a pure function over one interval dict plus a resolved rate map, with explicit accept/reject safeguards. A second pure function resolves which of a service's tariff rates are the PEAK/OFFPEAK/SHOULDER/CL2 "roles" by matching `rate_desc` text, only succeeding when each role matches exactly one rate. `api.py`'s interval loop is extended to capture the additional per-interval fields (`consumptionDollarIncGst`, `isPricingAvailable`, `isPricingReliable`) these functions need, stored per-interval on the normalized daily entry (not just the existing daily rollups) so a later stage can run inference without re-fetching raw API data.

**Tech Stack:** Python 3.13/3.14, pytest, Home Assistant custom integration conventions (plain dicts, no dataclasses/pydantic — this codebase uses neither).

## Global Constraints

- No existing raw/combined TOU sensor, coordinator method, or API field changes meaning — this plan is strictly additive. Do not modify `peak_import_usage`, `offpeak_import_usage`, `shoulder_import_usage`, or any other existing key in the dict returned by `_normalize_usage_entry`.
- Follow existing codebase conventions: plain `dict[str, Any]` returns, not dataclasses (verified: zero dataclass usage anywhere in `custom_components/red_energy/`).
- All new code lives in `custom_components/red_energy/`; all new tests live in `tests/` at the repo root, matching the existing flat test-file layout (no subdirectories).
- Money/energy rounding: energy to 6 decimal places, cost to 6 decimal places within the inference module (matches `carbon_emission_tonne` 6-dp precision elsewhere in `api.py`, and preserves precision for reconciliation-error checks that need finer granularity than the 2-3 dp used in already-published sensor values).
- Every new pure function must be independently unit-testable without a running coordinator, HA test harness, or mocked API client — plain input dict/list in, dict out.
- Do not add any new sensor, coordinator method, or config-flow/options-flow change in this plan. This is explicitly stage (a) of a two-stage rollout (per the plan author's comment on issue #61) — stage (b) wires this engine into sensors in a follow-up plan once this stage is merged and validated.
- `flake8 custom_components --count --select=E9,F63,F7,F82` and `mypy custom_components/red_energy --ignore-missing-imports` must stay clean for any file this plan touches (per this repo's CI, even though both are `continue-on-error: true`).

---

### Task 1: Capture per-interval pricing fields in `_normalize_usage_entry`

**Files:**
- Modify: `custom_components/red_energy/api.py:568-778` (the `_normalize_usage_entry` method) and `custom_components/red_energy/api.py:780-802` (the `_empty_entry` method)
- Test: `tests/test_api_interval_pricing.py` (new file)

**Interfaces:**
- Consumes: nothing new — reads directly from the raw `halfHours[]` interval dicts already looped over in `_normalize_usage_entry`.
- Produces: each entry returned by `_normalize_usage_entry` (and `_empty_entry`) gains one new key, `"intervals"`, a `list[dict[str, Any]]` — one dict per half-hour interval that had recognizable interval data, in the same order as the source `halfHours[]` array. Each interval dict has exactly these keys:
  - `"interval_start"`: `str | None` — raw value of `interval.get("intervalStart")`
  - `"consumption_kwh"`: `float` — raw value of `interval.get("consumptionKwh", 0.0)`, cast to float (same extraction as the existing `consumption` local variable)
  - `"consumption_dollar_incl_gst"`: `float | None` — `interval.get("consumptionDollarIncGst")` cast to float if present and not None, else `None`
  - `"tariff_component"`: `str` — the same normalized period value already computed in the existing loop (upper-cased, stripped; empty string `""` if no period field matched, exactly matching existing `period` variable semantics)
  - `"pricing_available"`: `bool` — `bool(interval.get("isPricingAvailable", False))`
  - `"pricing_reliable"`: `bool` — `bool(interval.get("isPricingReliable", False))`

  Later tasks (the inference module) consume this `"intervals"` list — each dict in it is the direct input to `infer_cl2_interval()` (Task 2).

- [ ] **Step 1: Write the failing test for interval capture**

Create `tests/test_api_interval_pricing.py`:

```python
"""Tests for per-interval pricing field capture in _normalize_usage_entry."""
import pytest

from custom_components.red_energy.api import RedEnergyAPI


@pytest.fixture
def api():
    return RedEnergyAPI(session=None)


def test_normalize_usage_entry_captures_interval_pricing_fields(api):
    """Each halfHours[] interval must surface as a dict on the "intervals" key
    with the fields the CL2 inference engine needs."""
    entry = {
        "usageDate": "2026-07-23",
        "halfHours": [
            {
                "intervalStart": "2026-07-23T21:00:00+10:00",
                "consumptionKwh": 1.702,
                "consumptionDollarIncGst": 0.4007,
                "primaryConsumptionTariffComponent": "SHOULDER",
                "isPricingAvailable": True,
                "isPricingReliable": True,
            },
        ],
        "consumptionDollar": 0.36,
    }

    result = api._normalize_usage_entry(entry)

    assert "intervals" in result
    assert len(result["intervals"]) == 1
    interval = result["intervals"][0]
    assert interval["interval_start"] == "2026-07-23T21:00:00+10:00"
    assert interval["consumption_kwh"] == pytest.approx(1.702)
    assert interval["consumption_dollar_incl_gst"] == pytest.approx(0.4007)
    assert interval["tariff_component"] == "SHOULDER"
    assert interval["pricing_available"] is True
    assert interval["pricing_reliable"] is True


def test_normalize_usage_entry_defaults_missing_pricing_fields(api):
    """Intervals from accounts/plans without pricing data (or older API
    responses) must not raise - pricing fields default to unavailable."""
    entry = {
        "usageDate": "2026-07-23",
        "halfHours": [
            {
                "intervalStart": "2026-07-23T21:00:00+10:00",
                "consumptionKwh": 0.5,
                "primaryConsumptionTariffComponent": "PEAK",
            },
        ],
    }

    result = api._normalize_usage_entry(entry)

    interval = result["intervals"][0]
    assert interval["consumption_dollar_incl_gst"] is None
    assert interval["pricing_available"] is False
    assert interval["pricing_reliable"] is False


def test_normalize_usage_entry_intervals_empty_when_no_half_hours(api):
    """An entry with no halfHours array must produce an empty intervals list,
    not raise or omit the key."""
    entry = {"usageDate": "2026-07-23", "consumptionDollar": 0.0}

    result = api._normalize_usage_entry(entry)

    assert result["intervals"] == []


def test_empty_entry_has_intervals_key():
    """_empty_entry() must include the intervals key so callers don't need
    a hasattr/get-with-default check to use it uniformly."""
    api = RedEnergyAPI(session=None)
    result = api._empty_entry()
    assert result["intervals"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_interval_pricing.py -v`
Expected: FAIL — `KeyError: 'intervals'` (or similar) on every test, since `_normalize_usage_entry` does not yet produce this key.

- [ ] **Step 3: Implement interval capture in `_normalize_usage_entry`**

In `custom_components/red_energy/api.py`, inside the `if isinstance(half_hours, list):` loop in `_normalize_usage_entry` (around line 641), add an accumulator list before the loop starts:

```python
        # Max demand tracking
        max_demand_kw = 0.0
        max_demand_time = None
        demand_data_available = False

        # Per-interval pricing data for CL2/TOU inference (see issue #61) -
        # captured alongside the existing daily rollups, not instead of them.
        intervals: list[dict[str, Any]] = []
```

(Insert this `intervals: list[dict[str, Any]] = []` line immediately after the existing `demand_data_available = False` line.)

The new append call must use the normalized `period` value as `tariff_component`, and `period` is only computed partway through the existing loop body (in the `period = ""` / `period_field_candidates` block). So the insertion point is **after** that computation, not at the top of the loop. Concretely, the full ordering inside the loop body becomes:

1. Existing: extract `consumption`, `generation`
2. Existing: compute `period` via `period_field_candidates` loop
3. Existing: `if period in ("PEAK", "OFFPEAK", "SHOULDER"): breakdown_available = True`
4. **New:** append to `intervals` using the now-computed `period` as `tariff_component`
5. Existing: accumulate totals, period-specific accumulation, max demand tracking

Add this block immediately after the existing:

```python
                # Only mark breakdown available for known ToU periods (ALLDAY = anytime tariff, no breakdown)
                if period in ("PEAK", "OFFPEAK", "SHOULDER"):
                    breakdown_available = True
```

and before the existing `# Accumulate totals` block:

```python
                # Capture per-interval pricing for CL2/TOU inference (issue #61).
                consumption_dollar_incl_gst_raw = interval.get("consumptionDollarIncGst")
                intervals.append({
                    "interval_start": interval.get("intervalStart"),
                    "consumption_kwh": consumption,
                    "consumption_dollar_incl_gst": (
                        float(consumption_dollar_incl_gst_raw)
                        if consumption_dollar_incl_gst_raw is not None
                        else None
                    ),
                    "tariff_component": period,
                    "pricing_available": bool(interval.get("isPricingAvailable", False)),
                    "pricing_reliable": bool(interval.get("isPricingReliable", False)),
                })
```

Finally, in the `result = {...}` dict literal at the end of `_normalize_usage_entry` (around line 745), add the new key. Insert it as its own labeled section, immediately after the existing `"_breakdown_available": breakdown_available` line:

```python
            # Metadata: indicate if breakdown data was available
            "_breakdown_available": breakdown_available,

            # Per-interval pricing data for CL2/TOU inference (issue #61)
            "intervals": intervals
```

(Note the trailing comma added to the `"_breakdown_available"` line since it's no longer the last entry.)

In `_empty_entry()`, add the same key with an empty list default. Insert immediately after the existing `"carbon_emission_tonne": 0.0` line:

```python
            "carbon_emission_tonne": 0.0,
            "intervals": []
```

(Note the trailing comma added to the `"carbon_emission_tonne"` line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_interval_pricing.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, same count as before plus 4 (no existing test asserts the exact key set of `_normalize_usage_entry`'s return value in a way that a new key would break — verify this assumption holds by checking the output for any new failures, not just a pass/fail count).

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/api.py tests/test_api_interval_pricing.py
git commit -m "feat: capture per-interval pricing data for CL2/TOU inference"
```

---

### Task 2: Interval-level CL2/TOU inference function

**Files:**
- Create: `custom_components/red_energy/cl2_inference.py`
- Test: `tests/test_cl2_inference.py`

**Interfaces:**
- Consumes: one interval dict matching the exact shape produced by Task 1 (`interval_start`, `consumption_kwh`, `consumption_dollar_incl_gst`, `tariff_component`, `pricing_available`, `pricing_reliable`), plus a `rates_incl_gst: dict[str, float]` mapping tariff-component strings (`"PEAK"`, `"OFFPEAK"`, `"SHOULDER"`) to their GST-inclusive dollar rate, plus a `cl2_rate_incl_gst: float`.
- Produces: `infer_cl2_interval(interval, rates_incl_gst, cl2_rate_incl_gst, *, tolerance_kwh=0.01) -> dict[str, Any]` — the function later tasks (and stage-b sensors) call per interval. Return dict has exactly these keys: `"combined_kwh"`, `"tou_kwh"`, `"cl2_kwh"`, `"api_cost"`, `"reconstructed_cost"`, `"reconciliation_error"`, `"accepted"` (bool), `"reason"` (`str | None` — populated only when `"accepted"` is `False`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cl2_inference.py`:

```python
"""Tests for the CL2/TOU interval inference engine (issue #61).

Test data and expected results are drawn from the real sanitised interval
and rate values provided by @LoznOz in the issue #61 discussion.
"""
import pytest

from custom_components.red_energy.cl2_inference import infer_cl2_interval

RATES_INCL_GST = {
    "PEAK": 0.45760,
    "SHOULDER": 0.41745,
    "OFFPEAK": 0.32483,
}
CL2_RATE_INCL_GST = 0.18425


def _interval(**overrides):
    base = {
        "interval_start": "2026-07-23T21:00:00+10:00",
        "consumption_kwh": 1.702,
        "consumption_dollar_incl_gst": 0.4007,
        "tariff_component": "SHOULDER",
        "pricing_available": True,
        "pricing_reliable": True,
    }
    base.update(overrides)
    return base


def test_infers_cl2_and_tou_split_for_shoulder_interval():
    """Worked example from issue #61: a Shoulder interval blending CL2."""
    result = infer_cl2_interval(_interval(), RATES_INCL_GST, CL2_RATE_INCL_GST)

    assert result["accepted"] is True
    assert result["reason"] is None
    assert result["combined_kwh"] == pytest.approx(1.702, abs=1e-6)
    assert result["cl2_kwh"] == pytest.approx(1.328, abs=0.01)
    assert result["tou_kwh"] == pytest.approx(0.374, abs=0.01)
    assert result["reconciliation_error"] == pytest.approx(0.0, abs=0.001)


def test_rejects_when_pricing_not_available():
    result = infer_cl2_interval(
        _interval(pricing_available=False), RATES_INCL_GST, CL2_RATE_INCL_GST
    )
    assert result["accepted"] is False
    assert result["reason"] == "pricing_not_available"


def test_rejects_when_pricing_not_reliable():
    result = infer_cl2_interval(
        _interval(pricing_reliable=False), RATES_INCL_GST, CL2_RATE_INCL_GST
    )
    assert result["accepted"] is False
    assert result["reason"] == "pricing_not_reliable"


def test_rejects_when_cost_missing():
    result = infer_cl2_interval(
        _interval(consumption_dollar_incl_gst=None), RATES_INCL_GST, CL2_RATE_INCL_GST
    )
    assert result["accepted"] is False
    assert result["reason"] == "missing_interval_cost"


def test_rejects_unknown_tariff_component():
    result = infer_cl2_interval(
        _interval(tariff_component="ALLDAY"), RATES_INCL_GST, CL2_RATE_INCL_GST
    )
    assert result["accepted"] is False
    assert result["reason"] == "unknown_tariff"


def test_rejects_when_tou_rate_equals_cl2_rate():
    """Rt == Rc makes the algebraic split undefined (division by zero)."""
    result = infer_cl2_interval(
        _interval(), RATES_INCL_GST, cl2_rate_incl_gst=RATES_INCL_GST["SHOULDER"]
    )
    assert result["accepted"] is False
    assert result["reason"] == "rates_not_distinguishable"


def test_rejects_when_inferred_cl2_out_of_range():
    """An interval cost wildly inconsistent with any TOU/CL2 rate combination
    must be rejected rather than returning a nonsensical negative or
    over-100%-of-combined split."""
    result = infer_cl2_interval(
        _interval(consumption_dollar_incl_gst=100.0), RATES_INCL_GST, CL2_RATE_INCL_GST
    )
    assert result["accepted"] is False
    assert result["reason"] == "inferred_cl2_out_of_range"


def test_clamps_small_negative_inference_to_zero_within_tolerance():
    """API rounding can produce a tiny negative inferred CL2 for
    CL2-free intervals - clamp to 0 within tolerance_kwh rather than reject."""
    # Choose a cost that reconstructs to a CL2 value of exactly 0 kWh, i.e.
    # cost == energy * TOU rate. A cost fractionally above that (within
    # tolerance) should still be accepted with cl2_kwh clamped to 0.0.
    energy = 1.0
    exact_zero_cl2_cost = energy * RATES_INCL_GST["PEAK"]
    result = infer_cl2_interval(
        _interval(
            consumption_kwh=energy,
            consumption_dollar_incl_gst=exact_zero_cl2_cost + 0.001,
            tariff_component="PEAK",
        ),
        RATES_INCL_GST,
        CL2_RATE_INCL_GST,
        tolerance_kwh=0.01,
    )
    assert result["accepted"] is True
    assert result["cl2_kwh"] == pytest.approx(0.0, abs=1e-9)
    assert result["tou_kwh"] == pytest.approx(energy, abs=1e-6)


def test_clamps_small_over_range_inference_to_combined_within_tolerance():
    """Symmetric case: inferred CL2 fractionally above combined_kwh (all-CL2
    interval plus rounding noise) clamps to combined_kwh rather than reject."""
    energy = 1.0
    exact_all_cl2_cost = energy * CL2_RATE_INCL_GST
    result = infer_cl2_interval(
        _interval(
            consumption_kwh=energy,
            consumption_dollar_incl_gst=exact_all_cl2_cost - 0.001,
            tariff_component="PEAK",
        ),
        RATES_INCL_GST,
        CL2_RATE_INCL_GST,
        tolerance_kwh=0.01,
    )
    assert result["accepted"] is True
    assert result["cl2_kwh"] == pytest.approx(energy, abs=1e-6)
    assert result["tou_kwh"] == pytest.approx(0.0, abs=1e-9)


def test_reconstructed_cost_matches_api_cost_within_tolerance():
    result = infer_cl2_interval(_interval(), RATES_INCL_GST, CL2_RATE_INCL_GST)
    assert result["reconstructed_cost"] == pytest.approx(
        result["api_cost"], abs=0.001
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cl2_inference.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'custom_components.red_energy.cl2_inference'`

- [ ] **Step 3: Implement `cl2_inference.py`**

Create `custom_components/red_energy/cl2_inference.py`:

```python
"""CL2 (Controlled Load 2) / TOU energy inference.

Red Energy's usage API returns a single blended consumptionKwh per
half-hour interval that combines general-supply TOU consumption with any
CL2 (controlled load) consumption occurring in the same interval, labelled
only with the active TOU tariff component. The interval cost, however, is
still priced correctly behind the scenes: general-supply energy at the
active TOU rate, CL2 energy at the CL2 rate, summed into one interval cost.

Given the interval's combined energy (E), its cost (C), the active TOU
rate (Rt), and the account's CL2 rate (Rc):

    CL2 kWh  = (E * Rt - C) / (Rt - Rc)
    TOU kWh  = E - CL2 kWh

This module infers that split per interval. See issue #61 for the full
derivation and empirical validation (~0.35% error against independently
metered CL2 consumption) contributed by @LoznOz.
"""
from __future__ import annotations

from typing import Any

_KNOWN_TOU_COMPONENTS = ("PEAK", "OFFPEAK", "SHOULDER")


def infer_cl2_interval(
    interval: dict[str, Any],
    rates_incl_gst: dict[str, float],
    cl2_rate_incl_gst: float,
    *,
    tolerance_kwh: float = 0.01,
) -> dict[str, Any]:
    """Infer the CL2/TOU energy split for one interval.

    Args:
        interval: one entry from _normalize_usage_entry()'s "intervals" list
            (see api.py) - must have interval_start, consumption_kwh,
            consumption_dollar_incl_gst, tariff_component, pricing_available,
            pricing_reliable.
        rates_incl_gst: mapping of "PEAK"/"OFFPEAK"/"SHOULDER" to the
            GST-inclusive dollar rate that applied on this interval's date.
        cl2_rate_incl_gst: the GST-inclusive CL2 dollar rate that applied on
            this interval's date.
        tolerance_kwh: allowed rounding noise when the raw inferred CL2
            value falls fractionally outside [0, combined_kwh].

    Returns:
        A dict with combined_kwh, tou_kwh, cl2_kwh, api_cost,
        reconstructed_cost, reconciliation_error, accepted, and reason
        (None when accepted).
    """
    energy = float(interval.get("consumption_kwh") or 0.0)

    def _rejected(reason: str, api_cost: float = 0.0) -> dict[str, Any]:
        return {
            "combined_kwh": round(energy, 6),
            "tou_kwh": 0.0,
            "cl2_kwh": 0.0,
            "api_cost": round(api_cost, 6),
            "reconstructed_cost": 0.0,
            "reconciliation_error": 0.0,
            "accepted": False,
            "reason": reason,
        }

    if not interval.get("pricing_available", False):
        return _rejected("pricing_not_available")

    if not interval.get("pricing_reliable", False):
        return _rejected("pricing_not_reliable")

    cost = interval.get("consumption_dollar_incl_gst")
    if cost is None:
        return _rejected("missing_interval_cost")

    tariff_component = interval.get("tariff_component")
    if tariff_component not in _KNOWN_TOU_COMPONENTS:
        return _rejected("unknown_tariff", api_cost=float(cost))

    tou_rate = rates_incl_gst.get(tariff_component)
    if tou_rate is None:
        return _rejected("unknown_tariff", api_cost=float(cost))

    denominator = tou_rate - cl2_rate_incl_gst
    if abs(denominator) < 1e-9:
        return _rejected("rates_not_distinguishable", api_cost=float(cost))

    cost = float(cost)
    inferred_cl2 = (energy * tou_rate - cost) / denominator

    # Clamp small rounding noise at either boundary rather than reject.
    if -tolerance_kwh <= inferred_cl2 < 0:
        inferred_cl2 = 0.0
    elif energy < inferred_cl2 <= energy + tolerance_kwh:
        inferred_cl2 = energy

    if inferred_cl2 < 0 or inferred_cl2 > energy:
        return _rejected("inferred_cl2_out_of_range", api_cost=cost)

    tou_kwh = energy - inferred_cl2
    reconstructed_cost = tou_kwh * tou_rate + inferred_cl2 * cl2_rate_incl_gst

    return {
        "combined_kwh": round(energy, 6),
        "tou_kwh": round(tou_kwh, 6),
        "cl2_kwh": round(inferred_cl2, 6),
        "api_cost": round(cost, 6),
        "reconstructed_cost": round(reconstructed_cost, 6),
        "reconciliation_error": round(reconstructed_cost - cost, 6),
        "accepted": True,
        "reason": None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cl2_inference.py -v`
Expected: PASS (10/10)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, all prior tests plus 10 new ones green.

- [ ] **Step 6: Commit**

```bash
git add custom_components/red_energy/cl2_inference.py tests/test_cl2_inference.py
git commit -m "feat: add CL2/TOU interval inference engine"
```

---

### Task 3: Rate-role resolution (matching plan rates to PEAK/OFFPEAK/SHOULDER/CL2)

**Files:**
- Modify: `custom_components/red_energy/cl2_inference.py` (add to the same module — small, tightly related to Task 2's consumer)
- Test: `tests/test_cl2_inference.py` (extend the same file from Task 2)

**Interfaces:**
- Consumes: `rates: list[dict[str, Any]]` — the exact list shape returned by `coordinator.get_service_rates()` / `data_validation.validate_rates()`, i.e. each dict has (at minimum) `"rate_desc": str` and `"rate_incl_gst_dollars": float`.
- Produces: `resolve_rate_roles(rates: list[dict[str, Any]]) -> dict[str, Any]` — returns a dict with keys `"rates_incl_gst"` (`dict[str, float]`, only the roles that resolved unambiguously — a `dict[str, float]` suitable for passing directly as `infer_cl2_interval`'s `rates_incl_gst` argument, using only the `"PEAK"`/`"OFFPEAK"`/`"SHOULDER"` keys present), `"cl2_rate_incl_gst"` (`float | None`), and `"unresolved_roles"` (`list[str]`, the roles that did not match exactly one rate, using the labels `"PEAK"`, `"OFFPEAK"`, `"SHOULDER"`, `"CL2"`).

  This is the function stage-b (a future plan) will call once per property/service before running `infer_cl2_interval` in a loop, using the resolved `rates_incl_gst`/`cl2_rate_incl_gst` as that function's arguments. A caller must check `"unresolved_roles"` is empty (or at least that the roles it needs are absent from it) before trusting `"rates_incl_gst"`/`"cl2_rate_incl_gst"` for inference — this plan does not enforce that at the caller since there is no caller yet.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cl2_inference.py`:

```python
from custom_components.red_energy.cl2_inference import resolve_rate_roles


def _rate(rate_desc: str, rate_incl_gst_dollars: float) -> dict:
    return {
        "rate_code": "irrelevant-for-role-matching",
        "rate_desc": rate_desc,
        "rate_incl_gst_dollars": rate_incl_gst_dollars,
    }


def test_resolves_all_four_roles_from_real_account_rates():
    """Rates and labels from the real account data in issue #61."""
    rates = [
        _rate("Peak", 0.45760),
        _rate("Shoulder", 0.41745),
        _rate("Off-peak", 0.32483),
        _rate("CL2", 0.18425),
    ]

    result = resolve_rate_roles(rates)

    assert result["rates_incl_gst"] == {
        "PEAK": pytest.approx(0.45760),
        "SHOULDER": pytest.approx(0.41745),
        "OFFPEAK": pytest.approx(0.32483),
    }
    assert result["cl2_rate_incl_gst"] == pytest.approx(0.18425)
    assert result["unresolved_roles"] == []


@pytest.mark.parametrize(
    "off_peak_label",
    ["Off-peak", "Off Peak", "OffPeak", "off peak", "OFF-PEAK"],
)
def test_offpeak_label_variants_all_resolve(off_peak_label):
    rates = [_rate(off_peak_label, 0.32483)]
    result = resolve_rate_roles(rates)
    assert result["rates_incl_gst"].get("OFFPEAK") == pytest.approx(0.32483)
    assert "OFFPEAK" not in result["unresolved_roles"]


@pytest.mark.parametrize(
    "cl2_label",
    ["CL2", "cl2", "Controlled Load 2", "controlled load"],
)
def test_cl2_label_variants_all_resolve(cl2_label):
    rates = [_rate(cl2_label, 0.18425)]
    result = resolve_rate_roles(rates)
    assert result["cl2_rate_incl_gst"] == pytest.approx(0.18425)
    assert "CL2" not in result["unresolved_roles"]


def test_peak_does_not_false_match_offpeak():
    """"Peak" must not match as a substring of "Off-peak" or vice versa -
    each role's label set must be distinguishing, not just substring checks."""
    rates = [_rate("Peak", 0.45760), _rate("Off-peak", 0.32483)]
    result = resolve_rate_roles(rates)
    assert result["rates_incl_gst"]["PEAK"] == pytest.approx(0.45760)
    assert result["rates_incl_gst"]["OFFPEAK"] == pytest.approx(0.32483)
    assert "PEAK" not in result["unresolved_roles"]
    assert "OFFPEAK" not in result["unresolved_roles"]


def test_role_unresolved_when_no_rate_matches():
    rates = [_rate("Peak", 0.45760)]  # no Shoulder/Off-peak/CL2 rate present
    result = resolve_rate_roles(rates)
    assert "SHOULDER" in result["unresolved_roles"]
    assert "OFFPEAK" in result["unresolved_roles"]
    assert "CL2" in result["unresolved_roles"]
    assert result["cl2_rate_incl_gst"] is None
    assert "SHOULDER" not in result["rates_incl_gst"]


def test_role_unresolved_when_multiple_rates_match_same_role():
    """Two rate rows that both normalize to the same label (e.g. a plan
    change mid-period leaving two "Peak" entries) must not be resolved by
    picking the first/last - ambiguous matches stay unresolved."""
    rates = [_rate("Peak", 0.45760), _rate("PEAK", 0.40000)]
    result = resolve_rate_roles(rates)
    assert "PEAK" in result["unresolved_roles"]
    assert "PEAK" not in result["rates_incl_gst"]


def test_unrelated_rates_are_ignored_not_misclassified():
    """Solar feed-in and tiered gas rates must not be forced into a role."""
    rates = [
        _rate("Peak", 0.45760),
        _rate("Solar", -0.04),
        _rate("Anytime Step1", 0.0495),
    ]
    result = resolve_rate_roles(rates)
    assert result["rates_incl_gst"]["PEAK"] == pytest.approx(0.45760)
    assert "SHOULDER" in result["unresolved_roles"]


def test_empty_rates_list_resolves_nothing():
    result = resolve_rate_roles([])
    assert result["rates_incl_gst"] == {}
    assert result["cl2_rate_incl_gst"] is None
    assert set(result["unresolved_roles"]) == {"PEAK", "OFFPEAK", "SHOULDER", "CL2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cl2_inference.py -v -k resolve_rate_roles or _resolve or _label or _match or _role`
Expected: FAIL — `ImportError: cannot import name 'resolve_rate_roles'`

- [ ] **Step 3: Implement `resolve_rate_roles`**

Append to `custom_components/red_energy/cl2_inference.py`:

```python
# Each role matches only when exactly one rate's normalized rate_desc is in
# its label set. "PEAK" uses an exact match (not substring) so it cannot
# false-match "Off-peak"/"off peak" - the OFFPEAK label set spells that
# case out explicitly instead of relying on "peak" appearing in both.
_ROLE_LABELS: dict[str, frozenset[str]] = {
    "PEAK": frozenset({"peak"}),
    "OFFPEAK": frozenset({"off peak", "off-peak", "offpeak"}),
    "SHOULDER": frozenset({"shoulder"}),
    "CL2": frozenset({"cl2", "controlled load 2", "controlled load"}),
}


def _normalize_rate_desc(rate_desc: str) -> str:
    return " ".join(rate_desc.strip().lower().split())


def resolve_rate_roles(rates: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a service's tariff rates to PEAK/OFFPEAK/SHOULDER/CL2 roles.

    Matching is by normalized rate_desc text against a fixed label set per
    role (see _ROLE_LABELS) - there is no controlled-vocabulary field tying
    a rate row to a role, so this is inherently best-effort. A role only
    resolves when exactly one rate in the list matches its label set; zero
    or multiple matches leave that role unresolved rather than guessing.

    Args:
        rates: the validated rates list for one service, as returned by
            coordinator.get_service_rates() (each dict has at least
            rate_desc and rate_incl_gst_dollars).

    Returns:
        A dict with rates_incl_gst (dict[str, float], only resolved
        PEAK/OFFPEAK/SHOULDER roles), cl2_rate_incl_gst (float | None), and
        unresolved_roles (list[str], the roles that did not resolve).
    """
    matches: dict[str, list[float]] = {role: [] for role in _ROLE_LABELS}

    for rate in rates:
        rate_desc = rate.get("rate_desc")
        if not isinstance(rate_desc, str):
            continue
        normalized = _normalize_rate_desc(rate_desc)

        for role, labels in _ROLE_LABELS.items():
            if normalized in labels:
                rate_value = rate.get("rate_incl_gst_dollars")
                if rate_value is not None:
                    matches[role].append(float(rate_value))

    rates_incl_gst: dict[str, float] = {}
    cl2_rate_incl_gst: float | None = None
    unresolved_roles: list[str] = []

    for role in ("PEAK", "OFFPEAK", "SHOULDER"):
        if len(matches[role]) == 1:
            rates_incl_gst[role] = matches[role][0]
        else:
            unresolved_roles.append(role)

    if len(matches["CL2"]) == 1:
        cl2_rate_incl_gst = matches["CL2"][0]
    else:
        unresolved_roles.append("CL2")

    return {
        "rates_incl_gst": rates_incl_gst,
        "cl2_rate_incl_gst": cl2_rate_incl_gst,
        "unresolved_roles": unresolved_roles,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cl2_inference.py -v`
Expected: PASS (all tests in the file, Task 2's 10 plus Task 3's 9 = 19)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS, all prior tests plus the new ones from Tasks 1-3.

- [ ] **Step 6: Run lint and type checks on the new/modified files**

Run: `.venv/bin/python -m flake8 custom_components/red_energy/cl2_inference.py custom_components/red_energy/api.py --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0` (no output, exit code 0)

Run: `.venv/bin/python -m mypy custom_components/red_energy/cl2_inference.py --ignore-missing-imports`
Expected: `Success: no issues found` (if mypy is not installed in the venv, note this in the commit/report rather than skipping silently — this repo's CI runs it with `continue-on-error: true`, so a missing local mypy is not a blocker, but must be reported, not hidden)

- [ ] **Step 7: Commit**

```bash
git add custom_components/red_energy/cl2_inference.py tests/test_cl2_inference.py
git commit -m "feat: add rate-role resolution for CL2/TOU inference"
```

---

## What This Plan Does Not Cover (deliberately)

This plan stops at a fully tested, standalone inference engine. It does **not**:
- Wire `infer_cl2_interval`/`resolve_rate_roles` into `coordinator.py`
- Add any new sensor in `sensor.py` or `const.py`
- Handle historical tariff versioning (using the rate that applied on an interval's date rather than today's plan rate) — `resolve_rate_roles` takes whatever `rates` list it's given; selecting the *correct* historical rates list per interval date is a stage-b coordinator concern once rate history storage is designed
- Add diagnostic attributes (`valid_intervals`, `rejected_intervals`, `reconciliation_difference` aggregated across a day/period) — those aggregate the per-interval `infer_cl2_interval` results, which is a sensor/coordinator concern for stage b

A follow-up plan will cover wiring this engine into the coordinator and adding the derived sensors described in issue #61, once this stage is merged.
