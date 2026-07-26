"""Buttons for Red Energy integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Red Energy buttons from a config entry."""
    entry_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    if not entry_data:
        return

    coordinator = entry_data.get("coordinator")
    if not coordinator:
        return

    # One button per device: the refresh itself is entry-wide (it refreshes
    # every selected account), but each device needs its own button so the
    # action is available no matter which device the user is viewing rather
    # than only the first one.
    selected_accounts = entry_data.get("selected_accounts", [])
    entities: list[ButtonEntity] = [
        RedEnergyRefreshMetadataButton(coordinator, config_entry, account_id)
        for account_id in selected_accounts
    ]

    _LOGGER.debug("About to register %d button entities with Home Assistant", len(entities))
    _LOGGER.debug("Button entity details: %s", [f"{entity.__class__.__name__}({entity.unique_id})" for entity in entities])
    
    try:
        async_add_entities(entities)
        _LOGGER.info("Successfully registered %d button entities with Home Assistant", len(entities))
        
        # Check if entities are actually in the entity registry
        entity_registry = er.async_get(hass)
        red_energy_entities = [entity for entity in entity_registry.entities.values() if entity.platform == DOMAIN]
        _LOGGER.debug("Found %d Red Energy entities in entity registry after button registration: %s", 
                     len(red_energy_entities), 
                     [entity.entity_id for entity in red_energy_entities[:10]])  # Show first 10
        
    except Exception as err:
        _LOGGER.error("Failed to register button entities with Home Assistant: %s", err, exc_info=True)


class RedEnergyRefreshMetadataButton(ButtonEntity):
    """Button to trigger full metadata refresh and data update.

    The refresh itself is entry-wide (every selected account is refreshed
    together), but one instance of this button is created per account/device
    so the action is available regardless of which device is being viewed.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry: ConfigEntry, account_id: str) -> None:
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._attr_name = "Refresh metadata"
        self._attr_unique_id = f"{config_entry.entry_id}_{account_id}_refresh_metadata"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, account_id)},
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Manual metadata refresh button pressed for entry %s", self._config_entry.entry_id)
        await self._coordinator.async_refresh_metadata_and_usage()


