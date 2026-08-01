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
