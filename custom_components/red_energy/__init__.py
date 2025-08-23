"""The Red Energy integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_CLIENT_ID,
    DATA_SELECTED_ACCOUNTS,
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
)
from .coordinator import RedEnergyDataCoordinator
from .services import async_setup_services, async_unload_services

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Red Energy from a config entry."""
    _LOGGER.debug("Setting up Red Energy integration for entry %s", entry.entry_id)
    
    # Extract configuration
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    client_id = entry.data[CONF_CLIENT_ID]
    selected_accounts = entry.data.get(DATA_SELECTED_ACCOUNTS, [])
    services = entry.data.get("services", [SERVICE_TYPE_ELECTRICITY])
    
    _LOGGER.debug(
        "Configuration: username=%s, accounts=%s, services=%s",
        username,
        selected_accounts,
        services
    )
    
    # Create data coordinator
    coordinator = RedEnergyDataCoordinator(
        hass, username, password, client_id, selected_accounts, services
    )
    
    # Test initial data fetch
    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        _LOGGER.error("Failed to set up Red Energy integration: %s", err)
        raise ConfigEntryNotReady(f"Failed to connect to Red Energy: {err}") from err
    
    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "username": username,
        "selected_accounts": selected_accounts,
        "services": services,
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Set up services (only once for the first entry)
    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)
    
    _LOGGER.info(
        "Red Energy integration setup complete for %s accounts with %s services",
        len(selected_accounts),
        len(services)
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Red Energy integration for entry %s", entry.entry_id)
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Clean up stored data
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        
        # Stop coordinator
        if "coordinator" in entry_data:
            coordinator = entry_data["coordinator"]
            # The coordinator will be garbage collected
            
        # Remove domain data if empty
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            # Unload services when last integration is removed
            await async_unload_services(hass)
        
        _LOGGER.debug("Red Energy integration unloaded successfully")
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)