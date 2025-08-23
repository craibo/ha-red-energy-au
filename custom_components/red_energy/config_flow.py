"""Config flow for Red Energy integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RedEnergyAPI, RedEnergyAPIError, RedEnergyAuthError
from .mock_api import MockRedEnergyAPI
from .const import (
    CONF_CLIENT_ID,
    DATA_ACCOUNTS,
    DATA_CUSTOMER_DATA,
    DATA_SELECTED_ACCOUNTS,
    DOMAIN,
    ERROR_AUTH_FAILED,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_CLIENT_ID,
    ERROR_NO_ACCOUNTS,
    ERROR_UNKNOWN,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
    STEP_ACCOUNT_SELECT,
    STEP_SERVICE_SELECT,
    STEP_USER,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_CLIENT_ID): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    # Use mock API for testing - replace with RedEnergyAPI for production
    api = MockRedEnergyAPI(session)
    
    try:
        # Test authentication
        auth_success = await api.test_credentials(
            data[CONF_USERNAME],
            data[CONF_PASSWORD], 
            data[CONF_CLIENT_ID]
        )
        
        if not auth_success:
            raise InvalidAuth
        
        # Get customer data and properties
        customer_data = await api.get_customer_data()
        properties = await api.get_properties()
        
        if not properties:
            raise NoAccounts
        
        # Return info that you want to store in the config entry.
        return {
            DATA_CUSTOMER_DATA: customer_data,
            DATA_ACCOUNTS: properties,
            "title": customer_data.get("name", "Red Energy Account")
        }
    except RedEnergyAuthError:
        raise InvalidAuth
    except RedEnergyAPIError:
        raise CannotConnect
    except Exception as err:
        _LOGGER.exception("Unexpected exception")
        raise UnknownError from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Red Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_data: Dict[str, Any] = {}
        self._customer_data: Dict[str, Any] = {}
        self._accounts: list[Dict[str, Any]] = []
        self._selected_accounts: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = ERROR_CANNOT_CONNECT
            except InvalidAuth:
                errors["base"] = ERROR_AUTH_FAILED
            except InvalidClientId:
                errors[CONF_CLIENT_ID] = ERROR_INVALID_CLIENT_ID
            except NoAccounts:
                errors["base"] = ERROR_NO_ACCOUNTS
            except UnknownError:
                errors["base"] = ERROR_UNKNOWN
            else:
                # Store user input and validation results
                self._user_data = user_input
                self._customer_data = info[DATA_CUSTOMER_DATA]
                self._accounts = info[DATA_ACCOUNTS]
                
                # Check if we already have this account configured
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME]}_{user_input[CONF_CLIENT_ID]}"
                )
                self._abort_if_unique_id_configured()
                
                # Move to account selection
                if len(self._accounts) == 1:
                    # Only one account, auto-select it
                    self._selected_accounts = [self._accounts[0].get("id", "0")]
                    return await self.async_step_service_select()
                else:
                    return await self.async_step_account_select()

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "client_id_help": "You need to capture the client_id from your Red Energy mobile app using a network monitoring tool like Proxyman."
            }
        )

    async def async_step_account_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle account selection."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            selected = user_input.get(DATA_SELECTED_ACCOUNTS, [])
            if not selected:
                errors[DATA_SELECTED_ACCOUNTS] = "select_account"
            else:
                self._selected_accounts = selected
                return await self.async_step_service_select()

        # Build account selection options
        account_options = {}
        for account in self._accounts:
            account_id = account.get("id", "unknown")
            account_name = account.get("name", f"Account {account_id}")
            address = account.get("address", {})
            display_name = f"{account_name}"
            if address:
                display_name += f" - {address.get('street', '')}, {address.get('city', '')}"
            account_options[account_id] = display_name

        schema = vol.Schema({
            vol.Required(DATA_SELECTED_ACCOUNTS): vol.In(account_options),
        })

        return self.async_show_form(
            step_id=STEP_ACCOUNT_SELECT,
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "account_count": str(len(self._accounts))
            }
        )

    async def async_step_service_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle service type selection."""
        if user_input is not None:
            # Combine all configuration data
            config_data = {
                **self._user_data,
                DATA_SELECTED_ACCOUNTS: self._selected_accounts,
                "services": user_input.get("services", [SERVICE_TYPE_ELECTRICITY])
            }
            
            title = self._customer_data.get("name", "Red Energy")
            if len(self._selected_accounts) > 1:
                title += f" ({len(self._selected_accounts)} accounts)"
                
            return self.async_create_entry(
                title=title,
                data=config_data
            )

        # Service selection schema
        service_options = {
            SERVICE_TYPE_ELECTRICITY: "Electricity",
            SERVICE_TYPE_GAS: "Gas",
        }
        
        schema = vol.Schema({
            vol.Required("services", default=[SERVICE_TYPE_ELECTRICITY]): vol.All(
                vol.Ensure_list, [vol.In(service_options)]
            ),
        })

        return self.async_show_form(
            step_id=STEP_SERVICE_SELECT,
            data_schema=schema,
            description_placeholders={
                "selected_accounts": str(len(self._selected_accounts))
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RedEnergyOptionsFlowHandler:
        """Create the options flow."""
        return RedEnergyOptionsFlowHandler(config_entry)


class RedEnergyOptionsFlowHandler(config_entries.OptionsFlow):
    """Red Energy config flow options handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_services = self.config_entry.data.get("services", [SERVICE_TYPE_ELECTRICITY])
        
        service_options = {
            SERVICE_TYPE_ELECTRICITY: "Electricity",
            SERVICE_TYPE_GAS: "Gas",
        }
        
        schema = vol.Schema({
            vol.Required("services", default=current_services): vol.All(
                vol.Ensure_list, [vol.In(service_options)]
            ),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidClientId(HomeAssistantError):
    """Error to indicate invalid client ID."""


class NoAccounts(HomeAssistantError):
    """Error to indicate no accounts found."""


class UnknownError(HomeAssistantError):
    """Error to indicate unknown error."""