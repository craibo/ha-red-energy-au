"""Config flow for Red Energy integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .api import RedEnergyAPI, RedEnergyAPIError, RedEnergyAuthError
from .data_validation import validate_config_data, DataValidationError
from .const import (
    CONF_CLIENT_ID,
    CONF_ENABLE_ADVANCED_SENSORS,
    CONF_SCAN_INTERVAL,
    DATA_ACCOUNTS,
    DATA_CUSTOMER_DATA,
    DATA_SELECTED_ACCOUNTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ERROR_AUTH_FAILED,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_CLIENT_ID,
    ERROR_NO_ACCOUNTS,
    ERROR_UNKNOWN,
    SCAN_INTERVAL_OPTIONS,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
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
    # First validate configuration data format
    try:
        validate_config_data(data)
    except DataValidationError as err:
        _LOGGER.error(
            "Configuration validation failed: %s. "
            "Ensure you have valid Red Energy credentials and client_id from mobile app",
            err
        )
        raise InvalidAuth from err
    
    session = async_get_clientsession(hass)
    # Use real Red Energy API
    api = RedEnergyAPI(session)
    
    try:
        # Test authentication
        auth_success = await api.test_credentials(
            data[CONF_USERNAME],
            data[CONF_PASSWORD], 
            data[CONF_CLIENT_ID]
        )
        
        if not auth_success:
            _LOGGER.error(
                "Authentication failed for user %s - credentials rejected by Red Energy API. "
                "Please verify: 1) Username/password are correct, 2) Client ID is valid and captured correctly from mobile app",
                data[CONF_USERNAME]
            )
            raise InvalidAuth
        
        # Get customer data and properties
        raw_customer_data = await api.get_customer_data()
        raw_properties = await api.get_properties()
        
        if not raw_properties:
            raise NoAccounts
        
        # Validate the data
        from .data_validation import validate_customer_data, validate_properties_data
        
        customer_data = validate_customer_data(raw_customer_data)
        properties = validate_properties_data(raw_properties)
        
        _LOGGER.info("Validated %d properties during setup", len(properties))
        
        # Return info that you want to store in the config entry.
        return {
            DATA_CUSTOMER_DATA: customer_data,
            DATA_ACCOUNTS: properties,
            "title": customer_data.get("name", "Red Energy Account")
        }
    except RedEnergyAuthError as err:
        _LOGGER.error(
            "Red Energy authentication error for user %s: %s. "
            "This typically indicates invalid credentials or client_id. "
            "Verify username/password work in Red Energy app and client_id is correctly captured.",
            data[CONF_USERNAME], err
        )
        raise InvalidAuth from err
    except DataValidationError as err:
        _LOGGER.error(
            "Data validation error for user %s: %s. "
            "The API response format may have changed or returned invalid data.",
            data[CONF_USERNAME], err
        )
        raise CannotConnect from err
    except RedEnergyAPIError as err:
        _LOGGER.error(
            "Red Energy API error for user %s: %s. "
            "This may indicate network issues, API unavailability, or invalid API responses.",
            data[CONF_USERNAME], err
        )
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.exception(
            "Unexpected error during Red Energy validation for user %s: %s. "
            "This may indicate a bug in the integration or unexpected API behavior.",
            data[CONF_USERNAME], err
        )
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
                
                _LOGGER.info("=" * 80)
                _LOGGER.info("CONFIG FLOW - Retrieved %d validated properties:", len(self._accounts))
                for idx, account in enumerate(self._accounts):
                    _LOGGER.info("  Property %d:", idx)
                    _LOGGER.info("    - ID: %s", account.get("id"))
                    _LOGGER.info("    - Name: %s", account.get("name"))
                    _LOGGER.info("    - Services: %d", len(account.get("services", [])))
                _LOGGER.info("=" * 80)
                
                # Check if we already have this account configured
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME]}_{user_input[CONF_CLIENT_ID]}"
                )
                self._abort_if_unique_id_configured()
                
                # Auto-select all accounts - properties are already validated with IDs
                self._selected_accounts = [account["id"] for account in self._accounts]
                _LOGGER.info("Auto-selected %d accounts: %s", len(self._selected_accounts), self._selected_accounts)
                
                if not self._selected_accounts:
                    _LOGGER.error("No valid account IDs found in properties. Raw accounts: %s", self._accounts)
                    errors["base"] = ERROR_NO_ACCOUNTS
                else:
                    return await self.async_step_service_select()

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "client_id_help": "You need to capture the client_id from your Red Energy mobile app using a network monitoring tool like Proxyman."
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
                title += f" ({len(self._selected_accounts)} properties)"
                
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
            vol.Required("services", default=[SERVICE_TYPE_ELECTRICITY]): cv.multi_select(service_options),
        })

        return self.async_show_form(
            step_id=STEP_SERVICE_SELECT,
            data_schema=schema,
            description_placeholders={
                "account_count": str(len(self._selected_accounts))
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update coordinator polling interval if changed
            entry_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
            coordinator = entry_data["coordinator"]
            
            new_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if new_interval != coordinator.update_interval.total_seconds():
                coordinator.update_interval = timedelta(seconds=new_interval)
                _LOGGER.info("Updated polling interval to %d seconds", new_interval)
            
            return self.async_create_entry(title="", data=user_input)

        # Get current configuration
        current_services = self.config_entry.data.get("services", [SERVICE_TYPE_ELECTRICITY])
        current_options = self.config_entry.options
        current_scan_interval = current_options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_advanced_sensors = current_options.get(CONF_ENABLE_ADVANCED_SENSORS, False)
        
        service_options = {
            SERVICE_TYPE_ELECTRICITY: "Electricity",
            SERVICE_TYPE_GAS: "Gas",
        }
        
        # Create interval display options
        interval_options = {}
        for key, seconds in SCAN_INTERVAL_OPTIONS.items():
            if seconds == 60:
                interval_options[key] = "1 minute"
            elif seconds == 300:
                interval_options[key] = "5 minutes (default)"
            elif seconds == 900:
                interval_options[key] = "15 minutes"
            elif seconds == 1800:
                interval_options[key] = "30 minutes"  
            elif seconds == 3600:
                interval_options[key] = "1 hour"
        
        schema = vol.Schema({
            vol.Required("services", default=current_services): cv.multi_select(service_options),
            vol.Required(CONF_SCAN_INTERVAL, default=current_scan_interval): vol.In(interval_options),
            vol.Required(CONF_ENABLE_ADVANCED_SENSORS, default=current_advanced_sensors): bool,
        })
        
        # Convert current_scan_interval to minutes for display
        if isinstance(current_scan_interval, str):
            current_scan_interval_seconds = SCAN_INTERVAL_OPTIONS.get(current_scan_interval, DEFAULT_SCAN_INTERVAL)
        else:
            current_scan_interval_seconds = current_scan_interval
        
        current_interval_minutes = current_scan_interval_seconds // 60

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "current_interval": f"{current_interval_minutes} minutes",
            }
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