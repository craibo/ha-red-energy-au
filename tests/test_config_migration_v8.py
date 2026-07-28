"""Test config migration to v8 - composite property IDs.

Regression test for GitHub issue #51: properties sharing accountNumber used
to collapse into a single device/entity set. v8 switches to a composite ID
(propertyPhysicalNumber + accountNumber) and migrates existing devices and
entities in place so history/statistics are preserved.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.config_migration import (
    CONFIG_VERSION_8,
    RedEnergyConfigMigrator,
)
from custom_components.red_energy.const import DOMAIN


def _make_config_entry(selected_accounts):
    entry = MagicMock()
    entry.version = 7
    entry.entry_id = "entry1"
    entry.data = {
        "username": "test@example.com",
        "password": "testpass",
        "selected_accounts": selected_accounts,
        "services": ["electricity", "gas"],
    }
    return entry


def _raw_properties():
    return [
        {
            "accountNumber": 1001100,
            "propertyPhysicalNumber": 1111111,
            "address": {"street": "1 FIRST STREET", "suburb": "SUBURBIA"},
            "consumers": [{"consumerNumber": 2000001, "utility": "E", "status": "ON"}],
        },
        {
            "accountNumber": 1001100,
            "propertyPhysicalNumber": 2222222,
            "address": {"street": "2 SECOND STREET", "suburb": "SUBURBIA"},
            "consumers": [{"consumerNumber": 2000002, "utility": "E", "status": "ON"}],
        },
    ]


@pytest.mark.asyncio
async def test_v7_entry_with_collapsed_account_id_gets_composite_ids():
    """The one property previously selected under the shared accountNumber
    is remapped to its new composite ID."""
    entry = _make_config_entry(selected_accounts=["1001100"])
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    mock_device = MagicMock()
    mock_device.id = "device1"
    mock_device.name = "1001100 - Electricity"

    mock_entity = MagicMock()
    mock_entity.entity_id = "sensor.red_energy_1001100_daily_import_usage"
    mock_entity.unique_id = f"{DOMAIN}_entry1_1001100_electricity_daily_import_usage"

    with patch(
        "custom_components.red_energy.api.RedEnergyAPI.authenticate",
        new=AsyncMock(return_value=True),
    ), patch(
        "custom_components.red_energy.api.RedEnergyAPI.get_properties",
        new=AsyncMock(return_value=_raw_properties()),
    ), patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "homeassistant.helpers.device_registry.async_get"
    ) as mock_dr_get, patch(
        "homeassistant.helpers.entity_registry.async_get"
    ) as mock_er_get, patch(
        "homeassistant.helpers.entity_registry.async_entries_for_device",
        return_value=[mock_entity],
    ):
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = mock_device
        mock_dr_get.return_value = mock_device_registry

        mock_entity_registry = MagicMock()
        mock_er_get.return_value = mock_entity_registry

        migrator = RedEnergyConfigMigrator(hass)
        result = await migrator._migrate_v7_to_v8(entry)

    assert result is True

    # Only one of the two properties was previously selected/visible, so only
    # that one is remapped - the newly-discovered sibling property is left
    # for the user to add via the options flow, with no history to preserve.
    mock_entity_registry.async_update_entity.assert_called_once_with(
        mock_entity.entity_id, new_unique_id=f"{DOMAIN}_entry1_1111111.1001100_electricity_daily_import_usage"
    )
    mock_device_registry.async_update_device.assert_called_once_with(
        mock_device.id, new_identifiers={(DOMAIN, "1111111.1001100")}
    )

    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data["selected_accounts"] == ["1111111.1001100"]


@pytest.mark.asyncio
async def test_v7_entry_with_shared_property_physical_number_still_remaps_both():
    """Regression test: some accounts have it the other way round from issue
    #51 - propertyPhysicalNumber is the SHARED field (one physical address,
    separate elec/gas billing accounts) and accountNumber is unique per
    property. The old ID (pre-v8) fell through to accountNumber alone in
    this shape, so both previously-selected properties must still be
    remapped to their new composite IDs."""
    entry = _make_config_entry(selected_accounts=["7471493", "8490263"])
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    raw_properties = [
        {
            "accountNumber": 7471493,
            "propertyPhysicalNumber": 82227160,
            "address": {"street": "1 EXAMPLE STREET", "suburb": "TESTVILLE"},
            "consumers": [{"consumerNumber": 3000001, "utility": "E", "status": "ON"}],
        },
        {
            "accountNumber": 8490263,
            "propertyPhysicalNumber": 82227160,
            "address": {"street": "1 EXAMPLE STREET", "suburb": "TESTVILLE"},
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
        result = await migrator._migrate_v7_to_v8(entry)

    assert result is True

    new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert set(new_data["selected_accounts"]) == {"82227160.7471493", "82227160.8490263"}


@pytest.mark.asyncio
async def test_v7_entry_with_already_unique_ids_is_a_noop():
    """Properties that already had distinct accountNumbers keep their IDs."""
    entry = _make_config_entry(selected_accounts=["1000001"])
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    raw_properties = [
        {
            "accountNumber": 1000001,
            "address": {"street": "1 FIRST STREET", "suburb": "SUBURBIA"},
            "consumers": [{"consumerNumber": 2000001, "utility": "E", "status": "ON"}],
        }
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
        result = await migrator._migrate_v7_to_v8(entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_v7_to_v8_api_failure_does_not_fail_migration():
    """If the API can't be reached during migration, existing config is kept
    and the fix still applies going forward for new setups."""
    entry = _make_config_entry(selected_accounts=["1001100"])
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    with patch(
        "custom_components.red_energy.api.RedEnergyAPI.authenticate",
        new=AsyncMock(side_effect=Exception("network error")),
    ), patch(
        "homeassistant.helpers.aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ):
        migrator = RedEnergyConfigMigrator(hass)
        result = await migrator._migrate_v7_to_v8(entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_not_called()


def test_config_version_8_exists():
    assert CONFIG_VERSION_8 == 8
