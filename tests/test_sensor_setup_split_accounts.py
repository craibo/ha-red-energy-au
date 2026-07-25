"""Test sensor platform setup does not cross-create entities for split accounts."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.red_energy.const import DOMAIN, SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS
from custom_components.red_energy.sensor import async_setup_entry


def _coordinator_for_split_accounts():
    coordinator = MagicMock()
    coordinator.data = {
        "usage_data": {
            "8490263": {
                "property": {
                    "name": "27 Sunnyside Crescent, Castlecrag",
                    "services": [{"type": SERVICE_TYPE_ELECTRICITY, "consumer_number": "elec-1"}],
                },
            },
            "7471493": {
                "property": {
                    "name": "27 Sunnyside Crescent, Castlecrag",
                    "services": [{"type": SERVICE_TYPE_GAS, "consumer_number": "gas-1"}],
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
async def test_no_electricity_entities_created_for_gas_only_account():
    """A gas-only account must not get electricity sensors, and vice versa."""
    coordinator = _coordinator_for_split_accounts()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["8490263", "7471493"],
                "services": [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    for entity in added_entities:
        if entity._property_id == "8490263":
            assert entity._service_type == SERVICE_TYPE_ELECTRICITY
        elif entity._property_id == "7471493":
            assert entity._service_type == SERVICE_TYPE_GAS

    assert any(e._property_id == "8490263" for e in added_entities)
    assert any(e._property_id == "7471493" for e in added_entities)
