"""Test config migration to v7 - always monitor both services."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.red_energy.config_migration import (
    CONFIG_VERSION_7,
    CURRENT_CONFIG_VERSION,
    RedEnergyConfigMigrator,
)
from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS


def _make_config_entry(version, services):
    entry = MagicMock()
    entry.version = version
    entry.entry_id = "entry1"
    entry.data = {
        "username": "test@example.com",
        "password": "testpass",
        "selected_accounts": ["1000001"],
        "services": services,
    }
    return entry


@pytest.mark.asyncio
async def test_v6_entry_with_electricity_only_upgrades_to_both_services():
    """An entry stuck on electricity-only (no service picker left to fix it) must be upgraded."""
    entry = _make_config_entry(version=6, services=[SERVICE_TYPE_ELECTRICITY])
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    migrator = RedEnergyConfigMigrator(hass)
    result = await migrator.async_migrate_config_entry(entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_any_call(
        entry, data={**entry.data, "services": [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS]}
    )
    hass.config_entries.async_update_entry.assert_any_call(entry, version=CURRENT_CONFIG_VERSION)


@pytest.mark.asyncio
async def test_current_version_entry_not_migrated():
    """An entry already at the current version should be left alone."""
    entry = _make_config_entry(
        version=CURRENT_CONFIG_VERSION, services=[SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS]
    )
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    migrator = RedEnergyConfigMigrator(hass)
    result = await migrator.async_migrate_config_entry(entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_not_called()


def test_config_version_7_is_current():
    assert CURRENT_CONFIG_VERSION == CONFIG_VERSION_7
