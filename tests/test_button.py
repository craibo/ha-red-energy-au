"""Tests for Red Energy button platform."""
from __future__ import annotations

import os


def test_button_file_exists():
    """Test that button.py exists and is included as a platform."""
    integration_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "custom_components", "red_energy"
    )

    button_path = os.path.join(integration_path, "button.py")
    assert os.path.exists(button_path), "button.py should exist for button platform"

    # __init__.py should include BUTTON platform
    init_path = os.path.join(integration_path, "__init__.py")
    with open(init_path, 'r') as f:
        content = f.read()
    assert "Platform.BUTTON" in content


