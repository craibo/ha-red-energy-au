"""Test the Red Energy options flow account selection."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.red_energy.const import DATA_SELECTED_ACCOUNTS, DOMAIN
from custom_components.red_energy.config_flow import RedEnergyOptionsFlowHandler

MOCK_ENTRY_DATA = {
    "username": "test@example.com",
    "password": "testpass",
    DATA_SELECTED_ACCOUNTS: ["1000001"],
    "services": ["electricity"],
}

def _raw_property(account_number, utility, consumer_number, property_physical_number=None):
    return {
        "accountNumber": account_number,
        "propertyPhysicalNumber": property_physical_number,
        "displayAddresses": {"shortForm": "1 Example Street, Testville"},
        "address": {
            "suburb": "Testville",
            "state": "NSW",
            "postcode": "2068",
            "displayAddresses": {"shortForm": "1 Example Street, Testville"},
        },
        "consumers": [
            {
                "consumerNumber": consumer_number,
                "utility": utility,
                "status": "ON",
            }
        ],
    }


MOCK_PROPERTIES_RESPONSE = [
    _raw_property(1000001, "E", 3000003),
    _raw_property(2000002, "G", 4000004),
]


def _make_config_entry():
    entry = MagicMock()
    entry.data = dict(MOCK_ENTRY_DATA)
    entry.options = {}
    entry.entry_id = "test_entry_id"
    return entry


def _make_hass(entry, properties=MOCK_PROPERTIES_RESPONSE):
    coordinator = MagicMock(update_interval=MagicMock(total_seconds=lambda: 1800))
    coordinator.api.get_properties = AsyncMock(return_value=properties)
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}
    hass.config_entries.async_get_known_entry = MagicMock(return_value=entry)
    return hass


@pytest.mark.asyncio
async def test_options_init_form_lists_newly_discovered_account():
    """The options form must offer the newly-appeared account, not just the originally selected one."""
    entry = _make_config_entry()
    hass = _make_hass(entry)

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_init()

    assert result["type"] == "form"
    # The selector's option values should include the newly-discovered gas account
    schema_dict = result["data_schema"]({
        "accounts": ["1000001", "2000002"],
        "scan_interval": "30min",
        "enable_advanced_sensors": False,
    })
    assert schema_dict["accounts"] == ["1000001", "2000002"]


@pytest.mark.asyncio
async def test_options_account_labels_use_account_id_not_shared_address():
    """Checkbox labels must disambiguate accounts sharing the same address.

    Both mock properties share the display address "1 Example Street,
    Testville" (electricity and gas billed on separate accounts) - the
    label shown to the user must not be that address for both, or the
    options screen is unusable (matches the reported UI screenshot).
    """
    entry = _make_config_entry()
    hass = _make_hass(entry)

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_init()

    accounts_validator = next(
        v for k, v in result["data_schema"].schema.items() if str(k) == "accounts"
    )
    labels = accounts_validator.options

    assert labels["1000001"] == "1000001 - Electricity"
    assert labels["2000002"] == "2000002 - Gas"
    assert "1 Example Street, Testville" not in labels.values()


@pytest.mark.asyncio
async def test_options_account_labels_show_property_and_account_number():
    """When propertyPhysicalNumber and accountNumber are both present and
    distinct, labels must read 'Property Number - Account Number - Service'."""
    properties = [
        _raw_property(7471493, "E", 3000001, property_physical_number=82227160),
        _raw_property(8490263, "G", 3000002, property_physical_number=82227160),
    ]
    entry = _make_config_entry()
    entry.data = {**MOCK_ENTRY_DATA, DATA_SELECTED_ACCOUNTS: ["82227160.7471493"]}
    hass = _make_hass(entry, properties=properties)

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_init()

    accounts_validator = next(
        v for k, v in result["data_schema"].schema.items() if str(k) == "accounts"
    )
    labels = accounts_validator.options

    assert labels["82227160.7471493"] == "82227160 - 7471493 - Electricity"
    assert labels["82227160.8490263"] == "82227160 - 8490263 - Gas"


@pytest.mark.asyncio
async def test_options_submit_adds_new_account_and_reloads():
    """Selecting the new account in options must persist it and trigger a reload."""
    entry = _make_config_entry()
    hass = _make_hass(entry)
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    user_input = {
        "accounts": ["1000001", "2000002"],
        "scan_interval": "30min",
        "enable_advanced_sensors": False,
    }

    result = await flow.async_step_init(user_input)

    assert result["type"] == "create_entry"
    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["data"][DATA_SELECTED_ACCOUNTS] == ["1000001", "2000002"]
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_options_init_reuses_coordinator_api_not_a_new_client():
    """The options flow must not construct its own RedEnergyAPI.

    A second, independently-locked RedEnergyAPI sharing the coordinator's
    aiohttp session can race the coordinator's in-flight authenticate() call
    at Okta's /authorize step, causing "No redirect location found in
    authorization response". Reusing coordinator.api avoids the race and an
    unnecessary duplicate login entirely.
    """
    entry = _make_config_entry()
    hass = _make_hass(entry)

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    await flow.async_step_init()

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.api.get_properties.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_submit_always_keeps_both_services():
    """Services are no longer user-configurable - both are always requested.

    Each account only ever bills one service, so a service-type toggle has
    nothing left to do; per-account filtering in sensor.py determines what's
    actually created. Submitting options must still write both services to
    entry.data so an old entry stuck on a subset gets upgraded.
    """
    entry = _make_config_entry()
    hass = _make_hass(entry)
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    user_input = {
        "accounts": ["1000001", "2000002"],  # changed from entry's original ["1000001"]
        "scan_interval": "30min",
        "enable_advanced_sensors": False,
    }

    await flow.async_step_init(user_input)

    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["data"]["services"] == ["electricity", "gas"]


@pytest.mark.asyncio
async def test_options_submit_does_not_crash_when_coordinator_not_loaded():
    """Submitting options must not crash if the integration failed to set up.

    If setup failed (e.g. mid auth race) hass.data[DOMAIN] never gets
    populated. The options form must still save without raising KeyError -
    the polling-interval live-update is simply skipped in that case.
    """
    entry = _make_config_entry()
    hass = MagicMock()
    hass.data = {}  # DOMAIN key absent entirely - integration never set up
    hass.config_entries = MagicMock()
    hass.config_entries.async_get_known_entry = MagicMock(return_value=entry)
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    user_input = {
        "accounts": ["1000001"],
        "scan_interval": "30min",
        "enable_advanced_sensors": False,
    }

    result = await flow.async_step_init(user_input)

    assert result["type"] == "create_entry"
