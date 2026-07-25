"""Test usage-dependent sensors default to disabled for BASIC/manual-read meters."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.red_energy.const import DOMAIN, SERVICE_TYPE_GAS, SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import async_setup_entry


def _coordinator_for_basic_gas_meter():
    coordinator = MagicMock()
    coordinator.data = {
        "usage_data": {
            "7471493": {
                "property": {
                    "name": "27 Sunnyside Crescent, Castlecrag",
                    "services": [
                        {
                            "type": SERVICE_TYPE_GAS,
                            "consumer_number": "gas-1",
                            "meterType": "BASIC",
                        }
                    ],
                },
            },
        }
    }
    coordinator.last_update_success = True

    def get_service_metadata(property_id, service_type):
        property_data = coordinator.data["usage_data"].get(str(property_id))
        if not property_data:
            return None
        services = property_data["property"].get("services", [])
        return next((s for s in services if s.get("type") == service_type), None)

    coordinator.get_service_metadata = MagicMock(side_effect=get_service_metadata)
    coordinator.get_service_usage = MagicMock(return_value=None)
    return coordinator


def _coordinator_for_interval_electricity_meter():
    coordinator = MagicMock()
    coordinator.data = {
        "usage_data": {
            "8490263": {
                "property": {
                    "name": "27 Sunnyside Crescent, Castlecrag",
                    "services": [
                        {
                            "type": SERVICE_TYPE_ELECTRICITY,
                            "consumer_number": "elec-1",
                            "meterType": "INTERVAL",
                        }
                    ],
                },
            },
        }
    }
    coordinator.last_update_success = True

    def get_service_metadata(property_id, service_type):
        property_data = coordinator.data["usage_data"].get(str(property_id))
        if not property_data:
            return None
        services = property_data["property"].get("services", [])
        return next((s for s in services if s.get("type") == service_type), None)

    coordinator.get_service_metadata = MagicMock(side_effect=get_service_metadata)
    coordinator.get_service_usage = MagicMock(return_value=None)
    return coordinator


@pytest.mark.asyncio
async def test_basic_meter_usage_sensors_disabled_by_default():
    """Usage-dependent sensors for a BASIC meter must be disabled by default."""
    coordinator = _coordinator_for_basic_gas_meter()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["7471493"],
                "services": [SERVICE_TYPE_GAS],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    assert added_entities, "Expected entities to be created"
    for entity in added_entities:
        if entity._requires_usage_data:
            assert entity._attr_entity_registry_enabled_default is False, (
                f"{entity.__class__.__name__} should default to disabled for a BASIC meter"
            )
        else:
            assert getattr(entity, "_attr_entity_registry_enabled_default", True) is True, (
                f"{entity.__class__.__name__} (metadata-only) should stay enabled"
            )


@pytest.mark.asyncio
async def test_interval_meter_usage_sensors_stay_enabled():
    """Usage-dependent sensors for a normal INTERVAL meter must stay enabled."""
    coordinator = _coordinator_for_interval_electricity_meter()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["8490263"],
                "services": [SERVICE_TYPE_ELECTRICITY],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    assert added_entities, "Expected entities to be created"
    for entity in added_entities:
        assert getattr(entity, "_attr_entity_registry_enabled_default", True) is True, (
            f"{entity.__class__.__name__} should stay enabled for an INTERVAL meter"
        )
