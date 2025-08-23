"""Red Energy device manager for enhanced device registry management."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN, MANUFACTURER, SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS

_LOGGER = logging.getLogger(__name__)


class RedEnergyDeviceManager:
    """Manage Red Energy devices and entity organization."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the device manager."""
        self.hass = hass
        self.config_entry = config_entry
        self._device_registry = dr.async_get(hass)
        self._entity_registry = er.async_get(hass)

    async def async_setup_devices(
        self, 
        coordinator_data: Dict[str, Any], 
        selected_accounts: List[str],
        services: List[str]
    ) -> Dict[str, DeviceEntry]:
        """Set up devices for all properties with enhanced organization."""
        devices = {}
        
        for account_id in selected_accounts:
            property_data = coordinator_data.get("usage_data", {}).get(account_id)
            if not property_data:
                continue
                
            property_info = property_data.get("property", {})
            device = await self._create_property_device(
                account_id, property_info, services
            )
            
            if device:
                devices[account_id] = device
                _LOGGER.debug("Created device for property %s: %s", account_id, device.name)

        return devices

    async def _create_property_device(
        self, 
        account_id: str, 
        property_info: Dict[str, Any],
        services: List[str]
    ) -> Optional[DeviceEntry]:
        """Create or update a device for a property."""
        property_name = property_info.get("name", f"Property {account_id}")
        address = property_info.get("address", {})
        
        # Create comprehensive device identifiers
        identifiers = {(DOMAIN, account_id)}
        
        # Enhanced device information
        device_info = {
            "identifiers": identifiers,
            "name": property_name,
            "manufacturer": MANUFACTURER,
            "model": self._get_device_model(services),
            "sw_version": self._get_software_version(),
            "configuration_url": "https://www.redenergy.com.au/login",
        }
        
        # Add address information if available
        if address:
            street = address.get("street_address", "")
            suburb = address.get("suburb", "")
            state = address.get("state", "")
            postcode = address.get("postcode", "")
            
            if street and suburb:
                full_address = f"{street}, {suburb}"
                if state and postcode:
                    full_address += f", {state} {postcode}"
                device_info["suggested_area"] = suburb
                
        # Register or update the device
        device = self._device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            **device_info
        )
        
        # Update device attributes if needed
        await self._update_device_attributes(device, property_info, services)
        
        return device

    def _get_device_model(self, services: List[str]) -> str:
        """Generate device model based on enabled services."""
        service_names = []
        if SERVICE_TYPE_ELECTRICITY in services:
            service_names.append("Electricity")
        if SERVICE_TYPE_GAS in services:
            service_names.append("Gas")
        
        if len(service_names) == 2:
            return "Dual Service Monitor"
        elif SERVICE_TYPE_ELECTRICITY in services:
            return "Electricity Monitor"
        elif SERVICE_TYPE_GAS in services:
            return "Gas Monitor"
        else:
            return "Energy Monitor"

    def _get_software_version(self) -> str:
        """Get the integration software version."""
        # This could be enhanced to read from manifest.json
        return "1.4.0"

    async def _update_device_attributes(
        self, 
        device: DeviceEntry, 
        property_info: Dict[str, Any],
        services: List[str]
    ) -> None:
        """Update device attributes with current information."""
        # This method can be enhanced to update device-specific attributes
        # such as last seen, connection status, etc.
        pass

    async def async_cleanup_orphaned_entities(self) -> int:
        """Clean up orphaned entities that no longer have corresponding devices."""
        cleaned_count = 0
        
        # Get all entities for this integration
        entities = er.async_entries_for_config_entry(
            self._entity_registry, self.config_entry.entry_id
        )
        
        # Get all current devices
        devices = dr.async_entries_for_config_entry(
            self._device_registry, self.config_entry.entry_id
        )
        device_ids = {device.id for device in devices}
        
        # Find orphaned entities
        for entity in entities:
            if entity.device_id and entity.device_id not in device_ids:
                _LOGGER.info("Removing orphaned entity: %s", entity.entity_id)
                self._entity_registry.async_remove(entity.entity_id)
                cleaned_count += 1
        
        return cleaned_count

    async def async_organize_entities_by_service(
        self, 
        account_id: str, 
        device: DeviceEntry
    ) -> Dict[str, List[str]]:
        """Organize entities by service type for better UI grouping."""
        entities = er.async_entries_for_device(
            self._entity_registry, device.id
        )
        
        service_groups = {
            SERVICE_TYPE_ELECTRICITY: [],
            SERVICE_TYPE_GAS: [],
            "advanced": []
        }
        
        for entity in entities:
            entity_id = entity.entity_id
            
            # Categorize based on entity ID patterns
            if SERVICE_TYPE_ELECTRICITY in entity_id:
                if any(advanced in entity_id for advanced in ["daily_average", "monthly_average", "peak_usage", "efficiency"]):
                    service_groups["advanced"].append(entity_id)
                else:
                    service_groups[SERVICE_TYPE_ELECTRICITY].append(entity_id)
            elif SERVICE_TYPE_GAS in entity_id:
                if any(advanced in entity_id for advanced in ["daily_average", "monthly_average", "peak_usage", "efficiency"]):
                    service_groups["advanced"].append(entity_id)
                else:
                    service_groups[SERVICE_TYPE_GAS].append(entity_id)
        
        return service_groups

    async def async_get_device_diagnostics(self, device: DeviceEntry) -> Dict[str, Any]:
        """Get comprehensive diagnostics for a device."""
        entities = er.async_entries_for_device(
            self._entity_registry, device.id
        )
        
        diagnostics = {
            "device_info": {
                "id": device.id,
                "name": device.name,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "sw_version": device.sw_version,
                "identifiers": list(device.identifiers),
                "connections": list(device.connections),
                "configuration_url": device.configuration_url,
                "suggested_area": device.suggested_area,
            },
            "entity_count": len(entities),
            "entities": []
        }
        
        # Add entity information
        for entity in entities:
            state = self.hass.states.get(entity.entity_id)
            entity_info = {
                "entity_id": entity.entity_id,
                "name": entity.name or entity.original_name,
                "platform": entity.platform,
                "device_class": entity.device_class,
                "unit_of_measurement": entity.unit_of_measurement,
                "state": state.state if state else "unknown",
                "available": state.state != "unavailable" if state else False,
                "last_updated": state.last_updated.isoformat() if state else None,
            }
            
            # Add attributes for advanced sensors
            if state and state.attributes:
                if any(advanced in entity.entity_id for advanced in ["efficiency", "peak_usage"]):
                    entity_info["attributes"] = dict(state.attributes)
            
            diagnostics["entities"].append(entity_info)
        
        return diagnostics

    async def async_update_device_configuration(
        self, 
        device: DeviceEntry,
        new_services: List[str]
    ) -> bool:
        """Update device configuration when services change."""
        try:
            # Update device model based on new services
            new_model = self._get_device_model(new_services)
            
            self._device_registry.async_update_device(
                device.id,
                model=new_model
            )
            
            _LOGGER.debug(
                "Updated device %s model to %s for services %s",
                device.name, new_model, new_services
            )
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to update device configuration: %s", err)
            return False

    async def async_migrate_device_identifiers(
        self, 
        old_identifier: str, 
        new_identifier: str
    ) -> bool:
        """Migrate device identifiers for configuration changes."""
        # Find device with old identifier
        device = self._device_registry.async_get_device({(DOMAIN, old_identifier)})
        if not device:
            _LOGGER.warning("No device found with identifier %s", old_identifier)
            return False
        
        try:
            # Create new identifiers set
            new_identifiers = {(DOMAIN, new_identifier)}
            
            # Update device identifiers
            self._device_registry.async_update_device(
                device.id,
                new_identifiers=new_identifiers
            )
            
            _LOGGER.info(
                "Migrated device identifiers from %s to %s",
                old_identifier, new_identifier
            )
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to migrate device identifiers: %s", err)
            return False

    async def async_get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for device management."""
        devices = dr.async_entries_for_config_entry(
            self._device_registry, self.config_entry.entry_id
        )
        
        entities = er.async_entries_for_config_entry(
            self._entity_registry, self.config_entry.entry_id
        )
        
        # Count available vs unavailable entities
        available_count = 0
        unavailable_count = 0
        
        for entity in entities:
            state = self.hass.states.get(entity.entity_id)
            if state and state.state != "unavailable":
                available_count += 1
            else:
                unavailable_count += 1
        
        return {
            "total_devices": len(devices),
            "total_entities": len(entities),
            "available_entities": available_count,
            "unavailable_entities": unavailable_count,
            "entity_availability_ratio": available_count / len(entities) if entities else 0,
        }