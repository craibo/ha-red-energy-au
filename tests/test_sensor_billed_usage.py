"""Tests for billed-period sensors on gas/BASIC meters."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.util import dt as dt_util

from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS
from custom_components.red_energy.sensor import (
    RedEnergyBilledAverageDailyCostSensor,
    RedEnergyBilledAverageDailyUsageSensor,
    RedEnergyBilledUsageSensor,
    RedEnergyCurrentReadSensor,
    RedEnergyPreviousReadSensor,
)

BILLED = {
    "from_date": "2026-01-01",
    "to_date": "2026-03-31",
    "days": 90,
    "consumption_mj": 3600.0,
    "consumption_kwh": 1000.0,
    "total_charges_dollar": 200.0,
    "is_pricing_reliable": True,
}


def _coordinator(billed):
    coordinator = MagicMock()
    coordinator.get_billed_usage = MagicMock(return_value=billed)
    return coordinator


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


def _sensor(cls, billed, service_type=SERVICE_TYPE_GAS):
    return cls(_coordinator(billed), _config_entry(), "2000002", service_type)


def test_billed_gas_usage_reports_mj_as_energy_total():
    sensor = _sensor(RedEnergyBilledUsageSensor, BILLED)

    assert sensor.name == "Billed Gas Usage"
    assert sensor.unique_id == "red_energy_entry1_2000002_gas_billed_usage"
    assert sensor.native_value == 3600.0
    assert sensor.native_unit_of_measurement == UnitOfEnergy.MEGA_JOULE
    assert sensor.device_class == SensorDeviceClass.ENERGY
    assert sensor.state_class == SensorStateClass.TOTAL
    assert sensor.last_reset == dt_util.as_utc(datetime(2026, 1, 1))
    assert sensor.extra_state_attributes == {
        "from_date": "2026-01-01",
        "to_date": "2026-03-31",
        "days": 90,
        "is_pricing_reliable": True,
        "consumption_kwh": 1000.0,
    }


def test_billed_electricity_usage_reports_kwh_for_basic_meter():
    sensor = _sensor(RedEnergyBilledUsageSensor, BILLED, SERVICE_TYPE_ELECTRICITY)

    assert sensor.name == "Billed Electricity Usage"
    assert sensor.native_value == 1000.0
    assert sensor.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert "consumption_kwh" not in sensor.extra_state_attributes


def test_billed_average_daily_usage():
    gas = _sensor(RedEnergyBilledAverageDailyUsageSensor, BILLED)
    elec = _sensor(RedEnergyBilledAverageDailyUsageSensor, BILLED, SERVICE_TYPE_ELECTRICITY)

    assert gas.name == "Billed Average Daily Usage"
    assert gas.native_value == 40.0
    assert gas.native_unit_of_measurement == "MJ/d"
    assert gas.state_class == SensorStateClass.MEASUREMENT
    assert elec.native_value == 11.11
    assert elec.native_unit_of_measurement == "kWh/d"


def test_billed_average_daily_cost_is_gst_inclusive():
    sensor = _sensor(RedEnergyBilledAverageDailyCostSensor, BILLED)

    assert sensor.name == "Billed Average Daily Cost"
    assert sensor.native_value == 2.22
    assert sensor.native_unit_of_measurement == "AUD/d"
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.extra_state_attributes["gst_basis"] == "inclusive"


@pytest.mark.parametrize(
    "cls",
    [RedEnergyBilledUsageSensor, RedEnergyBilledAverageDailyUsageSensor, RedEnergyBilledAverageDailyCostSensor],
)
def test_billed_sensors_unknown_without_billed_data(cls):
    sensor = _sensor(cls, None)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes is None
    if cls is RedEnergyBilledUsageSensor:
        assert sensor.last_reset is None


@pytest.mark.parametrize(
    "cls",
    [RedEnergyBilledAverageDailyUsageSensor, RedEnergyBilledAverageDailyCostSensor],
)
def test_billed_averages_unknown_when_source_value_missing(cls):
    billed = {**BILLED, "consumption_mj": None, "total_charges_dollar": None}

    assert _sensor(cls, billed).native_value is None


READING = {
    "meter_number": "MTR0001",
    "reading_date": "2026-03-31",
    "previous_read": 1000.0,
    "current_read": 1091.0,
    "read_type": "R",
    "estimated": False,
    "from_date": "2026-01-01",
    "to_date": "2026-03-31",
}


def _read_sensor(cls, reading):
    coordinator = MagicMock()
    coordinator.get_meter_reading = MagicMock(return_value=reading)
    return cls(coordinator, _config_entry(), "2000002", SERVICE_TYPE_GAS)


def test_previous_and_current_read_sensors():
    previous = _read_sensor(RedEnergyPreviousReadSensor, READING)
    current = _read_sensor(RedEnergyCurrentReadSensor, READING)

    assert previous.name == "Previous Read"
    assert previous.unique_id == "red_energy_entry1_2000002_gas_previous_read"
    assert previous.native_value == 1000.0
    assert previous.state_class is None
    assert current.name == "Current Read"
    assert current.native_value == 1091.0
    assert current.state_class == SensorStateClass.TOTAL_INCREASING
    for sensor in (previous, current):
        assert sensor.native_unit_of_measurement == UnitOfVolume.CUBIC_METERS
        assert sensor.device_class == SensorDeviceClass.GAS
        assert sensor.extra_state_attributes == {
            "meter_number": "MTR0001",
            "reading_date": "2026-03-31",
            "read_type": "R",
            "estimated": False,
            "from_date": "2026-01-01",
            "to_date": "2026-03-31",
        }


@pytest.mark.parametrize("cls", [RedEnergyPreviousReadSensor, RedEnergyCurrentReadSensor])
def test_read_sensors_unknown_without_reading(cls):
    sensor = _read_sensor(cls, None)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes is None
