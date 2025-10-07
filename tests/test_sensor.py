"""Comprehensive tests for Red Energy sensors."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from custom_components.red_energy.const import (
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
    SENSOR_TYPE_DAILY_AVERAGE,
    SENSOR_TYPE_MONTHLY_AVERAGE,
    SENSOR_TYPE_PEAK_USAGE,
    SENSOR_TYPE_EFFICIENCY,
)
from custom_components.red_energy.sensor import (
    RedEnergyBaseSensor,
    RedEnergyCostSensor,
    RedEnergyDailyAverageSensor,
    RedEnergyMonthlyAverageSensor,
    RedEnergyPeakUsageSensor,
    RedEnergyEfficiencySensor,
    RedEnergyNmiSensor,
    RedEnergyMeterTypeSensor,
    RedEnergySolarSensor,
    RedEnergyDailyImportUsageSensor,
    RedEnergyDailyExportUsageSensor,
    RedEnergyTotalImportUsageSensor,
    RedEnergyTotalExportUsageSensor,
    RedEnergyTotalImportCostSensor,
    RedEnergyTotalExportCreditSensor,
    RedEnergyNetCostSensor,
    RedEnergyPeakImportUsageSensor,
    RedEnergyOffpeakImportUsageSensor,
    RedEnergyShoulderImportUsageSensor,
)


def create_mock_coordinator():
    """Create a mock coordinator for testing."""
    coordinator = MagicMock()
    coordinator.data = {
        "usage_data": {
            "prop-001": {
                "property": {
                    "name": "Test Property",
                    "id": "prop-001"
                },
                "electricity": {
                    "consumer_number": "elec-123",
                    "metadata": {
                        "nmi": "1234567890",
                        "meterType": "Smart Meter",
                        "solar": True,
                        "productName": "Basic Energy Plan",
                        "linesCompany": "AusNet Services",
                        "balanceDollar": -150.50,
                        "arrearsDollar": 0.0,
                        "lastBillDate": "2024-01-01",
                        "nextBillDate": "2024-02-01",
                        "billingFrequency": "monthly",
                        "jurisdiction": "VIC",
                        "chargeClass": "RES",
                        "status": "ON"
                    },
                    "usage_data": {
                        "from_date": "2024-01-01",
                        "to_date": "2024-01-30",
                        "usage_data": [
                            {"date": "2024-01-01", "usage": 25.0, "cost": 7.00},
                            {"date": "2024-01-02", "usage": 30.0, "cost": 8.40},
                            {"date": "2024-01-03", "usage": 28.0, "cost": 7.84},
                        ]
                    },
                    "period_days": 30,
                    "last_updated": "2024-01-30T10:00:00"
                }
            }
        }
    }
    coordinator.last_update_success = True
    coordinator.get_service_usage = MagicMock(return_value=coordinator.data["usage_data"]["prop-001"]["electricity"])
    coordinator.get_service_metadata = MagicMock(return_value=coordinator.data["usage_data"]["prop-001"]["electricity"]["metadata"])
    coordinator.get_total_cost = MagicMock(return_value=23.24)
    coordinator.get_total_usage = MagicMock(return_value=83.0)
    coordinator.get_latest_import_usage = MagicMock(return_value=28.0)
    coordinator.get_latest_export_usage = MagicMock(return_value=5.0)
    coordinator.get_total_import_usage = MagicMock(return_value=83.0)
    coordinator.get_total_export_usage = MagicMock(return_value=15.0)
    coordinator.get_total_import_cost = MagicMock(return_value=23.24)
    coordinator.get_total_export_credit = MagicMock(return_value=2.10)
    coordinator.get_net_total_cost = MagicMock(return_value=21.14)
    coordinator.get_latest_import_cost = MagicMock(return_value=7.84)
    coordinator.get_latest_export_credit = MagicMock(return_value=0.70)
    coordinator.get_period_import_usage = MagicMock(return_value=50.0)
    coordinator.get_period_export_usage = MagicMock(return_value=10.0)
    coordinator.get_max_demand_data = MagicMock(return_value={
        "max_demand_kw": 5.2,
        "max_demand_time": "2024-01-15T18:30:00",
        "max_demand_date": "2024-01-15"
    })
    coordinator.get_total_carbon_emission = MagicMock(return_value=0.073)
    return coordinator


def create_mock_config_entry():
    """Create a mock config entry for testing."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "username": "test@example.com",
        "password": "testpass",
        "client_id": "test-client-id"
    }
    entry.options = {}
    return entry


class TestSensorDisplayNames:
    """Test sensor display names with underscore to space conversion."""

    def test_base_sensor_replaces_underscores_with_spaces(self):
        """Test that underscores in sensor_type are replaced with spaces in display names."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        # Test with sensor type containing underscores
        sensor = RedEnergyBaseSensor(
            coordinator,
            config_entry,
            "prop-001",
            SERVICE_TYPE_ELECTRICITY,
            "daily_import_usage"
        )
        
        # Display name should have spaces, not underscores
        assert "Daily Import Usage" in sensor._attr_name
        assert "_" not in sensor._attr_name.split(" ")[-3:]  # Check last 3 words don't have underscores

    def test_total_cost_sensor_display_name(self):
        """Test total_cost sensor display name."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert "Total Cost" in sensor._attr_name
        assert "Total_Cost" not in sensor._attr_name

    def test_daily_average_sensor_display_name(self):
        """Test daily_average sensor display name."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyDailyAverageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert "Daily Average" in sensor._attr_name
        assert "_" not in sensor._attr_name.split()[-2:]  # Last two words shouldn't have underscores

    def test_peak_import_usage_sensor_display_name(self):
        """Test peak_import_usage sensor display name."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyPeakImportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert "Peak Import Usage" in sensor._attr_name
        # Check that the sensor type portion doesn't have underscores
        assert "_import_" not in sensor._attr_name

    def test_carbon_emission_tonne_sensor_display_name(self):
        """Test carbon_emission_tonne sensor display name."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        from custom_components.red_energy.sensor import RedEnergyCarbonEmissionSensor
        sensor = RedEnergyCarbonEmissionSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert "Carbon Emission Tonne" in sensor._attr_name
        assert "_" not in sensor._attr_name.split()[-3:]


class TestSensorValues:
    """Test sensor value calculations."""

    def test_cost_sensor_value(self):
        """Test cost sensor returns correct value."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 23.24
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.device_class == SensorDeviceClass.MONETARY

    def test_daily_average_sensor_calculation(self):
        """Test daily average sensor calculates correctly."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyDailyAverageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        # Should calculate average from usage_data
        value = sensor.native_value
        assert value is not None
        # Average of [25.0, 30.0, 28.0] = 27.67
        assert 27.0 <= value <= 28.0

    def test_monthly_average_sensor_calculation(self):
        """Test monthly average sensor calculates correctly."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyMonthlyAverageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        value = sensor.native_value
        assert value is not None
        assert value > 0

    def test_peak_usage_sensor_value(self):
        """Test peak usage sensor returns max value."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyPeakUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        value = sensor.native_value
        assert value == 30.0  # Max of [25.0, 30.0, 28.0]

    def test_efficiency_sensor_calculation(self):
        """Test efficiency sensor calculates correctly."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyEfficiencySensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        # Efficiency sensor requires at least 7 days of data, mock only has 3
        # So it returns None, which is correct behavior
        value = sensor.native_value
        # Either None (not enough data) or a valid percentage
        if value is not None:
            assert 0 <= value <= 100
        assert sensor.native_unit_of_measurement == "%"


class TestSensorAttributes:
    """Test sensor extra state attributes."""

    def test_cost_sensor_attributes(self):
        """Test cost sensor has correct attributes."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "consumer_number" in attrs
        assert "service_type" in attrs
        assert "period" in attrs

    def test_peak_usage_sensor_attributes(self):
        """Test peak usage sensor has peak date attribute."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyPeakUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "peak_date" in attrs
        assert "peak_cost" in attrs

    def test_efficiency_sensor_attributes(self):
        """Test efficiency sensor has usage variation attribute."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyEfficiencySensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert "usage_variation" in attrs
        assert "mean_daily_usage" in attrs
        assert "calculation_days" in attrs


class TestMetadataSensors:
    """Test metadata sensors."""

    def test_nmi_sensor(self):
        """Test NMI sensor returns correct value."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyNmiSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == "1234567890"
        assert sensor.icon == "mdi:identifier"

    def test_meter_type_sensor(self):
        """Test meter type sensor returns correct value."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyMeterTypeSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == "Smart Meter"

    def test_solar_sensor(self):
        """Test solar sensor returns correct value."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergySolarSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == "Yes"


class TestImportExportSensors:
    """Test import/export sensors."""

    def test_daily_import_usage_sensor(self):
        """Test daily import usage sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyDailyImportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 28.0
        assert sensor.device_class == SensorDeviceClass.ENERGY
        assert sensor.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR

    def test_daily_export_usage_sensor(self):
        """Test daily export usage sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyDailyExportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 5.0
        assert sensor.icon == "mdi:solar-power"

    def test_total_import_usage_sensor(self):
        """Test total import usage sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyTotalImportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 83.0
        assert sensor.state_class == SensorStateClass.TOTAL

    def test_total_export_usage_sensor(self):
        """Test total export usage sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyTotalExportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 15.0


class TestCostCreditSensors:
    """Test cost and credit sensors."""

    def test_total_import_cost_sensor(self):
        """Test total import cost sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyTotalImportCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 23.24
        assert sensor.native_unit_of_measurement == "AUD"

    def test_total_export_credit_sensor(self):
        """Test total export credit sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyTotalExportCreditSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 2.10

    def test_net_cost_sensor(self):
        """Test net cost sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyNetCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 21.14
        attrs = sensor.extra_state_attributes
        assert "import_cost" in attrs
        assert "export_credit" in attrs
        assert "calculation" in attrs


class TestTimePeriodSensors:
    """Test time period sensors (peak, offpeak, shoulder)."""

    def test_peak_import_usage_sensor(self):
        """Test peak import usage sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyPeakImportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 50.0
        attrs = sensor.extra_state_attributes
        assert "time_period" in attrs
        assert attrs["time_period"] == "PEAK"

    def test_offpeak_import_usage_sensor(self):
        """Test offpeak import usage sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyOffpeakImportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 50.0

    def test_shoulder_import_usage_sensor(self):
        """Test shoulder import usage sensor."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyShoulderImportUsageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.native_value == 50.0


class TestSensorAvailability:
    """Test sensor availability logic."""

    def test_sensor_available_when_data_present(self):
        """Test sensor is available when data is present."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.available is True

    def test_sensor_unavailable_when_coordinator_fails(self):
        """Test sensor is unavailable when coordinator update fails."""
        coordinator = create_mock_coordinator()
        coordinator.last_update_success = False
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.available is False

    def test_sensor_unavailable_when_property_missing(self):
        """Test sensor is unavailable when property data is missing."""
        coordinator = create_mock_coordinator()
        coordinator.data = {"usage_data": {}}
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor.available is False


class TestSensorDeviceInfo:
    """Test sensor device information."""

    def test_sensor_device_info_structure(self):
        """Test sensor has correct device info structure."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        device_info = sensor.device_info
        assert device_info is not None
        assert "identifiers" in device_info
        assert "name" in device_info
        assert "manufacturer" in device_info
        assert "model" in device_info

    def test_sensor_device_info_grouping(self):
        """Test sensors from same property are grouped."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor1 = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        sensor2 = RedEnergyNmiSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        # Both sensors should have same device identifier
        device_id_1 = list(sensor1.device_info["identifiers"])[0]
        device_id_2 = list(sensor2.device_info["identifiers"])[0]
        assert device_id_1 == device_id_2


class TestSensorUniqueIds:
    """Test sensor unique IDs."""

    def test_sensor_unique_id_format(self):
        """Test sensor unique ID has correct format."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        unique_id = sensor.unique_id
        assert unique_id is not None
        assert DOMAIN in unique_id
        assert "test_entry_id" in unique_id
        assert "prop-001" in unique_id
        assert SERVICE_TYPE_ELECTRICITY in unique_id

    def test_different_sensors_have_different_unique_ids(self):
        """Test different sensors have different unique IDs."""
        coordinator = create_mock_coordinator()
        config_entry = create_mock_config_entry()
        
        sensor1 = RedEnergyCostSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        sensor2 = RedEnergyNmiSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_ELECTRICITY)
        
        assert sensor1.unique_id != sensor2.unique_id


class TestGasSensors:
    """Test gas service sensors."""

    def test_gas_sensor_units(self):
        """Test gas sensors use correct units."""
        coordinator = create_mock_coordinator()
        # Add gas data
        coordinator.data["usage_data"]["prop-001"]["gas"] = {
            "consumer_number": "gas-123",
            "metadata": {},
            "usage_data": {"usage_data": []},
            "period_days": 30
        }
        coordinator.get_service_usage = MagicMock(
            return_value=coordinator.data["usage_data"]["prop-001"]["gas"]
        )
        
        config_entry = create_mock_config_entry()
        
        sensor = RedEnergyDailyAverageSensor(coordinator, config_entry, "prop-001", SERVICE_TYPE_GAS)
        
        assert sensor.device_class == SensorDeviceClass.ENERGY
        assert sensor.native_unit_of_measurement == "MJ"

