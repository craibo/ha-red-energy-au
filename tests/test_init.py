"""Test the Red Energy integration constants and basic structure."""
from __future__ import annotations

import os
import sys

def test_integration_structure():
    """Test that the integration has the required files."""
    base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "custom_components", "red_energy")
    
    required_files = [
        "__init__.py",
        "const.py",
        "manifest.json", 
        "sensor.py"
    ]
    
    for file in required_files:
        file_path = os.path.join(base_path, file)
        assert os.path.exists(file_path), f"Required file {file} is missing"


def test_constants_import():
    """Test that constants can be imported."""
    import importlib.util
    
    const_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "custom_components", "red_energy", "const.py"
    )
    
    spec = importlib.util.spec_from_file_location("const", const_path)
    const_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const_module)
    
    assert const_module.DOMAIN == "red_energy"
    assert const_module.DEFAULT_NAME == "Red Energy"


def test_manifest_exists():
    """Test that manifest.json exists and has required structure."""
    import json
    
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "custom_components", "red_energy", "manifest.json"
    )
    
    assert os.path.exists(manifest_path)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    required_keys = ["domain", "name", "codeowners", "integration_type"]
    for key in required_keys:
        assert key in manifest, f"Required key {key} missing from manifest"
    
    assert manifest["domain"] == "red_energy"