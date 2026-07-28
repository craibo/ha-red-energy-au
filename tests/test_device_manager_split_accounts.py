"""Test device naming when electricity and gas live on separate accounts."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from custom_components.red_energy.const import (
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
)
from custom_components.red_energy.device_manager import RedEnergyDeviceManager

ADDRESS = {"street_address": "27 Sunnyside Crescent", "suburb": "Castlecrag"}


def _property_info(name, service_type, property_physical_number=None, account_number=None):
    return {
        "name": name,
        "address": ADDRESS,
        "services": [{"type": service_type}],
        "property_physical_number": property_physical_number,
        "account_number": account_number,
    }


def _fake_device(**kwargs):
    device = MagicMock()
    device.name = kwargs.get("name")
    return device


def _make_device_manager():
    mock_hass = MagicMock()
    mock_config_entry = MagicMock()
    mock_config_entry.entry_id = "entry1"

    manager = RedEnergyDeviceManager(mock_hass, mock_config_entry)
    manager._device_registry = MagicMock()
    manager._device_registry.async_get_or_create.side_effect = _fake_device
    return manager


@pytest.mark.asyncio
async def test_split_accounts_at_same_address_get_distinct_device_names():
    """Electricity and gas on separate accounts at the same address must not collide."""
    manager = _make_device_manager()

    electricity_device = await manager._create_property_device(
        "1000001",
        _property_info("27 Sunnyside Crescent, Castlecrag", SERVICE_TYPE_ELECTRICITY),
        [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
    )
    gas_device = await manager._create_property_device(
        "2000002",
        _property_info("27 Sunnyside Crescent, Castlecrag", SERVICE_TYPE_GAS),
        [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
    )

    assert electricity_device.name != gas_device.name
    assert electricity_device.name == "1000001 - Electricity"
    assert gas_device.name == "2000002 - Gas"


@pytest.mark.asyncio
async def test_device_model_reflects_accounts_own_service_not_global_toggle():
    """A gas-only account must get 'Gas Monitor', even if the global toggle enables both."""
    manager = _make_device_manager()

    await manager._create_property_device(
        "2000002",
        _property_info("27 Sunnyside Crescent, Castlecrag", SERVICE_TYPE_GAS),
        [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
    )

    _, kwargs = manager._device_registry.async_get_or_create.call_args
    assert kwargs["model"] == "Gas Monitor"


@pytest.mark.asyncio
async def test_device_name_shows_property_and_account_number():
    """When propertyPhysicalNumber and accountNumber are both present and
    distinct, the device name must read 'Property Number - Account Number - Service'."""
    manager = _make_device_manager()

    electricity_device = await manager._create_property_device(
        "82227160.7471493",
        _property_info(
            "27 Sunnyside Crescent, Castlecrag",
            SERVICE_TYPE_ELECTRICITY,
            property_physical_number="82227160",
            account_number="7471493",
        ),
        [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
    )
    gas_device = await manager._create_property_device(
        "82227160.8490263",
        _property_info(
            "27 Sunnyside Crescent, Castlecrag",
            SERVICE_TYPE_GAS,
            property_physical_number="82227160",
            account_number="8490263",
        ),
        [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
    )

    assert electricity_device.name == "82227160 - 7471493 - Electricity"
    assert gas_device.name == "82227160 - 8490263 - Gas"
