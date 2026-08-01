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

# CL2 resolves unambiguously, but there are no separate Peak/Off-peak/Shoulder
# rates - some accounts use a single flat TOU rate ("Anytime") alongside CL2.
# PEAK/OFFPEAK/SHOULDER all land in unresolved_roles in this case.
RATES_CL2_RESOLVED_TOU_UNRESOLVED = [
    {"rate_code": "A1", "rate_desc": "Anytime", "rate_incl_gst_dollars": 0.35000},
    {"rate_code": "C1", "rate_desc": "CL2", "rate_incl_gst_dollars": 0.18425},
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


def test_returns_none_when_tou_roles_unresolved_even_if_cl2_resolves(coordinator):
    """CL2 alone resolving isn't enough - if PEAK/OFFPEAK/SHOULDER don't all
    resolve too, inference must not run (see final-review bug report)."""
    _set_service_data(
        coordinator,
        [{"date": "2026-07-23", "intervals": [_shoulder_interval()]}],
        RATES_CL2_RESOLVED_TOU_UNRESOLVED,
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
