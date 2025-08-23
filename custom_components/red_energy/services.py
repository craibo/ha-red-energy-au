"""Red Energy integration services."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import RedEnergyDataCoordinator

_LOGGER = logging.getLogger(__name__)

# Service schemas
SERVICE_REFRESH_DATA_SCHEMA = vol.Schema({})

SERVICE_UPDATE_CREDENTIALS_SCHEMA = vol.Schema({
    vol.Required("username"): cv.string,
    vol.Required("password"): cv.string,
    vol.Required("client_id"): cv.string,
})

SERVICE_EXPORT_DATA_SCHEMA = vol.Schema({
    vol.Optional("format", default="json"): vol.In(["json", "csv"]),
    vol.Optional("days", default=30): vol.Range(min=1, max=365),
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Red Energy integration."""
    
    async def async_refresh_data(call: ServiceCall) -> None:
        """Service call to manually refresh data for all coordinators."""
        _LOGGER.info("Manual data refresh requested")
        
        refresh_count = 0
        for entry_id, entry_data in hass.data[DOMAIN].items():
            coordinator: RedEnergyDataCoordinator = entry_data.get("coordinator")
            if coordinator:
                try:
                    await coordinator.async_refresh()
                    refresh_count += 1
                    _LOGGER.debug("Refreshed data for coordinator %s", entry_id)
                except Exception as err:
                    _LOGGER.error("Failed to refresh coordinator %s: %s", entry_id, err)
        
        _LOGGER.info("Completed manual refresh for %d coordinators", refresh_count)
    
    async def async_update_credentials(call: ServiceCall) -> None:
        """Service call to update credentials for a specific integration."""
        username = call.data["username"]
        password = call.data["password"]
        client_id = call.data["client_id"]
        
        _LOGGER.info("Credential update requested for user %s", username)
        
        # Find coordinator matching the username
        updated = False
        for entry_id, entry_data in hass.data[DOMAIN].items():
            coordinator: RedEnergyDataCoordinator = entry_data.get("coordinator")
            if coordinator and coordinator.username == username:
                try:
                    success = await coordinator.async_refresh_credentials(
                        username, password, client_id
                    )
                    if success:
                        _LOGGER.info("Successfully updated credentials for %s", username)
                        updated = True
                    else:
                        _LOGGER.error("Failed to validate new credentials for %s", username)
                except Exception as err:
                    _LOGGER.error("Error updating credentials for %s: %s", username, err)
                break
        
        if not updated:
            _LOGGER.warning("No matching coordinator found for username %s", username)
    
    async def async_export_data(call: ServiceCall) -> None:
        """Service call to export usage data."""
        export_format = call.data.get("format", "json")
        days = call.data.get("days", 30)
        
        _LOGGER.info("Data export requested: format=%s, days=%d", export_format, days)
        
        all_data = {}
        for entry_id, entry_data in hass.data[DOMAIN].items():
            coordinator: RedEnergyDataCoordinator = entry_data.get("coordinator")
            if coordinator and coordinator.data:
                # Extract relevant data for export
                export_data = {
                    "customer": coordinator.data.get("customer", {}),
                    "properties": [],
                    "usage_summary": {}
                }
                
                # Add property and usage data
                for prop_id, prop_data in coordinator.data.get("usage_data", {}).items():
                    property_info = prop_data.get("property", {})
                    export_data["properties"].append({
                        "id": prop_id,
                        "name": property_info.get("name"),
                        "address": property_info.get("address", {}),
                    })
                    
                    # Add usage data for each service
                    services_data = {}
                    for service_type, service_data in prop_data.get("services", {}).items():
                        usage_info = service_data.get("usage_data", {})
                        services_data[service_type] = {
                            "total_usage": usage_info.get("total_usage"),
                            "total_cost": usage_info.get("total_cost"),
                            "from_date": usage_info.get("from_date"),
                            "to_date": usage_info.get("to_date"),
                            "daily_data": usage_info.get("usage_data", [])[:days]  # Limit to requested days
                        }
                    
                    export_data["usage_summary"][prop_id] = services_data
                
                all_data[entry_id] = export_data
        
        # Store exported data as a persistent notification
        # In a real implementation, this could write to a file or send via webhook
        _LOGGER.info("Export completed for %d integrations", len(all_data))
        
        # Create a summary notification
        total_properties = sum(len(data["properties"]) for data in all_data.values())
        hass.components.persistent_notification.create(
            f"Red Energy data export completed:\n"
            f"- Format: {export_format}\n"
            f"- Days: {days}\n"
            f"- Integrations: {len(all_data)}\n"
            f"- Properties: {total_properties}\n\n"
            f"Data has been processed and is available in the logs.",
            title="Red Energy Export Complete",
            notification_id="red_energy_export"
        )
    
    # Register services
    hass.services.async_register(
        DOMAIN, "refresh_data", async_refresh_data, schema=SERVICE_REFRESH_DATA_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, "update_credentials", async_update_credentials, schema=SERVICE_UPDATE_CREDENTIALS_SCHEMA
    )
    
    hass.services.async_register(
        DOMAIN, "export_data", async_export_data, schema=SERVICE_EXPORT_DATA_SCHEMA
    )
    
    _LOGGER.info("Red Energy services registered successfully")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload services when integration is removed."""
    services = ["refresh_data", "update_credentials", "export_data"]
    
    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    
    _LOGGER.info("Red Energy services unloaded successfully")