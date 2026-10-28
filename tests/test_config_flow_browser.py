"""Browser sign-in config flow and reauth (issue #103)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow

from custom_components.red_energy.api import (
    BrowserLogin,
    RedEnergyAuthError,
    RedEnergyCallbackError,
)
from custom_components.red_energy.config_flow import ConfigFlow
from custom_components.red_energy.const import (
    ABORT_WRONG_ACCOUNT,
    AUTH_METHOD_BROWSER,
    CONF_AUTH_METHOD,
    CONF_CALLBACK_URL,
    CONF_REFRESH_TOKEN,
    DATA_SELECTED_ACCOUNTS,
    ERROR_AUTH_FAILED,
    ERROR_BROWSER_SIGN_IN_FAILED,
    ERROR_CALLBACK_EXPIRED,
    ERROR_INVALID_CALLBACK,
    ERROR_NO_ACCOUNTS,
)

LOGIN = BrowserLogin(
    auth_url="https://login.example.com/oauth2/default/v1/authorize?state=s-1",
    code_verifier="v" * 48,
    state="s-1",
)
CALLBACK = {CONF_CALLBACK_URL: "au.com.redenergy://callback?code=c-1&state=s-1"}
CUSTOMER = {"id": "1000001", "name": "Test User", "email": "Test@Example.com"}
PROPERTIES = [
    {
        "accountNumber": "1000001",
        "consumers": [{"consumerNumber": "2000002", "utility": "E", "status": "ON"}],
        "address": {"street": "1 Example Street", "suburb": "Testville", "state": "NSW", "postcode": "2000"},
    }
]


def make_api():
    api = MagicMock()
    api.async_create_browser_login = AsyncMock(return_value=LOGIN)
    api.async_complete_browser_login = AsyncMock()
    api.get_customer_data = AsyncMock(return_value=CUSTOMER)
    api.get_properties = AsyncMock(return_value=PROPERTIES)
    api.refresh_token = "rt-1"
    return api


def make_flow(source: str = config_entries.SOURCE_USER) -> ConfigFlow:
    flow = ConfigFlow()
    flow.hass = AsyncMock(spec=HomeAssistant)
    flow.context = {"source": source}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


@pytest.fixture
def api():
    api = make_api()
    with patch("custom_components.red_energy.config_flow.RedEnergyAPI", return_value=api), patch(
        "custom_components.red_energy.config_flow.async_get_clientsession"
    ):
        yield api


@pytest.mark.asyncio
async def test_user_step_offers_both_sign_in_methods():
    result = await make_flow().async_step_user()
    assert result["type"] == "menu"
    assert result["menu_options"] == ["password", "browser"]


@pytest.mark.asyncio
async def test_browser_step_shows_sign_in_link(api):
    result = await make_flow().async_step_browser()
    assert result["type"] == "form"
    assert result["step_id"] == "browser"
    assert result["description_placeholders"]["auth_url"] == LOGIN.auth_url
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_browser_step_creates_entry_with_refresh_token_only(api):
    flow = make_flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    await flow.async_step_browser()
    result = await flow.async_step_browser(CALLBACK)

    assert result["type"] == "create_entry"
    _, kwargs = flow.async_create_entry.call_args
    data = kwargs["data"]
    assert kwargs["title"] == "Test User"
    assert data[CONF_AUTH_METHOD] == AUTH_METHOD_BROWSER
    assert data[CONF_REFRESH_TOKEN] == "rt-1"
    assert data["username"] == "test@example.com"
    assert "password" not in data
    assert data[DATA_SELECTED_ACCOUNTS] == ["1000001"]
    api.async_complete_browser_login.assert_awaited_once_with(CALLBACK[CONF_CALLBACK_URL], LOGIN)
    flow.async_set_unique_id.assert_awaited_once_with("test@example.com")
    flow._abort_if_unique_id_configured.assert_called_once()


@pytest.mark.asyncio
async def test_browser_step_invalid_callback_keeps_same_link(api):
    api.async_complete_browser_login.side_effect = RedEnergyCallbackError("bad", "invalid")
    flow = make_flow()
    await flow.async_step_browser()
    result = await flow.async_step_browser({CONF_CALLBACK_URL: "nonsense"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": ERROR_INVALID_CALLBACK}
    assert result["description_placeholders"]["auth_url"] == LOGIN.auth_url
    api.async_create_browser_login.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_step_expired_code_shows_error(api):
    api.async_complete_browser_login.side_effect = RedEnergyCallbackError("late", "expired")
    flow = make_flow()
    await flow.async_step_browser()
    result = await flow.async_step_browser(CALLBACK)
    assert result["errors"] == {"base": ERROR_CALLBACK_EXPIRED}


@pytest.mark.asyncio
async def test_browser_step_okta_error_is_sign_in_failed_not_bad_password(api):
    """A cancelled/denied SSO sign-in must not say "Invalid username or password"."""
    api.async_complete_browser_login.side_effect = RedEnergyAuthError("access_denied")
    flow = make_flow()
    await flow.async_step_browser()
    result = await flow.async_step_browser(CALLBACK)
    assert result["errors"] == {"base": ERROR_BROWSER_SIGN_IN_FAILED}
    assert result["errors"] != {"base": ERROR_AUTH_FAILED}


@pytest.mark.asyncio
async def test_browser_step_no_properties(api):
    api.get_properties.return_value = []
    flow = make_flow()
    await flow.async_step_browser()
    result = await flow.async_step_browser(CALLBACK)
    assert result["errors"] == {"base": ERROR_NO_ACCOUNTS}


@pytest.mark.asyncio
async def test_browser_step_aborts_when_okta_unreachable(api):
    api.async_create_browser_login.side_effect = TimeoutError
    result = await make_flow().async_step_browser()
    assert result["type"] == "abort"
    assert result["reason"] == "cannot_connect"


@pytest.mark.asyncio
async def test_reauth_updates_refresh_token(api):
    flow = make_flow(config_entries.SOURCE_REAUTH)
    entry = MagicMock()
    flow._get_reauth_entry = MagicMock(return_value=entry)
    flow._abort_if_unique_id_mismatch = MagicMock()
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": "abort", "reason": "reauth_successful"}
    )

    result = await flow.async_step_reauth({CONF_AUTH_METHOD: AUTH_METHOD_BROWSER})
    assert result["step_id"] == "browser"
    result = await flow.async_step_browser(CALLBACK)

    assert result["reason"] == "reauth_successful"
    flow._abort_if_unique_id_mismatch.assert_called_once_with(reason=ABORT_WRONG_ACCOUNT)
    flow.async_update_reload_and_abort.assert_called_once_with(
        entry, data_updates={CONF_REFRESH_TOKEN: "rt-1"}
    )


@pytest.mark.asyncio
async def test_reauth_with_different_account_aborts(api):
    flow = make_flow(config_entries.SOURCE_REAUTH)
    flow._get_reauth_entry = MagicMock(return_value=MagicMock())
    flow._abort_if_unique_id_mismatch = MagicMock(side_effect=AbortFlow(ABORT_WRONG_ACCOUNT))
    flow.async_update_reload_and_abort = MagicMock()

    await flow.async_step_reauth({})
    with pytest.raises(AbortFlow) as exc:
        await flow.async_step_browser(CALLBACK)

    assert exc.value.reason == ABORT_WRONG_ACCOUNT
    flow.async_update_reload_and_abort.assert_not_called()
