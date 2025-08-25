"""Test the Red Energy config flow basic structure."""
from __future__ import annotations

import importlib.util
import os


def test_config_flow_file_exists():
    """Test that config_flow.py exists."""
    config_flow_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "config_flow.py"
    )
    assert os.path.exists(config_flow_path)


def test_config_flow_has_required_classes():
    """Test that config_flow.py has the required classes."""
    config_flow_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "config_flow.py"
    )
    
    with open(config_flow_path, 'r') as f:
        content = f.read()
    
    # Check for required classes and methods
    assert "class ConfigFlow" in content
    assert "async_step_user" in content
    assert "async_step_account_select" in content
    assert "async_step_service_select" in content
    assert "RedEnergyOptionsFlowHandler" in content


def test_translations_exist():
    """Test that translation files exist."""
    translations_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "translations", "en.json"
    )
    assert os.path.exists(translations_path)


def test_mock_api_file_removed():
    """Test that mock API file has been removed."""
    mock_api_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "mock_api.py"
    )
    assert not os.path.exists(mock_api_path)


def test_api_file_exists():
    """Test that API file exists."""
    api_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "api.py"
    )
    assert os.path.exists(api_path)


def test_manifest_has_config_flow():
    """Test that manifest.json includes config_flow."""
    import json
    
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "manifest.json"
    )
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    assert manifest.get("config_flow") is True
    assert "voluptuous" in manifest.get("requirements", [])


def test_constants_include_config_flow_constants():
    """Test that const.py includes config flow constants."""
    import importlib.util
    
    const_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy", "const.py"
    )
    
    spec = importlib.util.spec_from_file_location("const", const_path)
    const_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const_module)
    
    # Check for config flow constants
    assert hasattr(const_module, "STEP_USER")
    assert hasattr(const_module, "STEP_ACCOUNT_SELECT")
    assert hasattr(const_module, "STEP_SERVICE_SELECT")
    assert hasattr(const_module, "ERROR_AUTH_FAILED")
    assert hasattr(const_module, "CONF_CLIENT_ID")