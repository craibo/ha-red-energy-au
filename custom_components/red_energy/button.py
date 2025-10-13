"""Buttons for Red Energy integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

    entities: list[ButtonEntity] = []
    entities.append(RedEnergyRefreshMetadataButton(coordinator, config_entry))

    _LOGGER.info("About to register %d button entities with Home Assistant", len(entities))
    try:
        async_add_entities(entities)
        _LOGGER.info("Successfully registered %d button entities with Home Assistant", len(entities))
    except Exception as err:
        _LOGGER.error("Failed to register button entities with Home Assistant: %s", err, exc_info=True)


class RedEnergyRefreshMetadataButton(ButtonEntity):
    """Button to trigger full metadata refresh and data update."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._attr_name = "Refresh metadata"
        self._attr_unique_id = f"{config_entry.entry_id}_refresh_metadata"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Manual metadata refresh button pressed for entry %s", self._config_entry.entry_id)
        await self._coordinator.async_refresh_metadata_and_usage()


