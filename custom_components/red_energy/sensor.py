"""Red Energy sensor platform."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
)
from .coordinator import RedEnergyDataCoordinator

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Red Energy sensors based on a config entry."""
    _LOGGER.debug("Setting up Red Energy sensors for config entry %s", config_entry.entry_id)
    
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: RedEnergyDataCoordinator = entry_data["coordinator"]
    selected_accounts = entry_data["selected_accounts"]
    services = entry_data["services"]
    
    entities = []
    
    # Create sensors for each selected account and service
    for account_id in selected_accounts:
        for service_type in services:
            # Create usage sensor
            entities.append(
                RedEnergyUsageSensor(
                    coordinator, config_entry, account_id, service_type
                )
            )
            
            # Create cost sensor
            entities.append(
                RedEnergyCostSensor(
                    coordinator, config_entry, account_id, service_type
                )
            )
            
            # Create total usage sensor (30-day total)
            entities.append(
                RedEnergyTotalUsageSensor(
                    coordinator, config_entry, account_id, service_type
                )
            )
    
    _LOGGER.debug("Created %d sensors for Red Energy integration", len(entities))
    async_add_entities(entities)


class RedEnergyBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Red Energy sensors."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        self._property_id = property_id
        self._service_type = service_type
        self._sensor_type = sensor_type
        
        # Get property info for naming
        property_data = None
        if coordinator.data and "usage_data" in coordinator.data:
            property_data = coordinator.data["usage_data"].get(property_id, {}).get("property")
        
        property_name = "Unknown Property"
        if property_data:
            property_name = property_data.get("name", f"Property {property_id}")
            
        service_display = service_type.title()
        
        self._attr_name = f"{property_name} {service_display} {sensor_type.title()}"
        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}_{property_id}_{service_type}_{sensor_type}"
        
        # Set device info for grouping
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{config_entry.entry_id}_{property_id}")},
            "name": property_name,
            "manufacturer": "Red Energy",
            "model": f"{service_display} Service",
            "via_device": (DOMAIN, config_entry.entry_id),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._property_id in self.coordinator.data.get("usage_data", {})
        )


class RedEnergyUsageSensor(RedEnergyBaseSensor):
    """Red Energy current usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "daily_usage")
        
        # Set appropriate device class and unit
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"  # Megajoules
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> Optional[float]:
        """Return the current daily usage."""
        return self.coordinator.get_latest_usage(self._property_id, self._service_type)

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "last_updated": service_data.get("last_updated"),
            "service_type": self._service_type,
        }


class RedEnergyCostSensor(RedEnergyBaseSensor):
    """Red Energy total cost sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the cost sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "total_cost")
        
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the total cost."""
        return self.coordinator.get_total_cost(self._property_id, self._service_type)

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "last_updated": service_data.get("last_updated"),
            "service_type": self._service_type,
            "period": "30 days",
        }


class RedEnergyTotalUsageSensor(RedEnergyBaseSensor):
    """Red Energy total usage sensor (30-day period)."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the total usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "total_usage")
        
        # Set appropriate device class and unit
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"  # Megajoules
            
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the total usage."""
        return self.coordinator.get_total_usage(self._property_id, self._service_type)

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        usage_data = service_data.get("usage_data", {})
        daily_data = usage_data.get("usage_data", [])
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "last_updated": service_data.get("last_updated"),
            "service_type": self._service_type,
            "period": "30 days",
            "daily_count": len(daily_data),
            "from_date": usage_data.get("from_date"),
            "to_date": usage_data.get("to_date"),
        }