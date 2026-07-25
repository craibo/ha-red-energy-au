"""Test the Red Energy options flow account selection."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.red_energy.const import DATA_SELECTED_ACCOUNTS, DOMAIN
from custom_components.red_energy.config_flow import RedEnergyOptionsFlowHandler

MOCK_ENTRY_DATA = {
    "username": "test@example.com",
    "password": "testpass",
    DATA_SELECTED_ACCOUNTS: ["8490263"],
    "services": ["electricity"],
}

def _raw_property(account_number, utility, consumer_number):
    return {
        "accountNumber": account_number,
        "displayAddresses": {"shortForm": "27 Sunnyside Crescent, Castlecrag"},
        "address": {
            "suburb": "Castlecrag",
            "state": "NSW",
            "postcode": "2068",
            "displayAddresses": {"shortForm": "27 Sunnyside Crescent, Castlecrag"},
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
    _raw_property(8490263, "E", 4235478511),
    _raw_property(7471493, "G", 4236257811),
]


def _make_config_entry():
    entry = MagicMock()
    entry.data = dict(MOCK_ENTRY_DATA)
    entry.options = {}
    entry.entry_id = "test_entry_id"
    return entry


@pytest.mark.asyncio
async def test_options_init_form_lists_newly_discovered_account():
    """The options form must offer the newly-appeared account, not just the originally selected one."""
    entry = _make_config_entry()
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: {"coordinator": MagicMock(update_interval=MagicMock(total_seconds=lambda: 1800))}}}

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow._config_entry = entry

    with patch(
        "custom_components.red_energy.config_flow.async_get_clientsession"
    ), patch(
        "custom_components.red_energy.config_flow.RedEnergyAPI"
    ) as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.test_credentials = AsyncMock(return_value=True)
        mock_api.get_properties = AsyncMock(return_value=MOCK_PROPERTIES_RESPONSE)

        result = await flow.async_step_init()

    assert result["type"] == "form"
    # The selector's option values should include the newly-discovered gas account
    schema_dict = result["data_schema"]({
        "accounts": ["8490263", "7471493"],
        "services": ["electricity"],
        "scan_interval": "30min",
        "enable_advanced_sensors": False,
    })
    assert schema_dict["accounts"] == ["8490263", "7471493"]


@pytest.mark.asyncio
async def test_options_submit_adds_new_account_and_reloads():
    """Selecting the new account in options must persist it and trigger a reload."""
    entry = _make_config_entry()
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: {"coordinator": MagicMock(update_interval=MagicMock(total_seconds=lambda: 1800))}}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow._config_entry = entry

    user_input = {
        "accounts": ["8490263", "7471493"],
        "services": ["electricity", "gas"],
        "scan_interval": "30min",
        "enable_advanced_sensors": False,
    }

    with patch(
        "custom_components.red_energy.config_flow.async_get_clientsession"
    ), patch(
        "custom_components.red_energy.config_flow.RedEnergyAPI"
    ) as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.test_credentials = AsyncMock(return_value=True)
        mock_api.get_properties = AsyncMock(return_value=MOCK_PROPERTIES_RESPONSE)

        result = await flow.async_step_init(user_input)

    assert result["type"] == "create_entry"
    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["data"][DATA_SELECTED_ACCOUNTS] == ["8490263", "7471493"]
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_options_submit_enabling_gas_service_persists_and_reloads():
    """Turning on the Gas service checkbox must actually take effect.

    entry.data["services"] is what the coordinator reads (entry.options is
    never consulted), so toggling "gas" on in the options form must update
    entry.data and reload — otherwise the checkbox is a no-op.
    """
    entry = _make_config_entry()
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: {"coordinator": MagicMock(update_interval=MagicMock(total_seconds=lambda: 1800))}}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow._config_entry = entry

    user_input = {
        "accounts": ["8490263"],
        "services": ["electricity", "gas"],
        "scan_interval": "30min",
        "enable_advanced_sensors": False,
    }

    with patch(
        "custom_components.red_energy.config_flow.async_get_clientsession"
    ), patch(
        "custom_components.red_energy.config_flow.RedEnergyAPI"
    ) as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.test_credentials = AsyncMock(return_value=True)
        mock_api.get_properties = AsyncMock(return_value=MOCK_PROPERTIES_RESPONSE)

        await flow.async_step_init(user_input)

    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["data"]["services"] == ["electricity", "gas"]
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
