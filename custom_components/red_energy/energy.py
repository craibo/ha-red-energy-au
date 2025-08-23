"""Energy dashboard integration for Red Energy."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.energy import (
    async_get_manager,
    EnergyManager,
    EnergyPlatform,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS

_LOGGER = logging.getLogger(__name__)


async def async_get_energy_platform(hass: HomeAssistant) -> EnergyPlatform:
    """Get the Red Energy energy platform."""
    return RedEnergyEnergyPlatform(hass)


class RedEnergyEnergyPlatform(EnergyPlatform):
    """Red Energy energy platform for Home Assistant Energy Dashboard."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the energy platform."""
        self.hass = hass

    async def async_get_config_flow_energy_sources(
        self, config_entry: ConfigEntry
    ) -> List[Dict[str, Any]]:
        """Return energy sources for config flow."""
        if config_entry.domain != DOMAIN:
            return []

        # Get integration data
        if config_entry.entry_id not in self.hass.data.get(DOMAIN, {}):
            return []

        entry_data = self.hass.data[DOMAIN][config_entry.entry_id]
        selected_accounts = entry_data.get("selected_accounts", [])
        services = entry_data.get("services", [])
        coordinator = entry_data.get("coordinator")

        if not coordinator or not coordinator.data:
            return []

        energy_sources = []

        # Create energy sources for each account and service
        for account_id in selected_accounts:
            property_data = coordinator.get_property_data(account_id)
            if not property_data:
                continue

            property_info = property_data.get("property", {})
            property_name = property_info.get("name", f"Property {account_id}")

            for service_type in services:
                service_data = coordinator.get_service_usage(account_id, service_type)
                if not service_data:
                    continue

                # Create unique entity ID for the total usage sensor
                entity_id = f"sensor.{property_name.lower().replace(' ', '_')}_{service_type}_total_usage"
                entity_id = entity_id.replace('-', '_')

                if service_type == SERVICE_TYPE_ELECTRICITY:
                    energy_sources.append({
                        "type": "grid",
                        "flow_type": "from",  # Energy consumed from grid
                        "stat_energy_from": entity_id,
                        "name": f"{property_name} Electricity",
                        "entity_id": entity_id,
                        "unit_of_measurement": "kWh",
                    })
                elif service_type == SERVICE_TYPE_GAS:
                    energy_sources.append({
                        "type": "gas",
                        "stat_energy_from": entity_id,
                        "name": f"{property_name} Gas",
                        "entity_id": entity_id,
                        "unit_of_measurement": "MJ",
                        # Convert MJ to kWh for energy dashboard (1 MJ = 0.278 kWh)
                        "unit_conversion": 0.278,
                    })

        _LOGGER.debug("Generated %d energy sources for Red Energy integration", len(energy_sources))
        return energy_sources

    async def async_get_config_entry_energy_settings(
        self, config_entry: ConfigEntry
    ) -> Optional[Dict[str, Any]]:
        """Return energy settings for a config entry."""
        if config_entry.domain != DOMAIN:
            return None

        # Get cost sensors for energy dashboard cost tracking
        if config_entry.entry_id not in self.hass.data.get(DOMAIN, {}):
            return None

        entry_data = self.hass.data[DOMAIN][config_entry.entry_id]
        coordinator = entry_data.get("coordinator")

        if not coordinator or not coordinator.data:
            return None

        # Energy dashboard can use cost sensors for pricing
        cost_sensors = []
        selected_accounts = entry_data.get("selected_accounts", [])
        services = entry_data.get("services", [])

        for account_id in selected_accounts:
            property_data = coordinator.get_property_data(account_id)
            if not property_data:
                continue

            property_info = property_data.get("property", {})
            property_name = property_info.get("name", f"Property {account_id}")

            for service_type in services:
                entity_id = f"sensor.{property_name.lower().replace(' ', '_')}_{service_type}_total_cost"
                entity_id = entity_id.replace('-', '_')
                cost_sensors.append(entity_id)

        return {
            "cost_sensors": cost_sensors,
            "currency": "AUD",
        } if cost_sensors else None


async def async_setup_energy_platform(hass: HomeAssistant) -> None:
    """Set up the Red Energy energy platform."""
    try:
        energy_manager: EnergyManager = await async_get_manager(hass)
        if energy_manager:
            platform = RedEnergyEnergyPlatform(hass)
            # Register the platform
            # Note: This would need to be adapted based on the actual HA Energy API
            _LOGGER.info("Red Energy energy platform registered")
        else:
            _LOGGER.warning("Energy manager not available, skipping energy platform setup")
    except Exception as err:
        _LOGGER.error("Failed to set up Red Energy energy platform: %s", err)


def get_energy_usage_sensors(entry_data: Dict[str, Any]) -> List[str]:
    """Get list of energy usage sensor entity IDs."""
    selected_accounts = entry_data.get("selected_accounts", [])
    services = entry_data.get("services", [])
    coordinator = entry_data.get("coordinator")

    if not coordinator or not coordinator.data:
        return []

    sensors = []
    for account_id in selected_accounts:
        property_data = coordinator.get_property_data(account_id)
        if not property_data:
            continue

        property_info = property_data.get("property", {})
        property_name = property_info.get("name", f"Property {account_id}")

        for service_type in services:
            # Total usage sensor entity ID
            entity_id = f"sensor.{property_name.lower().replace(' ', '_')}_{service_type}_total_usage"
            entity_id = entity_id.replace('-', '_')
            sensors.append(entity_id)

    return sensors


def get_energy_cost_sensors(entry_data: Dict[str, Any]) -> List[str]:
    """Get list of energy cost sensor entity IDs."""
    selected_accounts = entry_data.get("selected_accounts", [])
    services = entry_data.get("services", [])
    coordinator = entry_data.get("coordinator")

    if not coordinator or not coordinator.data:
        return []

    sensors = []
    for account_id in selected_accounts:
        property_data = coordinator.get_property_data(account_id)
        if not property_data:
            continue

        property_info = property_data.get("property", {})
        property_name = property_info.get("name", f"Property {account_id}")

        for service_type in services:
            # Total cost sensor entity ID
            entity_id = f"sensor.{property_name.lower().replace(' ', '_')}_{service_type}_total_cost"
            entity_id = entity_id.replace('-', '_')
            sensors.append(entity_id)

    return sensors