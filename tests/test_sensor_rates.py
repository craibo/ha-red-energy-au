"""Test dynamic per-rate diagnostic sensors."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.helpers.entity import EntityCategory

from custom_components.red_energy.const import DOMAIN, SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS
from custom_components.red_energy.sensor import (
    RedEnergyRateSensor,
    async_setup_entry,
)

ELECTRICITY_RATES = [
    {
        "rate_code": "80008279798P",
        "rate_desc": "Peak",
        "rate_incl_gst_dollars": 0.27005,
        "type": "PR",
        "rate_excl_gst_cents": 24.55,
        "discounted_rate_excl_gst_in_cents": 24.55,
        "discounted_rate_incl_gst_in_cents": 27.005,
        "unit": "kWh",
        "unit_step_desc": None,
    },
    {
        "rate_code": "80008279798GP",
        "rate_desc": "Solar",
        "rate_incl_gst_dollars": -0.04,
        "type": "PR",
        "rate_excl_gst_cents": -3.6364,
        "discounted_rate_excl_gst_in_cents": -3.6364,
        "discounted_rate_incl_gst_in_cents": -4,
        "unit": "kWh",
        "unit_step_desc": None,
    },
]

GAS_TIERED_RATES = [
    {
        "rate_code": "10009300825P",
        "rate_desc": "Anytime Step1",
        "rate_incl_gst_dollars": 0.0495,
        "type": "PSR1",
        "rate_excl_gst_cents": 4.5,
        "discounted_rate_excl_gst_in_cents": 4.5,
        "discounted_rate_incl_gst_in_cents": 4.95,
        "unit": "MJ",
        "unit_step_desc": "First 20.712 / day",
    },
    {
        "rate_code": "10009300825P",
        "rate_desc": "Anytime Step2",
        "rate_incl_gst_dollars": 0.0363,
        "type": "PSR1",
        "rate_excl_gst_cents": 3.3,
        "discounted_rate_excl_gst_in_cents": 3.3,
        "discounted_rate_incl_gst_in_cents": 3.63,
        "unit": "MJ",
        "unit_step_desc": "Next 20.384 / day",
    },
]

ELECTRICITY_SERVICE_METADATA = {
    "type": SERVICE_TYPE_ELECTRICITY,
    "consumer_number": "elec-1",
    "meterType": "INTERVAL",
    "solar": True,
    "rates": ELECTRICITY_RATES,
}

GAS_SERVICE_METADATA = {
    "type": SERVICE_TYPE_GAS,
    "consumer_number": "gas-1",
    "meterType": "BASIC",
    "solar": False,
    "rates": GAS_TIERED_RATES,
}


def _coordinator(service_metadata, service_type, property_id="2000002"):
    coordinator = MagicMock()
    coordinator.data = {
        "usage_data": {
            property_id: {
                "property": {
                    "name": "Test property",
                    "address": {},
                    "services": [service_metadata],
                },
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
async def test_one_rate_sensor_created_per_rate_entry():
    """async_setup_entry must create one RedEnergyRateSensor per rate in the service."""
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
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

    rate_sensors = [e for e in added_entities if isinstance(e, RedEnergyRateSensor)]
    assert len(rate_sensors) == 2
    names = {s._attr_name for s in rate_sensors}
    assert names == {"Peak", "Solar"}


@pytest.mark.asyncio
async def test_duplicate_rate_code_tiered_gas_rates_produce_distinct_entities():
    """Tiered gas rates sharing a rateCode must still produce distinct, uniquely-identified entities."""
    coordinator = _coordinator(GAS_SERVICE_METADATA, SERVICE_TYPE_GAS)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

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

    rate_sensors = [e for e in added_entities if isinstance(e, RedEnergyRateSensor)]
    assert len(rate_sensors) == 2
    unique_ids = {s.unique_id for s in rate_sensors}
    assert len(unique_ids) == 2
    names = {s._attr_name for s in rate_sensors}
    assert names == {"Anytime Step1", "Anytime Step2"}


def test_rate_sensor_native_value_and_attributes():
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyRateSensor(
        coordinator, config_entry, "2000002", SERVICE_TYPE_ELECTRICITY, ELECTRICITY_RATES[0]
    )

    assert sensor.native_value == pytest.approx(0.27005)
    assert sensor._attr_name == "Peak"
    assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC
    assert sensor._attr_device_class.value == "monetary"

    attrs = sensor.extra_state_attributes
    assert attrs["rate_code"] == "80008279798P"
    assert attrs["type"] == "PR"
    assert attrs["unit"] == "kWh"
    assert "rate_incl_gst_dollars" not in attrs


def test_rate_sensor_handles_negative_solar_value():
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyRateSensor(
        coordinator, config_entry, "2000002", SERVICE_TYPE_ELECTRICITY, ELECTRICITY_RATES[1]
    )

    assert sensor.native_value == pytest.approx(-0.04)


def test_rate_sensor_returns_none_when_rate_no_longer_present():
    """If the rate disappears from coordinator data (e.g. plan change before reload), native_value is None."""
    coordinator = _coordinator(ELECTRICITY_SERVICE_METADATA, SERVICE_TYPE_ELECTRICITY)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    sensor = RedEnergyRateSensor(
        coordinator, config_entry, "2000002", SERVICE_TYPE_ELECTRICITY,
        {"rate_code": "gone", "rate_desc": "Gone Rate", "rate_incl_gst_dollars": 1.0},
    )

    assert sensor.native_value is None
    assert sensor.extra_state_attributes is None
