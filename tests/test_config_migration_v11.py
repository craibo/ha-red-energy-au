"""Test config migration to v11 - rename Projected Charges to Projected
Net Cost.

The original "Projected Charges" sensor (issue #75) didn't disclose that
it's energy-only (it excludes the daily service/supply charge, see the
new "Projected Charges" sensor that replaces it and includes the service
charge, issue #77). This migration renames the old sensor's sensor_type
suffix to "projected_net_cost" so existing entities keep their
history/statistics rather than going stale and being recreated under a
new entity_id.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.red_energy.config_migration import (
    CONFIG_VERSION_11,
    CURRENT_CONFIG_VERSION,
    RedEnergyConfigMigrator,
    SENSOR_TYPE_RENAMES_V11,
)
from custom_components.red_energy.const import DOMAIN


def _make_config_entry(version=10):
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
async def test_renames_projected_charges_unique_id():
    entry = _make_config_entry(version=10)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    registry_entries = [
        _registry_entry(
            "sensor.entity_0", "red_energy_entry1_1000001_electricity_projected_charges"
        )
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

    mock_entity_registry.async_update_entity.assert_called_once_with(
        "sensor.entity_0",
        new_unique_id="red_energy_entry1_1000001_electricity_projected_net_cost",
    )

    hass.config_entries.async_update_entry.assert_any_call(entry, version=CURRENT_CONFIG_VERSION)


@pytest.mark.asyncio
async def test_entities_with_non_matching_sensor_type_are_untouched():
    entry = _make_config_entry(version=10)
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
        result = await migrator._migrate_v10_to_v11(entry)

    assert result is True
    mock_entity_registry.async_update_entity.assert_not_called()


@pytest.mark.asyncio
async def test_already_renamed_entity_is_a_noop():
    entry = _make_config_entry(version=10)
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    already_renamed = _registry_entry(
        "sensor.entity_0",
        "red_energy_entry1_1000001_electricity_projected_net_cost",
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
        result = await migrator._migrate_v10_to_v11(entry)

    assert result is True
    mock_entity_registry.async_update_entity.assert_not_called()


def test_config_version_11_is_current():
    assert CURRENT_CONFIG_VERSION == CONFIG_VERSION_11
    assert CONFIG_VERSION_11 == 11


def test_sensor_type_renames_v11():
    assert SENSOR_TYPE_RENAMES_V11 == {
        "projected_charges": "projected_net_cost",
    }


def test_config_flow_version_matches_current_config_version():
    """Home Assistant core only calls async_migrate_entry when
    ConfigEntry.version != ConfigFlow.VERSION - if these two drift apart,
    every migration in this file becomes dead code for existing entries,
    regardless of how correct the migration logic itself is."""
    from custom_components.red_energy.config_flow import ConfigFlow

    assert ConfigFlow.VERSION == CURRENT_CONFIG_VERSION
