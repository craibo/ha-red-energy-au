"""Config flow for Red Energy integration."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .api import (
    BrowserLogin,
    RedEnergyAPI,
    RedEnergyAPIError,
    RedEnergyAuthError,
    RedEnergyCallbackError,
)
from .config_migration import CURRENT_CONFIG_VERSION
from .data_validation import (
    build_property_display_name,
    validate_config_data,
    validate_customer_data,
    validate_properties_data,
    DataValidationError,
)
from .const import (
    ABORT_WRONG_ACCOUNT,
    AUTH_METHOD_BROWSER,
    AUTH_METHOD_PASSWORD,
    CLIENT_ID,
    CONF_AUTH_METHOD,
    CONF_CALLBACK_URL,
    CONF_ENABLE_ADVANCED_SENSORS,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DATA_ACCOUNTS,
    DATA_CUSTOMER_DATA,
    DATA_SELECTED_ACCOUNTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ERROR_AUTH_FAILED,
    ERROR_CALLBACK_EXPIRED,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_CALLBACK,
    ERROR_NO_ACCOUNTS,
    ERROR_UNKNOWN,
    SCAN_INTERVAL_OPTIONS,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
    STEP_BROWSER,
    STEP_PASSWORD,
    STEP_USER,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_BROWSER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_CALLBACK_URL): str})

# validate_customer_data's placeholder when the API omits an email.
_UNKNOWN_CUSTOMER_EMAIL = "unknown@redenergy.com.au"


async def _async_fetch_account_info(api: RedEnergyAPI) -> dict[str, Any]:
    """Fetch and validate customer + properties for an authenticated client."""
    raw_customer_data = await api.get_customer_data()
    raw_properties = await api.get_properties()
    if not raw_properties:
        raise NoAccounts

    customer_data = validate_customer_data(raw_customer_data)
    properties = validate_properties_data(raw_properties)
    _LOGGER.info("Validated %d properties during setup", len(properties))
    return {
        DATA_CUSTOMER_DATA: customer_data,
        DATA_ACCOUNTS: properties,
        "title": customer_data.get("name", "Red Energy Account"),
    }


def _browser_unique_id(customer_data: dict[str, Any]) -> str:
    """Stable identity for a browser sign-in entry: the customer's email
    (lower-cased by validate_customer_data), else their customer ID."""
    email = customer_data.get("email", "")
    if email and email != _UNKNOWN_CUSTOMER_EMAIL:
        return email
    return str(customer_data["id"])


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    # First validate configuration data format
    try:
        validate_config_data(data)
    except DataValidationError as err:
        _LOGGER.error(
            "Configuration validation failed: %s. "
            "Ensure you have valid Red Energy credentials",
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
            data[CONF_PASSWORD]
        )
        
        if not auth_success:
            _LOGGER.error(
                "Authentication failed for user %s - credentials rejected by Red Energy API. "
                "Please verify username and password are correct",
                data[CONF_USERNAME]
            )
            raise InvalidAuth
        
        return await _async_fetch_account_info(api)
    except NoAccounts:
        raise
    except RedEnergyAuthError as err:
        _LOGGER.error(
            "Red Energy authentication error for user %s: %s. "
            "This typically indicates invalid credentials. "
            "Verify username/password work in Red Energy app.",
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

    # Must match CURRENT_CONFIG_VERSION in config_migration.py, or Home
    # Assistant core will never call async_migrate_entry - it only migrates
    # when an entry's stored version differs from this class attribute.
    VERSION = CURRENT_CONFIG_VERSION

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._browser_api: RedEnergyAPI | None = None
        self._browser_login: BrowserLogin | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick password or browser (SSO / email code) sign-in."""
        return self.async_show_menu(
            step_id=STEP_USER, menu_options=[STEP_PASSWORD, STEP_BROWSER]
        )

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Sign in with Red Energy email and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = ERROR_CANNOT_CONNECT
            except InvalidAuth:
                errors["base"] = ERROR_AUTH_FAILED
            except NoAccounts:
                errors["base"] = ERROR_NO_ACCOUNTS
            except UnknownError:
                errors["base"] = ERROR_UNKNOWN
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                result = self._async_create_account_entry(
                    info, {**user_input, CONF_AUTH_METHOD: AUTH_METHOD_PASSWORD}
                )
                if result is not None:
                    return result
                errors["base"] = ERROR_NO_ACCOUNTS

        return self.async_show_form(
            step_id=STEP_PASSWORD,
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_browser(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Sign in through Red Energy's hosted page in the user's browser
        (Google/Apple/Microsoft SSO or emailed code - issue #103), then paste
        the au.com.redenergy://callback URL it redirects to."""
        errors: dict[str, str] = {}

        if self._browser_api is None:
            self._browser_api = RedEnergyAPI(async_get_clientsession(self.hass))
        api = self._browser_api

        if self._browser_login is None:
            try:
                self._browser_login = await api.async_create_browser_login()
            except (aiohttp.ClientError, TimeoutError, RedEnergyAPIError) as err:
                _LOGGER.error("Could not start Red Energy browser sign-in: %s", err)
                return self.async_abort(reason=ERROR_CANNOT_CONNECT)

        if user_input is not None:
            try:
                await api.async_complete_browser_login(
                    user_input[CONF_CALLBACK_URL], self._browser_login
                )
                info = await _async_fetch_account_info(api)
            except RedEnergyCallbackError as err:
                errors["base"] = (
                    ERROR_CALLBACK_EXPIRED if err.reason == "expired" else ERROR_INVALID_CALLBACK
                )
            except RedEnergyAuthError as err:
                _LOGGER.error("Red Energy browser sign-in failed: %s", err)
                errors["base"] = ERROR_AUTH_FAILED
            except NoAccounts:
                errors["base"] = ERROR_NO_ACCOUNTS
            except (RedEnergyAPIError, DataValidationError, aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.error("Red Energy browser sign-in could not connect: %s", err)
                errors["base"] = ERROR_CANNOT_CONNECT
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Red Energy browser sign-in")
                errors["base"] = ERROR_UNKNOWN
            else:
                unique_id = _browser_unique_id(info[DATA_CUSTOMER_DATA])
                await self.async_set_unique_id(unique_id)

                if self.source == config_entries.SOURCE_REAUTH:
                    self._abort_if_unique_id_mismatch(reason=ABORT_WRONG_ACCOUNT)
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data_updates={CONF_REFRESH_TOKEN: api.refresh_token},
                    )

                self._abort_if_unique_id_configured()
                result = self._async_create_account_entry(
                    info,
                    {
                        CONF_AUTH_METHOD: AUTH_METHOD_BROWSER,
                        CONF_USERNAME: unique_id,
                        CONF_REFRESH_TOKEN: api.refresh_token,
                    },
                )
                if result is not None:
                    return result
                errors["base"] = ERROR_NO_ACCOUNTS

        return self.async_show_form(
            step_id=STEP_BROWSER,
            data_schema=STEP_BROWSER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"auth_url": self._browser_login.auth_url},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Saved browser sign-in expired - sign in through the browser again.

        Only browser entries raise ConfigEntryAuthFailed (see coordinator),
        so reauth always means browser sign-in.
        """
        return await self.async_step_browser()

    def _async_create_account_entry(
        self, info: dict[str, Any], auth_data: dict[str, Any]
    ) -> FlowResult | None:
        """Create the entry for every discovered account, or None if no
        account has a usable ID."""
        accounts = info[DATA_ACCOUNTS]
        customer_data = info[DATA_CUSTOMER_DATA]
        _LOGGER.info("CONFIG FLOW - Retrieved %d validated properties", len(accounts))
        for idx, account in enumerate(accounts):
            _LOGGER.info(
                "  Property %d: id=%s name=%s services=%d",
                idx, account.get("id"), account.get("name"), len(account.get("services", [])),
            )

        # Auto-select all accounts - properties are already validated with IDs
        selected_accounts = [account["id"] for account in accounts]
        if not selected_accounts:
            _LOGGER.error("No valid account IDs found in properties. Raw accounts: %s", accounts)
            return None

        # Accounts are now selected individually and each only ever bills
        # one service, so there's nothing left for a service-type toggle to
        # do - always monitor both.
        config_data = {
            **auth_data,
            DATA_SELECTED_ACCOUNTS: selected_accounts,
            "services": [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
        }
        title = customer_data.get("name", "Red Energy")
        if len(selected_accounts) > 1:
            title += f" ({len(selected_accounts)} properties)"
        return self.async_create_entry(title=title, data=config_data)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RedEnergyOptionsFlowHandler:
        """Create the options flow."""
        return RedEnergyOptionsFlowHandler()


class RedEnergyOptionsFlowHandler(config_entries.OptionsFlow):
    """Red Energy config flow options handler."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        entry = self.config_entry
        current_selected_accounts = entry.data.get(DATA_SELECTED_ACCOUNTS, [])

        # Reuse the coordinator's own RedEnergyAPI client rather than creating
        # a new one. A separate client would share the same underlying aiohttp
        # session/cookie jar but hold its own auth lock, so it could race the
        # coordinator's in-flight authentication and break the Okta redirect.
        account_options: dict[str, str] = {}
        try:
            coordinator = self.hass.data[DOMAIN][entry.entry_id]["coordinator"]
            raw_properties = await coordinator.api.get_properties()
            for account in validate_properties_data(raw_properties):
                account_id = account["id"]
                service_label = "/".join(
                    s.get("type", "").title() for s in account.get("services", []) if s.get("type")
                )
                account_options[account_id] = build_property_display_name(
                    account_id, account, service_label
                )
        except Exception as err:
            _LOGGER.warning("Could not refresh account list for options flow: %s", err)
            # Fall back to the accounts already known to the config entry so the
            # form can still be shown even if the API is temporarily unreachable.
            account_options = {
                account_id: account_id for account_id in current_selected_accounts
            }

        if user_input is not None:
            new_selected_accounts = user_input.get(
                "accounts", current_selected_accounts
            )

            # entry.data (not entry.options) is what the coordinator reads, so
            # the account selection change must be written there to take
            # effect. Services are no longer user-configurable here - each
            # account only ever bills one service, so both are always
            # requested and per-account filtering (see sensor.py) determines
            # what's actually created.
            if set(new_selected_accounts) != set(current_selected_accounts):
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        DATA_SELECTED_ACCOUNTS: new_selected_accounts,
                        "services": [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)

            # Update coordinator polling interval if changed. The coordinator
            # may not be available (e.g. setup failed or is still retrying),
            # in which case there's nothing running to update live - the
            # entry data change above still applies on the next successful
            # setup, so this must degrade gracefully rather than crash the
            # options form.
            coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")

            if coordinator is not None:
                new_interval_key = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                # Convert string key to seconds value
                if isinstance(new_interval_key, str):
                    new_interval_seconds = SCAN_INTERVAL_OPTIONS.get(new_interval_key, DEFAULT_SCAN_INTERVAL)
                else:
                    new_interval_seconds = new_interval_key

                if new_interval_seconds != coordinator.update_interval.total_seconds():
                    coordinator.update_interval = timedelta(seconds=new_interval_seconds)
                    _LOGGER.info("Updated polling interval to %d seconds", new_interval_seconds)
            else:
                _LOGGER.warning(
                    "Coordinator not available for entry %s - options saved, "
                    "polling interval will apply on next successful setup",
                    entry.entry_id,
                )

            return self.async_create_entry(title="", data=user_input)

        # Get current configuration
        current_options = entry.options
        current_scan_interval = current_options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_advanced_sensors = current_options.get(CONF_ENABLE_ADVANCED_SENSORS, False)

        # Create interval display options
        interval_options = {}
        for key, seconds in SCAN_INTERVAL_OPTIONS.items():
            if seconds == 900:
                interval_options[key] = "15 minutes"
            elif seconds == 1800:
                interval_options[key] = "30 minutes (default)"
            elif seconds == 3600:
                interval_options[key] = "1 hour"
            elif seconds == 7200:
                interval_options[key] = "2 hours"
            elif seconds == 14400:
                interval_options[key] = "4 hours"

        # Default selection includes accounts already selected, even if the
        # API call above failed to confirm they still exist.
        accounts_default = [
            account_id
            for account_id in current_selected_accounts
            if account_id in account_options
        ] or current_selected_accounts

        schema = vol.Schema({
            vol.Required("accounts", default=accounts_default): cv.multi_select(account_options),
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


class NoAccounts(HomeAssistantError):
    """Error to indicate no accounts found."""


class UnknownError(HomeAssistantError):
    """Error to indicate unknown error."""