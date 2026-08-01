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
