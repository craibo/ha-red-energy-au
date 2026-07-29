"""Tests for the bug fixes tracked in GitHub issue #62.

Covers: daily energy sensor state class, max demand null-vs-zero,
"Peak Usage" sensor renaming, billing period boundary double-count,
and latest-day selection by usageDate instead of list position.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorStateClass

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.data_validation import validate_usage_entry
from custom_components.red_energy.sensor import (
    RedEnergyDailyImportUsageSensor,
    RedEnergyDailyExportUsageSensor,
    RedEnergyPeakUsageSensor,
)
from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY


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


def _usage_service_data(usage_entries, consumer_number="elec-123"):
    return {
        "consumer_number": consumer_number,
        "last_updated": "2024-01-30T10:00:00",
        "usage_data": {
            "from_date": "2024-01-01",
            "to_date": "2024-01-30",
            "usage_data": usage_entries,
        },
    }


def _set_service_usage(coordinator, usage_entries):
    coordinator.data = {
        "usage_data": {
            "prop-001": {
                "services": {
                    "electricity": _usage_service_data(usage_entries),
                }
            }
        }
    }


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


class TestDailyEnergySensorStateClass:
    """Bug #1: daily import/export usage sensors should be TOTAL, not TOTAL_INCREASING."""

    def test_daily_import_usage_is_total_not_total_increasing(self, coordinator):
        sensor = RedEnergyDailyImportUsageSensor(
            coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.state_class == SensorStateClass.TOTAL

    def test_daily_export_usage_is_total_not_total_increasing(self, coordinator):
        sensor = RedEnergyDailyExportUsageSensor(
            coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.state_class == SensorStateClass.TOTAL


class TestMaxDemandNullVsZero:
    """Bug #2: max demand should be None (unavailable), not 0.0, when no plan has demand data."""

    def test_returns_none_when_no_interval_has_demand_detail(self, coordinator):
        _set_service_usage(
            coordinator,
            [
                {"date": "2024-01-01", "import_usage": 10.0, "max_demand_kw": None},
                {"date": "2024-01-02", "import_usage": 12.0, "max_demand_kw": None},
            ],
        )
        assert coordinator.get_max_demand_data("prop-001", SERVICE_TYPE_ELECTRICITY) is None

    def test_validate_usage_entry_accepts_null_max_demand_kw(self):
        """Regression check: None must not blow up validate_usage_entry's float() coercion."""
        entry = {
            "date": "2024-01-01",
            "usage": 10.0,
            "cost": 3.0,
            "import_usage": 10.0,
            "export_usage": 0.0,
            "import_cost": 3.0,
            "export_credit": 0.0,
            "net_cost": 3.0,
            "max_demand_kw": None,
            "carbon_emission_tonne": 0.001,
        }
        validated = validate_usage_entry(entry)
        assert validated.get("max_demand_kw") is None

    def test_returns_actual_value_when_demand_data_present(self, coordinator):
        _set_service_usage(
            coordinator,
            [
                {"date": "2024-01-01", "import_usage": 10.0, "max_demand_kw": None},
                {
                    "date": "2024-01-02",
                    "import_usage": 12.0,
                    "max_demand_kw": 5.2,
                    "max_demand_time": "2024-01-02T18:00:00",
                },
            ],
        )
        result = coordinator.get_max_demand_data("prop-001", SERVICE_TYPE_ELECTRICITY)
        assert result["max_demand_kw"] == 5.2
        assert result["max_demand_date"] == "2024-01-02"


class TestPeakUsageSensorRenamed:
    """Bug #3: sensor formerly named "Peak Usage" should be clearly relabeled."""

    def test_name_no_longer_says_peak_usage(self, coordinator):
        sensor = RedEnergyPeakUsageSensor(
            coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor._attr_name == "Highest Net Usage Day"

    def test_unique_id_unchanged_for_backward_compatibility(self, coordinator):
        sensor = RedEnergyPeakUsageSensor(
            coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor._attr_unique_id.endswith("_peak_usage")


class TestBillingPeriodBoundary:
    """Bug #4: lastBillDate is the last day of the *previous* period and must be excluded."""

    def test_start_date_is_day_after_last_bill_date(self, coordinator):
        last_bill_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        service = {"lastBillDate": last_bill_date}

        start_date, _end_date = coordinator._get_usage_period_dates(service)

        expected_start = datetime.strptime(last_bill_date, "%Y-%m-%d") + timedelta(days=1)
        assert start_date.date() == expected_start.date()

    def test_falls_back_to_30_days_when_last_bill_date_missing(self, coordinator):
        start_date, end_date = coordinator._get_usage_period_dates({})
        assert (end_date - start_date).days == 30


class TestLatestDaySelection:
    """Bug #5: latest-day values should be selected by max usageDate, not list position."""

    def test_selects_max_date_even_when_out_of_order(self, coordinator):
        _set_service_usage(
            coordinator,
            [
                {"date": "2024-01-15", "import_usage": 99.0, "export_usage": 9.0,
                 "import_cost": 20.0, "export_credit": 2.0},
                {"date": "2024-01-10", "import_usage": 5.0, "export_usage": 1.0,
                 "import_cost": 1.5, "export_credit": 0.3},
            ],
        )

        assert coordinator.get_latest_import_usage("prop-001", SERVICE_TYPE_ELECTRICITY) == 99.0
        assert coordinator.get_latest_export_usage("prop-001", SERVICE_TYPE_ELECTRICITY) == 9.0
        assert coordinator.get_latest_import_cost("prop-001", SERVICE_TYPE_ELECTRICITY) == 20.0
        assert coordinator.get_latest_export_credit("prop-001", SERVICE_TYPE_ELECTRICITY) == 2.0
        assert coordinator.get_latest_usage_date("prop-001", SERVICE_TYPE_ELECTRICITY) == "2024-01-15"

    def test_falls_back_to_last_entry_when_dates_missing(self, coordinator):
        _set_service_usage(
            coordinator,
            [
                {"import_usage": 5.0},
                {"import_usage": 42.0},
            ],
        )
        assert coordinator.get_latest_import_usage("prop-001", SERVICE_TYPE_ELECTRICITY) == 42.0

    def test_returns_none_when_no_usage_data(self, coordinator):
        _set_service_usage(coordinator, [])
        assert coordinator.get_latest_import_usage("prop-001", SERVICE_TYPE_ELECTRICITY) is None
        assert coordinator.get_latest_usage_date("prop-001", SERVICE_TYPE_ELECTRICITY) is None

    def test_sensor_exposes_usage_date_attribute(self, coordinator):
        _set_service_usage(
            coordinator,
            [{"date": "2024-01-15", "import_usage": 99.0, "export_usage": 9.0}],
        )
        sensor = RedEnergyDailyImportUsageSensor(
            coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.extra_state_attributes["usage_date"] == "2024-01-15"
