"""Red Energy sensor platform."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLE_ADVANCED_SENSORS,
    DOMAIN,
    SENSOR_TYPE_ARREARS,
    SENSOR_TYPE_BALANCE,
    SENSOR_TYPE_BILLING_FREQUENCY,
    SENSOR_TYPE_DAILY_AVERAGE,
    SENSOR_TYPE_DISTRIBUTOR,
    SENSOR_TYPE_EFFICIENCY,
    SENSOR_TYPE_LAST_BILL_DATE,
    SENSOR_TYPE_METER_TYPE,
    SENSOR_TYPE_MONTHLY_AVERAGE,
    SENSOR_TYPE_NEXT_BILL_DATE,
    SENSOR_TYPE_NMI,
    SENSOR_TYPE_PEAK_USAGE,
    SENSOR_TYPE_PRODUCT_NAME,
    SENSOR_TYPE_SOLAR,
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
                RedEnergyNmiSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyMeterTypeSensor(coordinator, config_entry, account_id, service_type),
                RedEnergySolarSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyProductNameSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyDistributorSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyBalanceSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyArrearsSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyLastBillDateSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyNextBillDateSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyBillingFrequencySensor(coordinator, config_entry, account_id, service_type),
                # NEW: Daily import/export breakdown (CORE)
                RedEnergyDailyImportUsageSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyDailyExportUsageSensor(coordinator, config_entry, account_id, service_type),
                # NEW: Total import/export breakdown (CORE)
                RedEnergyTotalImportUsageSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyTotalExportUsageSensor(coordinator, config_entry, account_id, service_type),
                # NEW: Cost breakdown (CORE)
                RedEnergyTotalImportCostSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyTotalExportCreditSensor(coordinator, config_entry, account_id, service_type),
                RedEnergyNetCostSensor(coordinator, config_entry, account_id, service_type),
            ])
            
            # Advanced sensors (optional)
            if advanced_sensors_enabled:
                entities.extend([
                    # Existing advanced sensors
                    RedEnergyDailyAverageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyMonthlyAverageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyPeakUsageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyEfficiencySensor(coordinator, config_entry, account_id, service_type),
                    # NEW: Time period import breakdown (ADVANCED)
                    RedEnergyPeakImportUsageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyOffpeakImportUsageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyShoulderImportUsageSensor(coordinator, config_entry, account_id, service_type),
                    # NEW: Time period export breakdown (ADVANCED)
                    RedEnergyPeakExportUsageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyOffpeakExportUsageSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyShoulderExportUsageSensor(coordinator, config_entry, account_id, service_type),
                    # NEW: Demand and environmental (ADVANCED)
                    RedEnergyMaxDemandSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyMaxDemandTimeSensor(coordinator, config_entry, account_id, service_type),
                    RedEnergyCarbonEmissionSensor(coordinator, config_entry, account_id, service_type),
                ])
    
    _LOGGER.debug(
        "Created %d sensors (%d core, %d advanced) for Red Energy integration", 
        len(entities),
        len(selected_accounts) * len(services) * 20,  # Core sensors
        len(entities) - (len(selected_accounts) * len(services) * 20)  # Advanced sensors
    )
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


class RedEnergyNmiSensor(RedEnergyBaseSensor):
    """Red Energy NMI sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the NMI sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_NMI)
        
        self._attr_icon = "mdi:identifier"

    @property
    def native_value(self) -> Optional[str]:
        """Return the NMI."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        return metadata.get("nmi")


class RedEnergyMeterTypeSensor(RedEnergyBaseSensor):
    """Red Energy meter type sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the meter type sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_METER_TYPE)
        
        self._attr_icon = "mdi:meter-electric"

    @property
    def native_value(self) -> Optional[str]:
        """Return the meter type."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        return metadata.get("meterType")


class RedEnergySolarSensor(RedEnergyBaseSensor):
    """Red Energy solar capability sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the solar sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_SOLAR)
        
        self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> Optional[str]:
        """Return the solar status."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        has_solar = metadata.get("solar", False)
        return "Yes" if has_solar else "No"


class RedEnergyProductNameSensor(RedEnergyBaseSensor):
    """Red Energy energy plan sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the energy plan sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_PRODUCT_NAME)
        
        self._attr_icon = "mdi:package-variant"

    @property
    def native_value(self) -> Optional[str]:
        """Return the product name."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        return metadata.get("productName")


class RedEnergyDistributorSensor(RedEnergyBaseSensor):
    """Red Energy distributor/lines company sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the distributor sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_DISTRIBUTOR)
        
        self._attr_icon = "mdi:transmission-tower"

    @property
    def native_value(self) -> Optional[str]:
        """Return the distributor name."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        return metadata.get("linesCompany")


class RedEnergyBalanceSensor(RedEnergyBaseSensor):
    """Red Energy account balance sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the balance sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_BALANCE)
        
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the account balance."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        return metadata.get("balanceDollar")


class RedEnergyArrearsSensor(RedEnergyBaseSensor):
    """Red Energy arrears sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the arrears sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_ARREARS)
        
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the arrears amount."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        return metadata.get("arrearsDollar")


class RedEnergyLastBillDateSensor(RedEnergyBaseSensor):
    """Red Energy last bill date sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the last bill date sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_LAST_BILL_DATE)
        
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:calendar-check"

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the last bill date."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        last_bill = metadata.get("lastBillDate")
        if last_bill:
            try:
                naive_dt = datetime.strptime(last_bill, "%Y-%m-%d")
                return dt_util.as_utc(naive_dt)
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid lastBillDate format: %s", last_bill)
                return None
        return None


class RedEnergyNextBillDateSensor(RedEnergyBaseSensor):
    """Red Energy next bill date sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the next bill date sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_NEXT_BILL_DATE)
        
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:calendar-clock"

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the next bill date."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        next_bill = metadata.get("nextBillDate")
        if next_bill:
            try:
                naive_dt = datetime.strptime(next_bill, "%Y-%m-%d")
                return dt_util.as_utc(naive_dt)
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid nextBillDate format: %s", next_bill)
                return None
        return None


class RedEnergyBillingFrequencySensor(RedEnergyBaseSensor):
    """Red Energy billing frequency sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the billing frequency sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, SENSOR_TYPE_BILLING_FREQUENCY)
        
        self._attr_icon = "mdi:calendar-refresh"

    @property
    def native_value(self) -> Optional[str]:
        """Return the billing frequency."""
        metadata = self.coordinator.get_service_metadata(self._property_id, self._service_type)
        if not metadata:
            return None
        
        frequency = metadata.get("billingFrequency")
        if frequency:
            return frequency.title()
        return None


class RedEnergyDailyImportUsageSensor(RedEnergyBaseSensor):
    """Red Energy daily import usage sensor (grid consumption)."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the daily import usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "daily_import_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> Optional[float]:
        """Return the current daily import usage."""
        return self.coordinator.get_latest_import_usage(self._property_id, self._service_type)

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
            "description": "Grid import (consumption)"
        }


class RedEnergyDailyExportUsageSensor(RedEnergyBaseSensor):
    """Red Energy daily export usage sensor (solar generation)."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the daily export usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "daily_export_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_icon = "mdi:solar-power"
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> Optional[float]:
        """Return the current daily export usage."""
        return self.coordinator.get_latest_export_usage(self._property_id, self._service_type)

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
            "description": "Solar export (generation)"
        }


class RedEnergyTotalImportUsageSensor(RedEnergyBaseSensor):
    """Red Energy total import usage sensor (30-day period)."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the total import usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "total_import_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"
            
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the total import usage."""
        return self.coordinator.get_total_import_usage(self._property_id, self._service_type)

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
            "description": "Total grid import"
        }


class RedEnergyTotalExportUsageSensor(RedEnergyBaseSensor):
    """Red Energy total export usage sensor (30-day period)."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the total export usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "total_export_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_icon = "mdi:solar-power"
        elif service_type == SERVICE_TYPE_GAS:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "MJ"
            
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the total export usage."""
        return self.coordinator.get_total_export_usage(self._property_id, self._service_type)

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
            "description": "Total solar export"
        }


class RedEnergyTotalImportCostSensor(RedEnergyBaseSensor):
    """Red Energy total import cost sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the total import cost sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "total_import_cost")
        
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the total import cost."""
        return self.coordinator.get_total_import_cost(self._property_id, self._service_type)

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
            "gst_inclusive": False,
            "description": "Total cost of grid import"
        }


class RedEnergyTotalExportCreditSensor(RedEnergyBaseSensor):
    """Red Energy total export credit sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the total export credit sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "total_export_credit")
        
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> Optional[float]:
        """Return the total export credit."""
        return self.coordinator.get_total_export_credit(self._property_id, self._service_type)

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
            "description": "Total credit from solar export"
        }


class RedEnergyNetCostSensor(RedEnergyBaseSensor):
    """Red Energy net cost sensor (import cost - export credit)."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the net cost sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "net_cost")
        
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = "AUD"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the net cost."""
        return self.coordinator.get_net_total_cost(self._property_id, self._service_type)

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        import_cost = self.coordinator.get_total_import_cost(self._property_id, self._service_type)
        export_credit = self.coordinator.get_total_export_credit(self._property_id, self._service_type)
        
        return {
            "import_cost": import_cost,
            "export_credit": export_credit,
            "calculation": "import_cost - export_credit",
            "period": "30 days",
            "description": "Actual cost after solar credits"
        }


class RedEnergyPeakImportUsageSensor(RedEnergyBaseSensor):
    """Red Energy peak import usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the peak import usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "peak_import_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the peak import usage."""
        return self.coordinator.get_period_import_usage(self._property_id, self._service_type, "peak")

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        total_import = self.coordinator.get_total_import_usage(self._property_id, self._service_type)
        percentage = (self.native_value / total_import * 100) if total_import and self.native_value else 0
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "time_period": "PEAK",
            "percentage_of_total": round(percentage, 1),
            "period": "30 days"
        }


class RedEnergyOffpeakImportUsageSensor(RedEnergyBaseSensor):
    """Red Energy offpeak import usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the offpeak import usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "offpeak_import_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the offpeak import usage."""
        return self.coordinator.get_period_import_usage(self._property_id, self._service_type, "offpeak")

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        total_import = self.coordinator.get_total_import_usage(self._property_id, self._service_type)
        percentage = (self.native_value / total_import * 100) if total_import and self.native_value else 0
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "time_period": "OFFPEAK",
            "percentage_of_total": round(percentage, 1),
            "period": "30 days"
        }


class RedEnergyShoulderImportUsageSensor(RedEnergyBaseSensor):
    """Red Energy shoulder import usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the shoulder import usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "shoulder_import_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> Optional[float]:
        """Return the shoulder import usage."""
        return self.coordinator.get_period_import_usage(self._property_id, self._service_type, "shoulder")

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        total_import = self.coordinator.get_total_import_usage(self._property_id, self._service_type)
        percentage = (self.native_value / total_import * 100) if total_import and self.native_value else 0
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "time_period": "SHOULDER",
            "percentage_of_total": round(percentage, 1),
            "period": "30 days"
        }


class RedEnergyPeakExportUsageSensor(RedEnergyBaseSensor):
    """Red Energy peak export usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the peak export usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "peak_export_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> Optional[float]:
        """Return the peak export usage."""
        return self.coordinator.get_period_export_usage(self._property_id, self._service_type, "peak")

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        total_export = self.coordinator.get_total_export_usage(self._property_id, self._service_type)
        percentage = (self.native_value / total_export * 100) if total_export and self.native_value else 0
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "time_period": "PEAK",
            "percentage_of_total": round(percentage, 1),
            "period": "30 days",
            "description": "Solar export during peak tariff"
        }


class RedEnergyOffpeakExportUsageSensor(RedEnergyBaseSensor):
    """Red Energy offpeak export usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the offpeak export usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "offpeak_export_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> Optional[float]:
        """Return the offpeak export usage."""
        return self.coordinator.get_period_export_usage(self._property_id, self._service_type, "offpeak")

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        total_export = self.coordinator.get_total_export_usage(self._property_id, self._service_type)
        percentage = (self.native_value / total_export * 100) if total_export and self.native_value else 0
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "time_period": "OFFPEAK",
            "percentage_of_total": round(percentage, 1),
            "period": "30 days",
            "description": "Solar export during offpeak tariff"
        }


class RedEnergyShoulderExportUsageSensor(RedEnergyBaseSensor):
    """Red Energy shoulder export usage sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the shoulder export usage sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "shoulder_export_usage")
        
        if service_type == SERVICE_TYPE_ELECTRICITY:
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> Optional[float]:
        """Return the shoulder export usage."""
        return self.coordinator.get_period_export_usage(self._property_id, self._service_type, "shoulder")

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        service_data = self.coordinator.get_service_usage(self._property_id, self._service_type)
        if not service_data:
            return None
        
        total_export = self.coordinator.get_total_export_usage(self._property_id, self._service_type)
        percentage = (self.native_value / total_export * 100) if total_export and self.native_value else 0
        
        return {
            "consumer_number": service_data.get("consumer_number"),
            "time_period": "SHOULDER",
            "percentage_of_total": round(percentage, 1),
            "period": "30 days",
            "description": "Solar export during shoulder tariff"
        }


class RedEnergyMaxDemandSensor(RedEnergyBaseSensor):
    """Red Energy maximum demand sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the maximum demand sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "max_demand")
        
        from homeassistant.const import UnitOfPower
        
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:lightning-bolt"

    @property
    def native_value(self) -> Optional[float]:
        """Return the maximum demand."""
        data = self.coordinator.get_max_demand_data(self._property_id, self._service_type)
        return data.get("max_demand_kw") if data else None

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        data = self.coordinator.get_max_demand_data(self._property_id, self._service_type)
        if not data:
            return None
        
        return {
            "max_demand_time": data.get("max_demand_time"),
            "max_demand_date": data.get("max_demand_date"),
            "period": "30 days"
        }


class RedEnergyMaxDemandTimeSensor(RedEnergyBaseSensor):
    """Red Energy maximum demand timestamp sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the maximum demand timestamp sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "max_demand_interval_start")
        
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:clock-alert"

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the maximum demand timestamp."""
        data = self.coordinator.get_max_demand_data(self._property_id, self._service_type)
        if not data or not data.get("max_demand_time"):
            return None
        
        try:
            return datetime.fromisoformat(data["max_demand_time"])
        except (ValueError, TypeError):
            return None


class RedEnergyCarbonEmissionSensor(RedEnergyBaseSensor):
    """Red Energy carbon emission sensor."""

    def __init__(
        self,
        coordinator: RedEnergyDataCoordinator,
        config_entry: ConfigEntry,
        property_id: str,
        service_type: str,
    ) -> None:
        """Initialize the carbon emission sensor."""
        super().__init__(coordinator, config_entry, property_id, service_type, "carbon_emission_tonne")
        
        self._attr_native_unit_of_measurement = "t CO₂"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:molecule-co2"

    @property
    def native_value(self) -> Optional[float]:
        """Return the total carbon emissions."""
        return self.coordinator.get_total_carbon_emission(self._property_id, self._service_type)

    @property
    def extra_state_attributes(self) -> Optional[dict[str, Any]]:
        """Return extra state attributes."""
        total_import = self.coordinator.get_total_import_usage(self._property_id, self._service_type)
        emission = self.native_value
        
        emission_factor = (emission / total_import * 1000) if total_import and emission else 0
        
        return {
            "emission_factor_kg_per_kwh": round(emission_factor, 3),
            "period": "30 days",
            "description": "Total carbon emissions from grid consumption"
        }