"""Test the Red Energy advanced features from Stage 4."""
from __future__ import annotations

import os


def test_stage4_files_exist():
    """Test that Stage 4 files exist."""
    base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "custom_components", "red_energy")
    
    stage4_files = [
        "services.py",
        "energy.py",
    ]
    
    for file in stage4_files:
        file_path = os.path.join(base_path, file)
        assert os.path.exists(file_path), f"Stage 4 file {file} is missing"


def test_services_file_structure():
    """Test that services.py has required functions."""
    services_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "services.py"
    )
    
    with open(services_path, 'r') as f:
        content = f.read()
    
    # Check for service functions
    assert "async_setup_services" in content
    assert "async_unload_services" in content
    assert "async_refresh_data" in content
    assert "async_update_credentials" in content
    assert "async_export_data" in content


def test_energy_integration_structure():
    """Test that energy.py has required classes."""
    energy_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "energy.py"
    )
    
    with open(energy_path, 'r') as f:
        content = f.read()
    
    # Check for energy platform classes
    assert "RedEnergyEnergyPlatform" in content
    assert "async_get_config_flow_energy_sources" in content
    assert "get_energy_usage_sensors" in content
    assert "get_energy_cost_sensors" in content


def test_advanced_sensor_classes():
    """Test that advanced sensor classes exist in sensor.py."""
    sensor_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "sensor.py"
    )
    
    with open(sensor_path, 'r') as f:
        content = f.read()
    
    # Check for advanced sensor classes
    advanced_sensors = [
        "RedEnergyDailyAverageSensor",
        "RedEnergyMonthlyAverageSensor", 
        "RedEnergyPeakUsageSensor",
        "RedEnergyEfficiencySensor",
    ]
    
    for sensor_class in advanced_sensors:
        assert sensor_class in content, f"Advanced sensor {sensor_class} not found"


def test_constants_updated():
    """Test that const.py has Stage 4 constants."""
    const_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "const.py"
    )
    
    with open(const_path, 'r') as f:
        content = f.read()
    
    # Check for Stage 4 constants
    stage4_constants = [
        "SCAN_INTERVAL_OPTIONS",
        "SENSOR_TYPE_DAILY_AVERAGE",
        "SENSOR_TYPE_PEAK_USAGE",
        "SENSOR_TYPE_EFFICIENCY",
        "CONF_ENABLE_ADVANCED_SENSORS",
        "CONF_SCAN_INTERVAL",
    ]
    
    for constant in stage4_constants:
        assert constant in content, f"Stage 4 constant {constant} not found"


def test_config_flow_options_updated():
    """Test that config_flow.py has options flow updates."""
    config_flow_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "config_flow.py"
    )
    
    with open(config_flow_path, 'r') as f:
        content = f.read()
    
    # Check for options flow enhancements
    assert "CONF_SCAN_INTERVAL" in content
    assert "CONF_ENABLE_ADVANCED_SENSORS" in content
    assert "interval_options" in content
    assert "coordinator.update_interval" in content


def test_automation_examples_exist():
    """Test that automation examples file exists."""
    examples_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "AUTOMATION_EXAMPLES.md"
    )
    
    assert os.path.exists(examples_path)
    
    with open(examples_path, 'r') as f:
        content = f.read()
    
    # Check for key sections
    sections = [
        "Cost Monitoring Automations",
        "Usage Pattern Automations", 
        "Cost Optimization Automations",
        "Data Management Automations",
        "Smart Home Integration",
        "Voice Assistant Integration",
    ]
    
    for section in sections:
        assert section in content, f"Automation section {section} not found"


def test_init_services_integration():
    """Test that __init__.py includes services setup."""
    init_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "__init__.py"
    )
    
    with open(init_path, 'r') as f:
        content = f.read()
    
    # Check for services integration
    assert "async_setup_services" in content
    assert "async_unload_services" in content
    assert "if len(hass.data[DOMAIN]) == 1:" in content  # Services setup condition


def test_manifest_updated():
    """Test that manifest.json is properly configured."""
    import json
    
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "manifest.json"
    )
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Should still have required fields
    assert manifest["domain"] == "red_energy"
    assert manifest["name"] == "Red Energy"
    assert "config_flow" in manifest
    assert manifest["config_flow"] is True


def test_stage4_file_count():
    """Test that we have the expected number of files for Stage 4."""
    integration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy"
    )
    
    python_files = [f for f in os.listdir(integration_path) if f.endswith('.py')]
    
    # Expected files for Stage 4 (added services.py and energy.py)
    expected_files = [
        "__init__.py",
        "api.py",
        "config_flow.py", 
        "const.py",
        "coordinator.py",
        "data_validation.py",
        "diagnostics.py",
        "energy.py",
        "mock_api.py",
        "sensor.py",
        "services.py",
    ]
    
    for expected in expected_files:
        assert expected in python_files, f"Missing expected file: {expected}"
    
    # Should have at least 11 Python files
    assert len(python_files) >= 11, f"Expected at least 11 Python files, found {len(python_files)}: {python_files}"


def test_advanced_sensor_creation_logic():
    """Test that sensor setup includes advanced sensor logic."""
    sensor_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "sensor.py"
    )
    
    with open(sensor_path, 'r') as f:
        content = f.read()
    
    # Check for advanced sensor conditional creation
    assert "advanced_sensors_enabled" in content
    assert "CONF_ENABLE_ADVANCED_SENSORS" in content
    assert "if advanced_sensors_enabled:" in content
    

def test_efficiency_sensor_calculations():
    """Test that efficiency sensor has proper calculation logic."""
    sensor_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "sensor.py"
    )
    
    with open(sensor_path, 'r') as f:
        content = f.read()
    
    # Check for efficiency calculation components
    efficiency_components = [
        "coefficient of variation",
        "mean_usage",
        "std_dev",
        "efficiency = max(0, min(100",
        "usage_variation",
    ]
    
    for component in efficiency_components:
        assert component in content, f"Efficiency calculation component '{component}' not found"