"""Diagnostics support for Red Energy integration."""
from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import RedEnergyDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: RedEnergyDataCoordinator = entry_data["coordinator"]
    
    # Basic integration info
    diagnostics = {
        "integration_info": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
            "selected_accounts": entry_data.get("selected_accounts", []),
            "services": entry_data.get("services", []),
        },
        "coordinator_info": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
            "update_interval": str(coordinator.update_interval),
            "data_available": coordinator.data is not None,
        },
    }
    
    # Add coordinator data (sanitized)
    if coordinator.data:
        diagnostics["coordinator_data"] = {
            "customer": _sanitize_customer_data(coordinator.data.get("customer", {})),
            "properties_count": len(coordinator.data.get("properties", [])),
            "usage_data_count": len(coordinator.data.get("usage_data", {})),
            "last_update": coordinator.data.get("last_update"),
        }
        
        # Add property details (sanitized)
        properties = coordinator.data.get("properties", [])
        diagnostics["properties"] = []
        for prop in properties:
            diagnostics["properties"].append({
                "id": prop.get("id"),
                "name": prop.get("name"),
                "services_count": len(prop.get("services", [])),
                "services": [
                    {
                        "type": service.get("type"),
                        "active": service.get("active"),
                        "consumer_number_length": len(service.get("consumer_number", "")),
                    }
                    for service in prop.get("services", [])
                ]
            })
        
        # Add usage data summary
        usage_data = coordinator.data.get("usage_data", {})
        diagnostics["usage_summary"] = {}
        for prop_id, prop_data in usage_data.items():
            services_summary = {}
            for service_type, service_data in prop_data.get("services", {}).items():
                usage_info = service_data.get("usage_data", {})
                daily_data = usage_info.get("usage_data", [])
                services_summary[service_type] = {
                    "consumer_number_length": len(service_data.get("consumer_number", "")),
                    "total_usage": usage_info.get("total_usage"),
                    "total_cost": usage_info.get("total_cost"),
                    "daily_entries": len(daily_data),
                    "from_date": usage_info.get("from_date"),
                    "to_date": usage_info.get("to_date"),
                    "last_updated": service_data.get("last_updated"),
                }
            diagnostics["usage_summary"][prop_id] = services_summary
    
    # Add API info
    api_info = {
        "api_type": type(coordinator.api).__name__,
        "has_access_token": coordinator.api._access_token is not None,
        "token_expires": coordinator.api._token_expires.isoformat() if coordinator.api._token_expires else None,
    }
    diagnostics["api_info"] = api_info
    
    return diagnostics


def _sanitize_customer_data(customer_data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize customer data for diagnostics."""
    if not customer_data:
        return {}
    
    sanitized = {
        "id_length": len(customer_data.get("id", "")),
        "name_length": len(customer_data.get("name", "")),
        "email_domain": customer_data.get("email", "").split("@")[-1] if "@" in customer_data.get("email", "") else "",
    }
    
    if "phone" in customer_data:
        phone = customer_data["phone"]
        sanitized["phone_length"] = len(phone)
        sanitized["phone_prefix"] = phone[:3] if len(phone) >= 3 else ""
    
    return sanitized


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device
) -> Dict[str, Any]:
    """Return diagnostics for a device entry."""
    # For Red Energy, devices are properties
    # We can provide property-specific diagnostics here
    
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: RedEnergyDataCoordinator = entry_data["coordinator"]
    
    # Extract property ID from device identifier
    device_id = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            device_id = identifier[1].replace(f"{entry.entry_id}_", "")
            break
    
    if not device_id or not coordinator.data:
        return {"error": "Device not found or no data available"}
    
    # Get property-specific data
    property_data = coordinator.get_property_data(device_id)
    if not property_data:
        return {"error": f"No data available for property {device_id}"}
    
    diagnostics = {
        "device_info": {
            "property_id": device_id,
            "device_identifier": device_id,
        },
        "property_data": {
            "name": property_data.get("property", {}).get("name"),
            "services": list(property_data.get("services", {}).keys()),
        },
        "services_data": {},
    }
    
    # Add service-specific data
    for service_type, service_data in property_data.get("services", {}).items():
        usage_info = service_data.get("usage_data", {})
        daily_data = usage_info.get("usage_data", [])
        
        # Calculate some statistics
        if daily_data:
            usage_values = [entry.get("usage", 0) for entry in daily_data]
            cost_values = [entry.get("cost", 0) for entry in daily_data]
            
            diagnostics["services_data"][service_type] = {
                "consumer_number_length": len(service_data.get("consumer_number", "")),
                "total_usage": usage_info.get("total_usage"),
                "total_cost": usage_info.get("total_cost"),
                "daily_entries": len(daily_data),
                "from_date": usage_info.get("from_date"),
                "to_date": usage_info.get("to_date"),
                "usage_stats": {
                    "min": min(usage_values) if usage_values else 0,
                    "max": max(usage_values) if usage_values else 0,
                    "avg": sum(usage_values) / len(usage_values) if usage_values else 0,
                },
                "cost_stats": {
                    "min": min(cost_values) if cost_values else 0,
                    "max": max(cost_values) if cost_values else 0,
                    "avg": sum(cost_values) / len(cost_values) if cost_values else 0,
                },
                "last_updated": service_data.get("last_updated"),
            }
    
    return diagnostics