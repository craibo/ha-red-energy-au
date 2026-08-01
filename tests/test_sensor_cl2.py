"""Tests for the CL2/TOU derived sensors (issue #61)."""
from unittest.mock import MagicMock

import pytest

from homeassistant.components.sensor import SensorStateClass

from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import (
    RedEnergyCl2CostSensor,
    RedEnergyCl2EnergySensor,
    RedEnergyCorrectedOffpeakImportSensor,
    RedEnergyCorrectedPeakImportSensor,
    RedEnergyCorrectedShoulderImportSensor,
    RedEnergyReconstructedImportCostSensor,
)

CL2_DATA = {
    "cl2_energy_kwh": 15.35,
    "corrected_peak_kwh": 3.2,
    "corrected_shoulder_kwh": 0.374,
    "corrected_offpeak_kwh": 1.1,
    "cl2_cost": 2.83,
    "reconstructed_import_cost": 19.09,
    "api_import_cost": 19.10,
    "reconciliation_difference": -0.01,
    "accepted_interval_count": 47,
    "rejected_interval_count": 1,
    "rejection_reasons": {"pricing_not_reliable": 1},
    "rates_used": {"PEAK": 0.4576, "SHOULDER": 0.41745, "OFFPEAK": 0.32483, "CL2": 0.18425},
    "rates_source": "current plan rates (no historical rate data available)",
}


def _coordinator(cl2_data=CL2_DATA):
    coordinator = MagicMock()
    coordinator.get_cl2_inference = MagicMock(return_value=cl2_data)
    return coordinator


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


@pytest.mark.parametrize(
    "sensor_cls,value_key",
    [
        (RedEnergyCl2EnergySensor, "cl2_energy_kwh"),
        (RedEnergyCorrectedPeakImportSensor, "corrected_peak_kwh"),
        (RedEnergyCorrectedShoulderImportSensor, "corrected_shoulder_kwh"),
        (RedEnergyCorrectedOffpeakImportSensor, "corrected_offpeak_kwh"),
        (RedEnergyCl2CostSensor, "cl2_cost"),
        (RedEnergyReconstructedImportCostSensor, "reconstructed_import_cost"),
    ],
)
def test_native_value_reads_from_coordinator(sensor_cls, value_key):
    coordinator = _coordinator()
    sensor = sensor_cls(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor.native_value == CL2_DATA[value_key]


@pytest.mark.parametrize(
    "sensor_cls",
    [
        RedEnergyCl2EnergySensor,
        RedEnergyCorrectedPeakImportSensor,
        RedEnergyCorrectedShoulderImportSensor,
        RedEnergyCorrectedOffpeakImportSensor,
        RedEnergyCl2CostSensor,
        RedEnergyReconstructedImportCostSensor,
    ],
)
def test_native_value_none_when_coordinator_returns_none(sensor_cls):
    coordinator = _coordinator(cl2_data=None)
    sensor = sensor_cls(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor.native_value is None


@pytest.mark.parametrize(
    "sensor_cls",
    [
        RedEnergyCl2EnergySensor,
        RedEnergyCorrectedPeakImportSensor,
        RedEnergyCorrectedShoulderImportSensor,
        RedEnergyCorrectedOffpeakImportSensor,
        RedEnergyCl2CostSensor,
        RedEnergyReconstructedImportCostSensor,
    ],
)
def test_all_cl2_sensors_are_electricity_only(sensor_cls):
    coordinator = _coordinator()
    sensor = sensor_cls(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor._electricity_only is True


@pytest.mark.parametrize(
    "sensor_cls",
    [
        RedEnergyCl2EnergySensor,
        RedEnergyCorrectedPeakImportSensor,
        RedEnergyCorrectedShoulderImportSensor,
        RedEnergyCorrectedOffpeakImportSensor,
        RedEnergyCl2CostSensor,
        RedEnergyReconstructedImportCostSensor,
    ],
)
def test_all_cl2_sensors_have_total_state_class(sensor_cls):
    coordinator = _coordinator()
    sensor = sensor_cls(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor.state_class == SensorStateClass.TOTAL


def test_cl2_energy_sensor_exposes_diagnostic_attributes():
    coordinator = _coordinator()
    sensor = RedEnergyCl2EnergySensor(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    attrs = sensor.extra_state_attributes

    assert attrs["accepted_interval_count"] == 47
    assert attrs["rejected_interval_count"] == 1
    assert attrs["rejection_reasons"] == {"pricing_not_reliable": 1}
    assert attrs["rates_used"] == CL2_DATA["rates_used"]
    assert attrs["rates_source"] == "current plan rates (no historical rate data available)"


def test_reconstructed_import_cost_sensor_exposes_reconciliation_difference():
    coordinator = _coordinator()
    sensor = RedEnergyReconstructedImportCostSensor(
        coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY
    )
    attrs = sensor.extra_state_attributes

    assert attrs["reconciliation_difference"] == -0.01
    assert attrs["api_import_cost"] == 19.10


def test_diagnostic_attributes_none_when_coordinator_returns_none():
    coordinator = _coordinator(cl2_data=None)
    sensor = RedEnergyCl2EnergySensor(coordinator, _config_entry(), "prop-001", SERVICE_TYPE_ELECTRICITY)
    assert sensor.extra_state_attributes is None
