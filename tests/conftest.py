"""Pytest configuration and fixtures for Red Energy tests."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

# Add the project root to the path so we can import custom_components
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
async def hass():
    """Create a minimal Home Assistant instance for testing."""
    hass_instance = MagicMock(spec=HomeAssistant)
    hass_instance.data = {}
    hass_instance.config_entries = MagicMock()
    hass_instance.config_entries._entries = {}
    hass_instance.async_block_till_done = MagicMock(return_value=None)
    
    # Create real device and entity registries
    device_registry_instance = dr.DeviceRegistry(hass_instance)
    entity_registry_instance = er.EntityRegistry(hass_instance)
    
    # Mock the async_get functions to return our instances
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dr, "async_get", lambda h: device_registry_instance)
        mp.setattr(er, "async_get", lambda h: entity_registry_instance)
        yield hass_instance

