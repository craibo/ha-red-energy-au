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
