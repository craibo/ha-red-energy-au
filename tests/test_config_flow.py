"""Test the Red Energy config flow."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from custom_components.red_energy.const import (
    CONF_CLIENT_ID,
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
    CONF_CLIENT_ID: "test-client-id-123",
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
    flow.async_create_entry = AsyncMock(return_value={"type": "create_entry"})
    
    mock_validation_result = {
        "customer_data": MOCK_CUSTOMER_DATA,
        "accounts": [MOCK_PROPERTIES[0]],  # Single account
        "title": "Test User"
    }
    
    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        return_value=mock_validation_result,
    ):
        # Step 1: User input
        result = await flow.async_step_user(MOCK_USER_INPUT)
        
        # Should go directly to service selection for single account
        assert result["type"] == "form"
        assert result["step_id"] == "service_select"
        
        # Step 2: Service selection
        service_input = {"services": ["electricity"]}
        result = await flow.async_step_service_select(service_input)
        
        # Should create entry
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
    flow.async_create_entry = AsyncMock(return_value={"type": "create_entry"})
    flow.async_show_form = AsyncMock(return_value={
        "type": "form",
        "step_id": "account_select"
    })
    
    mock_validation_result = {
        "customer_data": MOCK_CUSTOMER_DATA,
        "accounts": MOCK_PROPERTIES,  # Multiple accounts
        "title": "Test User"
    }
    
    with patch(
        "custom_components.red_energy.config_flow.validate_input",
        return_value=mock_validation_result,
    ):
        # Step 1: User input
        result = await flow.async_step_user(MOCK_USER_INPUT)
        
        # Should go to account selection for multiple accounts
        flow.async_show_form.assert_called_once()
        called_args = flow.async_show_form.call_args
        assert called_args[1]["step_id"] == "account_select"


def test_validate_input_structure():
    """Test that validate_input returns expected structure."""
    # This is a unit test for the function structure
    from custom_components.red_energy.config_flow import STEP_USER_DATA_SCHEMA
    
    # Test that schema accepts valid data
    validated = STEP_USER_DATA_SCHEMA(MOCK_USER_INPUT)
    assert validated[CONF_USERNAME] == "test@example.com"
    assert validated[CONF_PASSWORD] == "testpass" 
    assert validated[CONF_CLIENT_ID] == "test-client-id-123"


def test_domain_constant():
    """Test that domain constant is correct."""
    assert DOMAIN == "red_energy"