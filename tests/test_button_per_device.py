"""Test that the refresh metadata button is created once per device."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.red_energy.button import (
    RedEnergyRefreshMetadataButton,
    async_setup_entry,
)
from custom_components.red_energy.const import DOMAIN


@pytest.mark.asyncio
async def test_one_button_created_per_selected_account():
    """Every device must get its own refresh button, not just the first one."""
    coordinator = MagicMock()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["8490263", "7471493"],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    assert len(added_entities) == 2
    device_ids = {
        next(iter(e._attr_device_info["identifiers"]))[1] for e in added_entities
    }
    assert device_ids == {"8490263", "7471493"}


@pytest.mark.asyncio
async def test_button_unique_ids_do_not_collide_across_devices():
    """Each per-device button must have a distinct unique_id."""
    coordinator = MagicMock()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    button_a = RedEnergyRefreshMetadataButton(coordinator, config_entry, "8490263")
    button_b = RedEnergyRefreshMetadataButton(coordinator, config_entry, "7471493")

    assert button_a.unique_id != button_b.unique_id


@pytest.mark.asyncio
async def test_button_press_triggers_entry_wide_refresh():
    """Pressing any device's button refreshes all accounts, not just its own."""
    coordinator = MagicMock()
    coordinator.async_refresh_metadata_and_usage = AsyncMock()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"

    button = RedEnergyRefreshMetadataButton(coordinator, config_entry, "7471493")
    await button.async_press()

    coordinator.async_refresh_metadata_and_usage.assert_awaited_once()
