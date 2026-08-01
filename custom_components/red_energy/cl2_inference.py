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
