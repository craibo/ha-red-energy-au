"""Test config migration to v9 - repair entries stuck on stale property IDs.

Follow-up regression test: the original v7->v8 migration only matched old
IDs derived from accountNumber. Accounts where propertyPhysicalNumber (not
accountNumber) is the field shared across properties had their old ID come
from accountNumber via a different branch of the pre-v8 fallback chain, so
the match silently failed and selected_accounts was left stale - and since
the entry had already advanced to version 8, the migration would never run
again on its own. v9 re-runs the same repair for entries in this state.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.config_migration import (
    CONFIG_VERSION_9,
    CURRENT_CONFIG_VERSION,
    RedEnergyConfigMigrator,
)
from custom_components.red_energy.const import DOMAIN


def _make_config_entry(selected_accounts, version=8):
    entry = MagicMock()
    entry.version = version
    entry.entry_id = "entry1"
    entry.data = {
        "username": "test@example.com",
        "password": "testpass",
        "selected_accounts": selected_accounts,
        "services": ["electricity", "gas"],
    }
    return entry


@pytest.mark.asyncio
async def test_v8_entry_stuck_with_stale_ids_gets_repaired():
    """An entry already at v8 with selected_accounts that no longer match
    any current property ID (the exact stuck state from issue #51 follow-up)
    must be repaired by re-deriving the old ID and remapping to the new one."""
    entry = _make_config_entry(selected_accounts=["7471493", "8490263"], version=8)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    raw_properties = [
        {
            "accountNumber": 7471493,
            "propertyPhysicalNumber": 82227160,
            "address": {"street": "27 SUNNYSIDE CRESCENT", "suburb": "CASTLECRAG"},
            "consumers": [{"consumerNumber": 3000001, "utility": "E", "status": "ON"}],
        },
        {
            "accountNumber": 8490263,
            "propertyPhysicalNumber": 82227160,
            "address": {"street": "27 SUNNYSIDE CRESCENT", "suburb": "CASTLECRAG"},
            "consumers": [{"consumerNumber": 3000002, "utility": "G", "status": "ON"}],
        },
    ]

    mock_device_registry = MagicMock()
    mock_device_registry.async_get_device.return_value = None
    mock_entity_registry = MagicMock()

    with patch(
        "custom_components.red_energy.api.RedEnergyAPI.authenticate",
        new=AsyncMock(return_value=True),
    ), patch(
        "custom_components.red_energy.api.RedEnergyAPI.get_properties",
        new=AsyncMock(return_value=raw_properties),
    ), patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "homeassistant.helpers.device_registry.async_get", return_value=mock_device_registry
    ), patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=mock_entity_registry
    ):
        migrator = RedEnergyConfigMigrator(hass)
        result = await migrator.async_migrate_config_entry(entry)

    assert result is True

    data_updates = [
        call.kwargs["data"]
        for call in hass.config_entries.async_update_entry.call_args_list
        if "data" in call.kwargs
    ]
    assert data_updates, "expected selected_accounts to be updated"
    final_selected = data_updates[-1]["selected_accounts"]
    assert set(final_selected) == {"82227160.7471493", "82227160.8490263"}

    hass.config_entries.async_update_entry.assert_any_call(entry, version=CURRENT_CONFIG_VERSION)


@pytest.mark.asyncio
async def test_v8_entry_with_matching_ids_is_a_noop():
    """An entry at v8 whose selected_accounts already match current property
    IDs (the fix worked correctly the first time) should not be touched."""
    entry = _make_config_entry(selected_accounts=["82227160.7471493"], version=8)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    raw_properties = [
        {
            "accountNumber": 7471493,
            "propertyPhysicalNumber": 82227160,
            "address": {"street": "27 SUNNYSIDE CRESCENT", "suburb": "CASTLECRAG"},
            "consumers": [{"consumerNumber": 3000001, "utility": "E", "status": "ON"}],
        },
    ]

    with patch(
        "custom_components.red_energy.api.RedEnergyAPI.authenticate",
        new=AsyncMock(return_value=True),
    ), patch(
        "custom_components.red_energy.api.RedEnergyAPI.get_properties",
        new=AsyncMock(return_value=raw_properties),
    ), patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ):
        migrator = RedEnergyConfigMigrator(hass)
        result = await migrator._migrate_v8_to_v9(entry)

    assert result is True
    data_updates = [
        call.kwargs["data"]
        for call in hass.config_entries.async_update_entry.call_args_list
        if "data" in call.kwargs
    ]
    assert not data_updates


def test_config_version_9_is_current():
    assert CURRENT_CONFIG_VERSION == CONFIG_VERSION_9
    assert CONFIG_VERSION_9 == 9


def test_config_flow_version_matches_current_config_version():
    """Home Assistant core only calls async_migrate_entry when
    ConfigEntry.version != ConfigFlow.VERSION - if these two drift apart,
    every migration in this file becomes dead code for existing entries,
    regardless of how correct the migration logic itself is."""
    from custom_components.red_energy.config_flow import ConfigFlow

    assert ConfigFlow.VERSION == CURRENT_CONFIG_VERSION
