"""Tests for Daily Service Charge and Billing Period Service Charge sensors (issue #71)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import (
    RedEnergyDailyServiceChargeSensor,
    RedEnergyBillingPeriodServiceChargeSensor,
)

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

ENERGY_RATE = {
    "rate_code": "80008279798P",
    "rate_desc": "Peak",
    "rate_incl_gst_dollars": 0.27005,
    "type": "PR",
    "rate_excl_gst_cents": 24.55,
    "discounted_rate_excl_gst_in_cents": 24.55,
    "discounted_rate_incl_gst_in_cents": 27.005,
    "unit": "kWh",
    "unit_step_desc": None,
}

SECOND_SUPPLY_CHARGE_RATE = {
    "rate_code": "80008279798S2",
    "rate_desc": "Second Daily Supply Charge",
    "rate_incl_gst_dollars": 0.5,
    "type": "SC",
    "rate_excl_gst_cents": 45.45,
    "discounted_rate_excl_gst_in_cents": 45.45,
    "discounted_rate_incl_gst_in_cents": 50.0,
    "unit": "day",
    "unit_step_desc": None,
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
            selected_accounts=["2000002"],
            services=["electricity"],
        )
    coord.api = AsyncMock()
    coord.api._access_token = "test_token"
    return coord


def _set_coordinator_data(coordinator, rates, usage_entries=None, last_bill_date=None):
    """Build coordinator.data with both the property.services (metadata/rates)
    and top-level services (usage) shapes get_service_metadata/get_service_usage expect."""
    service_metadata = {
        "type": SERVICE_TYPE_ELECTRICITY,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": rates,
    }
    if last_bill_date is not None:
        service_metadata["lastBillDate"] = last_bill_date

    services_usage = {}
    if usage_entries is not None:
        services_usage[SERVICE_TYPE_ELECTRICITY] = {
            "consumer_number": "elec-1",
            "last_updated": "2024-01-30T10:00:00",
            "usage_data": {
                "from_date": "2024-01-01",
                "to_date": "2024-01-30",
                "usage_data": usage_entries,
            },
        }

    coordinator.data = {
        "usage_data": {
            "2000002": {
                "property": {
                    "name": "Test property",
                    "address": {},
                    "services": [service_metadata],
                },
                "services": services_usage,
            },
        }
    }


class TestFindServiceChargeRate:
    def test_returns_none_when_no_rates(self, coordinator):
        _set_coordinator_data(coordinator, [])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_no_sc_day_rate(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_finds_the_sc_day_rate_among_others(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE, SUPPLY_CHARGE_RATE])
        result = coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == SUPPLY_CHARGE_RATE

    def test_uses_first_match_when_multiple_sc_day_rates(self, coordinator):
        _set_coordinator_data(coordinator, [SUPPLY_CHARGE_RATE, SECOND_SUPPLY_CHARGE_RATE])
        result = coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == SUPPLY_CHARGE_RATE

    def test_type_sc_without_day_unit_does_not_match(self, coordinator):
        rate = {**SUPPLY_CHARGE_RATE, "unit": "kWh"}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_day_unit_without_type_sc_does_not_match(self, coordinator):
        rate = {**SUPPLY_CHARGE_RATE, "type": "PR"}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None


class TestGetDailyServiceCharge:
    def test_returns_rate_incl_gst_dollars(self, coordinator):
        _set_coordinator_data(coordinator, [SUPPLY_CHARGE_RATE])
        assert coordinator.get_daily_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) == pytest.approx(1.78145)

    def test_returns_none_when_no_matching_rate(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE])
        assert coordinator.get_daily_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None


class TestGetBillingPeriodServiceCharge:
    def test_seven_day_period_matches_issue_example(self, coordinator):
        last_bill_date = "2025-07-25"
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date=last_bill_date,
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == pytest.approx(7 * 1.78145)

    def test_returns_none_when_no_matching_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [ENERGY_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_no_usage_data(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_latest_usage_date_before_period_start(self, coordinator):
        """Stale/cached usage predating a just-rolled billing period must not produce a negative day count."""
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-07-20", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_falls_back_to_30_day_period_when_last_bill_date_missing(self, coordinator):
        today = datetime.now()
        latest_usage_date = today.strftime("%Y-%m-%d")
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": latest_usage_date, "import_usage": 10.0}],
            last_bill_date=None,
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        expected_days = (today.date() - (today - timedelta(days=30)).date()).days + 1
        assert result == pytest.approx(expected_days * 1.78145)

    def test_single_day_period_counts_as_one_day(self, coordinator):
        """lastBillDate + 1 == latest usageDate must count as exactly 1 day, not 0."""
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-07-26", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == pytest.approx(1 * 1.78145)


from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


class TestDailyServiceChargeSensor:
    def test_native_value_and_metadata(self, coordinator):
        _set_coordinator_data(coordinator, [SUPPLY_CHARGE_RATE])
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value == pytest.approx(1.78145)
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class == SensorStateClass.TOTAL

    def test_native_value_none_when_no_rate(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE])
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None

    def test_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
        )
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        attrs = sensor.extra_state_attributes
        assert attrs["usage_date"] == "2025-08-01"
        assert attrs["service_rate_incl_gst"] == pytest.approx(1.78145)
        assert attrs["service_rate_excl_gst"] == pytest.approx(1.6195)
        assert attrs["represented_day_count"] == 1
        assert "calculation" in attrs

    def test_last_reset_is_latest_usage_date(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
        )
        sensor = RedEnergyDailyServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.last_reset.date().isoformat() == "2025-08-01"


class TestBillingPeriodServiceChargeSensor:
    def test_native_value_and_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value == pytest.approx(7 * 1.78145)
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class == SensorStateClass.TOTAL

        attrs = sensor.extra_state_attributes
        assert attrs["billing_period_start"] == "2025-07-26"
        assert attrs["billing_period_end"] == "2025-08-01"
        assert attrs["latest_usage_date"] == "2025-08-01"
        assert attrs["represented_day_count"] == 7
        assert attrs["service_rate_incl_gst"] == pytest.approx(1.78145)
        assert attrs["service_rate_excl_gst"] == pytest.approx(1.6195)
        assert "calculation" in attrs

    def test_native_value_none_when_no_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [ENERGY_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None

    def test_last_reset_is_billing_period_start(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.last_reset.date().isoformat() == "2025-07-26"


from custom_components.red_energy.const import DOMAIN, CONF_ENABLE_ADVANCED_SENSORS, SERVICE_TYPE_GAS
from custom_components.red_energy.sensor import async_setup_entry


def _mock_coordinator_for_setup(rates, service_type=SERVICE_TYPE_ELECTRICITY, property_id="2000002"):
    coordinator = MagicMock()
    service_metadata = {
        "type": service_type,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": rates,
    }
    coordinator.data = {
        "usage_data": {
            property_id: {
                "property": {"name": "Test property", "address": {}, "services": [service_metadata]},
                "services": {},
            },
        }
    }
    coordinator.last_update_success = True
    coordinator.get_property_data = MagicMock(
        side_effect=lambda pid: coordinator.data["usage_data"].get(str(pid))
    )

    def get_service_metadata(prop_id, svc_type):
        property_data = coordinator.data["usage_data"].get(str(prop_id))
        if not property_data:
            return None
        services = property_data["property"].get("services", [])
        return next((s for s in services if s.get("type") == svc_type), None)

    coordinator.get_service_metadata = MagicMock(side_effect=get_service_metadata)

    def get_service_rates(prop_id, svc_type):
        metadata = get_service_metadata(prop_id, svc_type)
        return metadata.get("rates", []) if metadata else []

    coordinator.get_service_rates = MagicMock(side_effect=get_service_rates)
    coordinator.get_service_usage = MagicMock(return_value=None)
    return coordinator


@pytest.mark.asyncio
async def test_service_charge_sensors_not_created_when_advanced_disabled():
    coordinator = _mock_coordinator_for_setup([SUPPLY_CHARGE_RATE])
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["2000002"],
                "services": [SERVICE_TYPE_ELECTRICITY],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))
    await async_setup_entry(hass, config_entry, async_add_entities)

    charge_sensors = [
        e for e in added_entities
        if isinstance(e, (RedEnergyDailyServiceChargeSensor, RedEnergyBillingPeriodServiceChargeSensor))
    ]
    assert charge_sensors == []


@pytest.mark.asyncio
async def test_service_charge_sensors_created_for_electricity_and_gas_when_advanced_enabled():
    coordinator = _mock_coordinator_for_setup([SUPPLY_CHARGE_RATE], service_type=SERVICE_TYPE_ELECTRICITY)
    gas_coordinator_data = coordinator.data["usage_data"]["2000002"]["property"]["services"]
    gas_coordinator_data.append({**gas_coordinator_data[0], "type": SERVICE_TYPE_GAS})

    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {CONF_ENABLE_ADVANCED_SENSORS: True}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["2000002"],
                "services": [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))
    await async_setup_entry(hass, config_entry, async_add_entities)

    daily_charge_sensors = [e for e in added_entities if isinstance(e, RedEnergyDailyServiceChargeSensor)]
    billing_charge_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyBillingPeriodServiceChargeSensor)
    ]
    assert len(daily_charge_sensors) == 2
    assert len(billing_charge_sensors) == 2
