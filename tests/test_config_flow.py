"""Test the Red Energy config flow."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from custom_components.red_energy.const import (
    DATA_SELECTED_ACCOUNTS,
    DOMAIN,
    ERROR_AUTH_FAILED,
    ERROR_CANNOT_CONNECT,
    ERROR_NO_ACCOUNTS,
)
from custom_components.red_energy.config_flow import (
    CannotConnect,
    InvalidAuth,
    NoAccounts,
)

MOCK_USER_INPUT = {
    CONF_USERNAME: "test@example.com",
    CONF_PASSWORD: "testpass",
}

MOCK_CUSTOMER_DATA = {
    "id": "12345",
    "name": "Test User",
    "email": "test@example.com"
}

MOCK_PROPERTIES = [
    {
        "id": "prop-001",
        "name": "Main Residence",
        "address": {"street": "123 Test St", "city": "Melbourne"}
    }
]


@pytest.mark.asyncio
async def test_form():
    """Test we get the form."""
    hass = AsyncMock(spec=HomeAssistant)
    
    from custom_components.red_energy.config_flow import ConfigFlow
    flow = ConfigFlow()
    flow.hass = hass
    
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_form_auth_error():
    """Test we handle auth errors."""
    hass = AsyncMock(spec=HomeAssistant)
    
    from custom_components.red_energy.config_flow import ConfigFlow
    flow = ConfigFlow()
    flow.hass = hass
    
    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        side_effect=InvalidAuth,
    ):
        result = await flow.async_step_user(MOCK_USER_INPUT)

    assert result["type"] == "form"
    assert result["errors"] == {"base": ERROR_AUTH_FAILED}


@pytest.mark.asyncio
async def test_form_cannot_connect():
    """Test we handle cannot connect error."""
    hass = AsyncMock(spec=HomeAssistant)
    
    from custom_components.red_energy.config_flow import ConfigFlow
    flow = ConfigFlow()
    flow.hass = hass
    
    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        side_effect=CannotConnect,
    ):
        result = await flow.async_step_user(MOCK_USER_INPUT)

    assert result["type"] == "form"
    assert result["errors"] == {"base": ERROR_CANNOT_CONNECT}


@pytest.mark.asyncio
async def test_form_no_accounts():
    """Test we handle no accounts error.""" 
    hass = AsyncMock(spec=HomeAssistant)
    
    from custom_components.red_energy.config_flow import ConfigFlow
    flow = ConfigFlow()
    flow.hass = hass
    
    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        side_effect=NoAccounts,
    ):
        result = await flow.async_step_user(MOCK_USER_INPUT)

    assert result["type"] == "form"
    assert result["errors"] == {"base": ERROR_NO_ACCOUNTS}


@pytest.mark.asyncio
async def test_successful_single_account_flow():
    """Test successful config flow with single account."""
    hass = AsyncMock(spec=HomeAssistant)
    
    from custom_components.red_energy.config_flow import ConfigFlow
    flow = ConfigFlow()
    flow.hass = hass
    
    # Mock async_set_unique_id and _abort_if_unique_id_configured
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = AsyncMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    
    mock_validation_result = {
        "customer_data": MOCK_CUSTOMER_DATA,
        "accounts": [MOCK_PROPERTIES[0]],  # Single account
        "title": "Test User"
    }
    
    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        return_value=mock_validation_result,
    ):
        # Accounts are auto-selected and both services are always requested
        # (no separate service-selection step) - the config flow creates
        # the entry directly after account discovery.
        result = await flow.async_step_user(MOCK_USER_INPUT)

        flow.async_create_entry.assert_called_once()


@pytest.mark.asyncio
async def test_successful_multi_account_flow():
    """Test successful config flow with multiple accounts."""
    hass = AsyncMock(spec=HomeAssistant)
    
    from custom_components.red_energy.config_flow import ConfigFlow
    flow = ConfigFlow()
    flow.hass = hass
    
    # Mock methods
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = AsyncMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    
    # Add two properties to simulate multiple accounts
    mock_validation_result = {
        "customer_data": MOCK_CUSTOMER_DATA,
        "accounts": [MOCK_PROPERTIES[0], {**MOCK_PROPERTIES[0], "id": "prop-002"}],
        "title": "Test User"
    }
    
    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        return_value=mock_validation_result,
    ):
        # Both accounts are auto-selected and the entry is created directly
        result = await flow.async_step_user(MOCK_USER_INPUT)

        assert result is not None
        flow.async_create_entry.assert_called_once()
        _, kwargs = flow.async_create_entry.call_args
        assert kwargs["data"][DATA_SELECTED_ACCOUNTS] == ["prop-001", "prop-002"]


def test_validate_input_structure():
    """Test that validate_input returns expected structure."""
    # This is a unit test for the function structure
    from custom_components.red_energy.config_flow import STEP_USER_DATA_SCHEMA
    
    # Test that schema accepts valid data
    validated = STEP_USER_DATA_SCHEMA(MOCK_USER_INPUT)
    assert validated[CONF_USERNAME] == "test@example.com"
    assert validated[CONF_PASSWORD] == "testpass"


@pytest.mark.asyncio
async def test_config_flow_always_requests_both_services():
    """Both electricity and gas are always requested - no service picker.

    Each account only ever bills one service (Red Energy splits electricity
    and gas onto separate accounts), so a service-type toggle has nothing
    left to do; per-account filtering in sensor.py determines what's
    actually created.
    """
    hass = AsyncMock(spec=HomeAssistant)

    from custom_components.red_energy.config_flow import ConfigFlow
    from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS

    flow = ConfigFlow()
    flow.hass = hass
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = AsyncMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    mock_validation_result = {
        "customer_data": MOCK_CUSTOMER_DATA,
        "accounts": [MOCK_PROPERTIES[0]],
        "title": "Test User"
    }

    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        return_value=mock_validation_result,
    ):
        await flow.async_step_user(MOCK_USER_INPUT)

    _, kwargs = flow.async_create_entry.call_args
    assert set(kwargs["data"]["services"]) == {SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS}


def test_domain_constant():
    """Test that domain constant is correct."""
    assert DOMAIN == "red_energy"