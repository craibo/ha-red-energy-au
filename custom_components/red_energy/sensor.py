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
    CONF_ENABLE_ADVANCED_SENSORS,
    DOMAIN,
    SENSOR_TYPE_DAILY_AVERAGE,
    SENSOR_TYPE_EFFICIENCY,
    SENSOR_TYPE_MONTHLY_AVERAGE,
    SENSOR_TYPE_PEAK_USAGE,
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
    
    # Check if advanced sensors are enabled
    advanced_sensors_enabled = config_entry.options.get(CONF_ENABLE_ADVANCED_SENSORS, False)
    
    entities = []
    
    # Create sensors for each selected account and service
    for account_id in selected_accounts:
        for service_type in services:
            # Core sensors (always created)
            entities.extend([
                RedEnergyUsageSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyCostSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyTotalUsageSensor(coordinator, config_entry, account_id, service_type),
            ])
            
            # Advanced sensors (optional)
            if advanced_sensors_enabled:
                entities.extend([
                    RedEnergyDailyAverageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyMonthlyAverageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyPeakUsageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyEfficiencySensor(coordinator, config_entry, account_id, service_type),
                ])
    
    _LOGGER.debug("Created %d sensors (%d advanced) for Red Energy integration", 
                 len(entities), len(entities) - (len(selected_accounts) * len(services) * 3))
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


class RedEnergyDailyAverageSensor(RedEnergyBaseSensor):
    """Red Energy daily average usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the daily average sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_DAILY_AVERAGE)
        
        # Set appropriate device class and unit
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"
            
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[float]:
        """Return the daily average usage."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        # Calculate average daily usage
        total_usage = sum(entry.get("usage", 0) for entry in usage_data)
        return round(total_usage / len(usage_data), 2) if usage_data else 0

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return {
            "consumer_number": service_data.get("consumer_number"),
            "calculation_period": f"{len(usage_data)} days",
            "service_type": self._service_type,
        }


class RedEnergyMonthlyAverageSensor(RedEnergyBaseSensor):
    """Red Energy monthly average usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the monthly average sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_MONTHLY_AVERAGE)
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"
            
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[float]:
        """Return the estimated monthly average usage."""
        total_usage = self.coordinator.get_total_usage(self._property_id, self._service_type)
        if total_usage is None:
            return None
        
        # Project 30-day usage to monthly (30.44 days average)
        return round(total_usage * (30.44 / 30), 2)


class RedEnergyPeakUsageSensor(RedEnergyBaseSensor):
    """Red Energy peak daily usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the peak usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_PEAK_USAGE)
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"
            
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[float]:
        """Return the peak daily usage."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        # Find peak daily usage
        usage_values = [entry.get("usage", 0) for entry in usage_data]
        return max(usage_values) if usage_values else 0

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        # Find peak date
        peak_entry = max(usage_data, key=lambda x: x.get("usage", 0))
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "peak_date": peak_entry.get("date"),
            "peak_cost": peak_entry.get("cost"),
            "service_type": self._service_type,
        }


class RedEnergyEfficiencySensor(RedEnergyBaseSensor):
    """Red Energy efficiency rating sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the efficiency sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_EFFICIENCY)
        
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:leaf"

    @property
    def native_value(self) -> Optional[float]:
        """Return the efficiency rating (0-100%)."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if len(usage_data) < 7:  # Need at least a week of data
            return None
        
        # Calculate efficiency based on usage consistency and trends
        usage_values = [entry.get("usage", 0) for entry in usage_data]
        
        # Calculate coefficient of variation (lower is more efficient/consistent)
        if not usage_values or len(usage_values) < 2:
            return None
        
        mean_usage = sum(usage_values) / len(usage_values)
        if mean_usage == 0:
            return 100  # Perfect efficiency if no usage
        
        variance = sum((x - mean_usage) ** 2 for x in usage_values) / len(usage_values)
        std_dev = variance ** 0.5
        cv = std_dev / mean_usage
        
        # Convert to efficiency score (0-100%, where lower CV = higher efficiency)
        efficiency = max(0, min(100, 100 - (cv * 100)))
        return round(efficiency, 1)

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        usage_values = [entry.get("usage", 0) for entry in usage_data]
        mean_usage = sum(usage_values) / len(usage_values) if usage_values else 0
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "mean_daily_usage": round(mean_usage, 2),
            "usage_variation": "Low" if self.native_value and self.native_value > 80 else 
                             "Medium" if self.native_value and self.native_value > 60 else "High",
            "calculation_days": len(usage_data),
            "service_type": self._service_type,
        }