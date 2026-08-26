"""Test config migration to v10 - rename "Total" sensors to "Current Period".

"Total Cost", "Total Import Usage", "Total Export Usage", "Total Import
Cost", and "Total Export Credit" all report a partial sum accruing since
the current billing cycle's lastBillDate, not a complete/lifetime total
(see issue #78). This migration renames their sensor_type suffix so
existing entities keep their history/statistics rather than going stale
and being recreated under a new entity_id.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.red_energy.config_migration import (
    CONFIG_VERSION_10,
    CURRENT_CONFIG_VERSION,
    RedEnergyConfigMigrator,
    SENSOR_TYPE_RENAMES_V10,
)
from custom_components.red_energy.const import DOMAIN


def _make_config_entry(version=9):
    entry = MagicMock()
    entry.version = version
    entry.entry_id = "entry1"
    entry.data = {
        "username": "test@example.com",
        "password": "testpass",
        "selected_accounts": ["1000001"],
        "services": ["electricity", "gas"],
    }
    return entry


def _registry_entry(entity_id, unique_id):
    entry = MagicMock()
    entry.entity_id = entity_id
    entry.unique_id = unique_id
    entry.platform = DOMAIN
    return entry


@pytest.mark.asyncio
async def test_renames_all_five_total_sensor_unique_ids():
    entry = _make_config_entry(version=9)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    old_unique_ids = [
        "red_energy_entry1_1000001_electricity_total_cost",
        "red_energy_entry1_1000001_electricity_total_import_usage",
        "red_energy_entry1_1000001_electricity_total_export_usage",
        "red_energy_entry1_1000001_electricity_total_import_cost",
        "red_energy_entry1_1000001_electricity_total_export_credit",
    ]
    registry_entries = [
        _registry_entry(f"sensor.entity_{i}", uid) for i, uid in enumerate(old_unique_ids)
    ]

    mock_entity_registry = MagicMock()
    mock_entity_registry.async_update_entity = MagicMock()

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=mock_entity_registry
    ), patch(
        "homeassistant.helpers.entity_registry.async_entries_for_config_entry",
        return_value=registry_entries,
    ):
        migrator = RedEnergyConfigMigrator(hass)
        result = await migrator.async_migrate_config_entry(entry)

    assert result is True

    expected_new_ids = {
        "red_energy_entry1_1000001_electricity_current_period_net_cost",
        "red_energy_entry1_1000001_electricity_current_period_import_usage",
        "red_energy_entry1_1000001_electricity_current_period_export_usage",
        "red_energy_entry1_1000001_electricity_current_period_import_cost",
        "red_energy_entry1_1000001_electricity_current_period_export_credit",
    }
    actual_new_ids = {
        call.kwargs["new_unique_id"]
        for call in mock_entity_registry.async_update_entity.call_args_list
    }
    assert actual_new_ids == expected_new_ids

    hass.config_entries.async_update_entry.assert_any_call(entry, version=CURRENT_CONFIG_VERSION)


@pytest.mark.asyncio
async def test_entities_with_non_matching_sensor_type_are_untouched():
    """Entities in this config entry whose unique_id doesn't end in one of
    the renamed sensor_type suffixes (e.g. daily_import_usage) must be left alone."""
    entry = _make_config_entry(version=9)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    unrelated_entry = _registry_entry(
        "sensor.daily_import", "red_energy_entry1_1000001_electricity_daily_import_usage"
    )

    mock_entity_registry = MagicMock()
    mock_entity_registry.async_update_entity = MagicMock()

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=mock_entity_registry
    ), patch(
        "homeassistant.helpers.entity_registry.async_entries_for_config_entry",
        return_value=[unrelated_entry],
    ):
        migrator = RedEnergyConfigMigrator(hass)
        result = await migrator.async_migrate_config_entry(entry)

    assert result is True
    mock_entity_registry.async_update_entity.assert_not_called()


@pytest.mark.asyncio
async def test_already_renamed_entity_is_a_noop():
    """An entity already using the new sensor_type (e.g. set up fresh after
    this migration shipped) must not be touched again."""
    entry = _make_config_entry(version=9)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    already_renamed = _registry_entry(
        "sensor.entity_0", "red_energy_entry1_1000001_electricity_current_period_net_cost"
    )

    mock_entity_registry = MagicMock()
    mock_entity_registry.async_update_entity = MagicMock()

    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=mock_entity_registry
    ), patch(
        "homeassistant.helpers.entity_registry.async_entries_for_config_entry",
        return_value=[already_renamed],
    ):
        migrator = RedEnergyConfigMigrator(hass)
        result = await migrator._migrate_v9_to_v10(entry)

    assert result is True
    mock_entity_registry.async_update_entity.assert_not_called()


def test_config_version_10_value():
    """CONFIG_VERSION_10 == 10 is a fixed historical fact, independent of
    whichever version is CURRENT_CONFIG_VERSION today. The "is this the
    current version" and "does ConfigFlow.VERSION match" checks belong to
    whichever migration test file introduced the latest version - see
    test_config_migration_v11.py."""
    assert CONFIG_VERSION_10 == 10


def test_sensor_type_renames_v10_covers_all_total_sensors():
    """Every "total_*" sensor_type in the codebase must have a rename entry -
    otherwise a sensor slips through this migration and keeps its
    misleading name/entity_id forever for existing installs."""
    assert SENSOR_TYPE_RENAMES_V10 == {
        "total_cost": "current_period_net_cost",
        "total_import_usage": "current_period_import_usage",
        "total_export_usage": "current_period_export_usage",
        "total_import_cost": "current_period_import_cost",
        "total_export_credit": "current_period_export_credit",
    }
