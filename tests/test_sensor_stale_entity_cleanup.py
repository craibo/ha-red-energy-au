"""Test that sensor setup removes entities no longer produced by config."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.red_energy.const import DOMAIN, SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import async_setup_entry


def _coordinator_for_single_account():
    coordinator = MagicMock()
    coordinator.data = {
        "usage_data": {
            "1000001": {
                "property": {
                    "name": "27 Sunnyside Crescent, Castlecrag",
                    "services": [{"type": SERVICE_TYPE_ELECTRICITY, "consumer_number": "elec-1"}],
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


def _registry_entry(entity_id, unique_id):
    entry = MagicMock()
    entry.entity_id = entity_id
    entry.unique_id = unique_id
    entry.platform = DOMAIN
    return entry


@pytest.mark.asyncio
async def test_stale_entity_removed_when_no_longer_produced():
    """An entity from a prior configuration (e.g. a deselected account) must be removed.

    HA never auto-purges entities that are merely "Unavailable" - they stay
    in the registry forever unless something explicitly removes them. Since
    the underlying device is untouched by an account/service deselection,
    device-based orphan cleanup won't catch these either.
    """
    coordinator = _coordinator_for_single_account()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["1000001"],
                "services": [SERVICE_TYPE_ELECTRICITY],
            }
        }
    }

    stale_entity = _registry_entry(
        "sensor.stale_gas_entity",
        "red_energy_entry1_2000002_gas_total_cost",
    )

    mock_registry = MagicMock()
    mock_registry.entities.values.return_value = [stale_entity]
    mock_registry.async_remove = MagicMock()

    async_add_entities = MagicMock()

    with patch(
        "custom_components.red_energy.sensor.er.async_get", return_value=mock_registry
    ), patch(
        "custom_components.red_energy.sensor.er.async_entries_for_config_entry",
        return_value=[stale_entity],
    ):
        await async_setup_entry(hass, config_entry, async_add_entities)

    mock_registry.async_remove.assert_called_once_with("sensor.stale_gas_entity")


@pytest.mark.asyncio
async def test_current_entity_not_removed():
    """An entity that matches the current configuration must be left alone."""
    coordinator = _coordinator_for_single_account()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["1000001"],
                "services": [SERVICE_TYPE_ELECTRICITY],
            }
        }
    }

    async_add_entities = MagicMock()
    created_entities = []
    async_add_entities.side_effect = lambda entities: created_entities.extend(entities)

    mock_registry = MagicMock()
    mock_registry.entities.values.return_value = []
    mock_registry.async_remove = MagicMock()

    with patch(
        "custom_components.red_energy.sensor.er.async_get", return_value=mock_registry
    ), patch(
        "custom_components.red_energy.sensor.er.async_entries_for_config_entry",
        side_effect=lambda registry, entry_id: [
            _registry_entry(f"sensor.{e.unique_id}", e.unique_id) for e in created_entities
        ],
    ):
        await async_setup_entry(hass, config_entry, async_add_entities)

    mock_registry.async_remove.assert_not_called()
