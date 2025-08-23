"""Test the Red Energy coordinator."""
from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timedelta


def test_coordinator_file_exists():
    """Test that coordinator.py exists."""
    coordinator_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "coordinator.py"
    )
    assert os.path.exists(coordinator_path)


def test_coordinator_has_required_classes():
    """Test that coordinator.py has the required classes."""
    coordinator_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "coordinator.py"
    )
    
    with open(coordinator_path, 'r') as f:
        content = f.read()
    
    # Check for required classes and methods
    assert "class RedEnergyDataCoordinator" in content
    assert "_async_update_data" in content
    assert "async_refresh_credentials" in content
    assert "get_property_data" in content
    assert "get_service_usage" in content


def test_data_validation_file_exists():
    """Test that data_validation.py exists."""
    validation_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "data_validation.py"
    )
    assert os.path.exists(validation_path)


def test_data_validation_functions():
    """Test that data validation functions exist."""
    validation_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "data_validation.py"
    )
    
    with open(validation_path, 'r') as f:
        content = f.read()
    
    # Check for required validation functions
    assert "validate_customer_data" in content
    assert "validate_properties_data" in content
    assert "validate_usage_data" in content
    assert "validate_config_data" in content


def test_diagnostics_file_exists():
    """Test that diagnostics.py exists."""
    diagnostics_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "diagnostics.py"
    )
    assert os.path.exists(diagnostics_path)


def test_diagnostics_functions():
    """Test that diagnostics functions exist."""
    diagnostics_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "diagnostics.py"
    )
    
    with open(diagnostics_path, 'r') as f:
        content = f.read()
    
    # Check for required diagnostic functions
    assert "async_get_config_entry_diagnostics" in content
    assert "async_get_device_diagnostics" in content


def test_mock_api_credentials():
    """Test that mock API has valid test credentials."""
    mock_api_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "mock_api.py"
    )
    
    # Read the file content and check for credential structure
    with open(mock_api_path, 'r') as f:
        content = f.read()
    
    # Check that the file contains the expected credential structure
    assert "VALID_CREDENTIALS" in content
    assert "test@example.com" in content
    assert "testpass" in content
    assert "test-client-id-123" in content
    assert "demo@redenergy.com.au" in content


def test_data_validation_basic():
    """Test basic data validation functionality."""
    import importlib.util
    
    validation_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "data_validation.py"
    )
    
    spec = importlib.util.spec_from_file_location("data_validation", validation_path)
    validation_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validation_module)
    
    # Test config data validation
    validate_config = getattr(validation_module, "validate_config_data", None)
    assert validate_config is not None
    
    # Test with valid config
    valid_config = {
        "username": "test@example.com",
        "password": "testpass",
        "client_id": "test-client-id-123"
    }
    
    # Should not raise exception
    try:
        validate_config(valid_config)
    except Exception as e:
        assert False, f"Valid config failed validation: {e}"


def test_sensor_updates():
    """Test that sensor.py has been updated for Stage 3."""
    sensor_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "sensor.py"
    )
    
    with open(sensor_path, 'r') as f:
        content = f.read()
    
    # Check for Stage 3 sensor classes
    assert "RedEnergyUsageSensor" in content
    assert "RedEnergyCostSensor" in content
    assert "RedEnergyTotalUsageSensor" in content
    assert "RedEnergyBaseSensor" in content
    assert "CoordinatorEntity" in content
    
    # Check for proper device classes
    assert "SensorDeviceClass" in content
    assert "SensorStateClass" in content


def test_init_updates():
    """Test that __init__.py has been updated for Stage 3."""
    init_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "__init__.py"
    )
    
    with open(init_path, 'r') as f:
        content = f.read()
    
    # Check for Stage 3 updates
    assert "RedEnergyDataCoordinator" in content
    assert "async_config_entry_first_refresh" in content
    assert "ConfigEntryNotReady" in content
    assert "UpdateFailed" in content


def test_file_count():
    """Test that we have the expected number of files."""
    integration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy"
    )
    
    # Count Python files
    python_files = []
    for file in os.listdir(integration_path):
        if file.endswith('.py'):
            python_files.append(file)
    
    # Expected files for Stage 3
    expected_files = [
        "__init__.py",
        "api.py", 
        "config_flow.py",
        "const.py",
        "coordinator.py",
        "data_validation.py", 
        "diagnostics.py",
        "mock_api.py",
        "sensor.py"
    ]
    
    for expected in expected_files:
        assert expected in python_files, f"Missing expected file: {expected}"
    
    # We should have at least 9 Python files
    assert len(python_files) >= 9, f"Expected at least 9 Python files, found {len(python_files)}: {python_files}"