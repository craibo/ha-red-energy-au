"""Test electricity-only sensor gating, new diagnostic sensors, and attributes."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.red_energy.const import DOMAIN, SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS
from custom_components.red_energy.sensor import (
    RedEnergyAddressSensor,
    RedEnergyMaxDemandTimeSensor,
    RedEnergyPaymentTypeSensor,
    RedEnergyProductNameSensor,
    RedEnergySolarSensor,
    async_setup_entry,
)

GAS_SERVICE_METADATA = {
    "type": SERVICE_TYPE_GAS,
    "consumer_number": "gas-1",
    "meterType": "INTERVAL",
    "solar": False,
    "paymentTypeDescription": "DirectDebit Bank",
    "promotionDesc": "Qantas Red Saver, 2 QFF Points per $1",
    "latitude": -33.799045,
    "longitude": 151.212185,
}

ELECTRICITY_SERVICE_METADATA = {
    "type": SERVICE_TYPE_ELECTRICITY,
    "consumer_number": "elec-1",
    "meterType": "INTERVAL",
    "solar": True,
    "paymentTypeDescription": "DirectDebit Bank",
    "promotionDesc": "Qantas Red Saver, 2 QFF Points per $1",
}


def _coordinator(service_metadata, service_type):
    coordinator = MagicMock()
    coordinator.data = {
        "usage_data": {
            "2000002": {
                "property": {
                    "name": "1 Example Street, Testville",
                    "address": {
                        "street": "1 Example Street",
                        "city": "Testville",
                        "state": "NSW",
                        "postcode": "2068",
                    },
                    "services": [service_metadata],
                },
            },
        }
    }
    coordinator.last_update_success = True
    coordinator.get_property_data = MagicMock(
        side_effect=lambda pid: coordinator.data["usage_data"].get(str(pid))
    )

    def get_service_metadata(property_id, svc_type):
        property_data = coordinator.data["usage_data"].get(str(property_id))
        if not property_data:
            return None
        services = property_data["property"].get("services", [])
        return next((s for s in services if s.get("type") == svc_type), None)

    coordinator.get_service_metadata = MagicMock(side_effect=get_service_metadata)
    coordinator.get_service_usage = MagicMock(return_value=None)
    return coordinator


@pytest.mark.asyncio
async def test_electricity_only_sensors_not_created_for_gas_account():
    """Solar, export, ToU breakdown, demand, carbon emission, efficiency must not exist for gas."""
    coordinator = _coordinator(GAS_SERVICE_METADATA, SERVICE_TYPE_GAS)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {"enable_advanced_sensors": True}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["2000002"],
                "services": [SERVICE_TYPE_GAS],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    electricity_only_present = [e for e in added_entities if e._electricity_only]
    assert electricity_only_present == [], (
        f"Electricity-only sensors created for gas account: "
        f"{[e.__class__.__name__ for e in electricity_only_present]}"
    )
    assert not any(isinstance(e, RedEnergySolarSensor) for e in added_entities)


@pytest.mark.asyncio
async def test_electricity_only_sensors_created_for_electricity_account():
    """The same sensors must still exist for an electricity account."""
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {"enable_advanced_sensors": True}

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

    assert any(isinstance(e, RedEnergySolarSensor) for e in added_entities)


@pytest.mark.asyncio
async def test_max_demand_time_disabled_by_default():
    """The Max Demand Interval Start sensor must default to disabled."""
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {"enable_advanced_sensors": True}

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

    max_demand_time = next(e for e in added_entities if isinstance(e, RedEnergyMaxDemandTimeSensor))
    assert max_demand_time._attr_entity_registry_enabled_default is False


def test_address_sensor_formats_full_address():
    coordinator = _coordinator(GAS_SERVICE_METADATA, SERVICE_TYPE_GAS)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyAddressSensor(coordinator, config_entry, "2000002", SERVICE_TYPE_GAS)

    assert sensor.native_value == "1 Example Street, Testville NSW 2068"


def test_address_sensor_exposes_latitude_longitude_attributes():
    """Lat/long must be exposed as entity attributes so the address can be plotted on a map."""
    coordinator = _coordinator(GAS_SERVICE_METADATA, SERVICE_TYPE_GAS)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyAddressSensor(coordinator, config_entry, "2000002", SERVICE_TYPE_GAS)

    assert sensor.extra_state_attributes == {
        "latitude": -33.799045,
        "longitude": 151.212185,
    }


def test_payment_type_sensor_returns_description():
    coordinator = _coordinator(GAS_SERVICE_METADATA, SERVICE_TYPE_GAS)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyPaymentTypeSensor(coordinator, config_entry, "2000002", SERVICE_TYPE_GAS)

    assert sensor.native_value == "DirectDebit Bank"


def test_energy_plan_sensor_exposes_promotion_desc_attribute():
    coordinator = _coordinator(GAS_SERVICE_METADATA, SERVICE_TYPE_GAS)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyProductNameSensor(coordinator, config_entry, "2000002", SERVICE_TYPE_GAS)

    assert sensor.extra_state_attributes == {
        "promotion_description": "Qantas Red Saver, 2 QFF Points per $1"
    }
