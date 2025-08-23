"""Red Energy sensor platform."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Red Energy sensor based on a config entry."""
    _LOGGER.debug("Setting up Red Energy sensors for config entry %s", config_entry.entry_id)
    
    async_add_entities([RedEnergySensor(config_entry)])


class RedEnergySensor(SensorEntity):
    """Representation of a Red Energy sensor."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._config_entry = config_entry
        self._attr_name = "Red Energy Test Sensor"
        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}_test"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return "Integration loaded successfully"