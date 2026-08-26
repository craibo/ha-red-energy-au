"""Tests for GST basis of the current/daily import cost sensors.

Red Energy's consumptionDollar (-> import_cost) is ex-GST at the API
boundary. Current Period Import Cost, Current Period Net Cost, and Daily
Import Cost report this figure as-is (GST-exclusive) and disclose that
via a "gst_basis" attribute, rather than uplifting it - unlike the
forward-looking Projected Net Cost / Projected Charges sensors (see
test_projected_charges.py), which are deliberately GST-inclusive.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import (
    RedEnergyCostSensor,
    RedEnergyDailyImportCostSensor,
    RedEnergyTotalImportCostSensor,
)


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
            selected_accounts=["2000002"],
            services=["electricity"],
        )
    coord.api = AsyncMock()
    coord.api._access_token = "test_token"
    return coord


def _set_coordinator_data(coordinator, usage_entries):
    coordinator.data = {
        "usage_data": {
            "2000002": {
                "property": {
                    "name": "Test property",
                    "address": {},
                    "services": [
                        {
                            "type": SERVICE_TYPE_ELECTRICITY,
                            "consumer_number": "elec-1",
                            "meterType": "INTERVAL",
                            "rates": [],
                            "lastBillDate": "2025-07-25",
                        }
                    ],
                },
                "services": {
                    SERVICE_TYPE_ELECTRICITY: {
                        "consumer_number": "elec-1",
                        "last_updated": "2025-08-01T10:00:00",
                        "usage_data": {
                            "from_date": "2025-07-26",
                            "to_date": "2025-08-01",
                            "usage_data": usage_entries,
                        },
                    }
                },
            },
        }
    }


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


class TestCoordinatorGstExclusive:
    def test_get_total_import_cost_is_ex_gst(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [
                {"date": "2025-07-31", "import_usage": 10.0, "import_cost": 10.0, "export_credit": 0.0},
                {"date": "2025-08-01", "import_usage": 10.0, "import_cost": 25.0, "export_credit": 0.0},
            ],
        )
        assert coordinator.get_total_import_cost("2000002", SERVICE_TYPE_ELECTRICITY) == pytest.approx(35.0)

    def test_get_latest_import_cost_is_ex_gst(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [{"date": "2025-08-01", "import_usage": 10.0, "import_cost": 20.0, "export_credit": 0.0}],
        )
        assert coordinator.get_latest_import_cost("2000002", SERVICE_TYPE_ELECTRICITY) == pytest.approx(20.0)

    def test_get_total_cost_is_ex_gst_net(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [{"date": "2025-08-01", "import_usage": 10.0, "import_cost": 20.0, "export_credit": 5.0}],
        )
        # No GST uplift here - 20.0 - 5.0 = 15.0, not (20.0*1.10) - 5.0
        assert coordinator.get_total_cost("2000002", SERVICE_TYPE_ELECTRICITY) == pytest.approx(15.0)


class TestSensorGstBasisAttribute:
    def test_current_period_import_cost_discloses_exclusive(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [{"date": "2025-08-01", "import_usage": 10.0, "import_cost": 20.0, "export_credit": 0.0}],
        )
        sensor = RedEnergyTotalImportCostSensor(coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY)
        assert sensor.native_value == pytest.approx(20.0)
        assert sensor.extra_state_attributes["gst_basis"] == "exclusive"

    def test_current_period_net_cost_discloses_exclusive(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [{"date": "2025-08-01", "import_usage": 10.0, "import_cost": 20.0, "export_credit": 5.0}],
        )
        sensor = RedEnergyCostSensor(coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY)
        assert sensor.native_value == pytest.approx(15.0)
        assert sensor.extra_state_attributes["gst_basis"] == "exclusive"

    def test_daily_import_cost_discloses_exclusive(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [{"date": "2025-08-01", "import_usage": 10.0, "import_cost": 20.0, "export_credit": 0.0}],
        )
        sensor = RedEnergyDailyImportCostSensor(coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY)
        assert sensor.native_value == pytest.approx(20.0)
        assert sensor.extra_state_attributes["gst_basis"] == "exclusive"
