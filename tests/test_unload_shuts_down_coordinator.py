"""Test that unloading the integration shuts down the coordinator's refresh loop."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.red_energy import async_unload_entry
from custom_components.red_energy.const import DOMAIN


@pytest.mark.asyncio
async def test_unload_entry_shuts_down_coordinator():
    """Unloading must stop the coordinator's scheduled refresh timer.

    Without this, the old coordinator's periodic refresh can still fire (or
    be mid-authenticate) after unload, racing a freshly-created coordinator's
    authenticate() call on the same shared aiohttp session during a reload
    (e.g. after changing the selected accounts) - breaking the Okta redirect
    until the next full Home Assistant restart clears it.
    """
    entry = MagicMock()
    entry.entry_id = "entry1"

    coordinator = MagicMock()
    coordinator.async_shutdown = AsyncMock()

    state_manager = MagicMock()
    state_manager.async_save_states = AsyncMock()

    device_manager = MagicMock()
    device_manager.async_cleanup_orphaned_entities = AsyncMock()

    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "state_manager": state_manager,
                "device_manager": device_manager,
            }
        }
    }

    result = await async_unload_entry(hass, entry)

    assert result is True
    coordinator.async_shutdown.assert_awaited_once()
