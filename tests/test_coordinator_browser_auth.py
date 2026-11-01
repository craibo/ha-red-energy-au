"""Coordinator auth for browser sign-in entries (issue #103)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.red_energy.api import RedEnergyAPIError, RedEnergyAuthError
from custom_components.red_energy.const import (
    AUTH_METHOD_BROWSER,
    AUTH_METHOD_PASSWORD,
    CONF_AUTH_METHOD,
    CONF_REFRESH_TOKEN,
)
from custom_components.red_energy.coordinator import RedEnergyDataCoordinator


def make_coordinator(auth_method: str, refresh_token: str | None = "rt-1"):
    hass = MagicMock()
    entry = MagicMock()
    entry.data = {
        CONF_AUTH_METHOD: auth_method,
        "username": "test@example.com",
        CONF_REFRESH_TOKEN: refresh_token,
    }
    with patch(
        "custom_components.red_energy.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        coordinator = RedEnergyDataCoordinator(
            hass=hass,
            username="test@example.com",
            password="" if auth_method == AUTH_METHOD_BROWSER else "testpass",
            selected_accounts=["1000001"],
            services=["electricity"],
            config_entry=entry,
            auth_method=auth_method,
            refresh_token=refresh_token,
        )
    return coordinator, hass, entry


@pytest.mark.asyncio
async def test_browser_entry_authenticates_with_refresh_token():
    coordinator, _, _ = make_coordinator(AUTH_METHOD_BROWSER)
    coordinator.api.authenticate_with_refresh_token = AsyncMock(return_value=True)
    coordinator.api.authenticate = AsyncMock()

    await coordinator._async_ensure_authenticated()

    coordinator.api.authenticate_with_refresh_token.assert_awaited_once_with("rt-1")
    coordinator.api.authenticate.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_entry_still_uses_password():
    coordinator, _, _ = make_coordinator(AUTH_METHOD_PASSWORD, refresh_token=None)
    coordinator.api.authenticate = AsyncMock(return_value=True)

    await coordinator._async_ensure_authenticated()

    coordinator.api.authenticate.assert_awaited_once_with("test@example.com", "testpass")


@pytest.mark.asyncio
async def test_already_authenticated_skips_login():
    coordinator, _, _ = make_coordinator(AUTH_METHOD_BROWSER)
    coordinator.api._access_token = "at-1"
    coordinator.api.authenticate_with_refresh_token = AsyncMock()

    await coordinator._async_ensure_authenticated()

    coordinator.api.authenticate_with_refresh_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_rejected_refresh_token_raises_config_entry_auth_failed():
    coordinator, _, _ = make_coordinator(AUTH_METHOD_BROWSER)
    coordinator.api.authenticate_with_refresh_token = AsyncMock(
        side_effect=RedEnergyAuthError("Token refresh rejected")
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data_once()


@pytest.mark.asyncio
async def test_password_auth_failure_still_update_failed():
    coordinator, _, _ = make_coordinator(AUTH_METHOD_PASSWORD, refresh_token=None)
    coordinator.api.authenticate = AsyncMock(side_effect=RedEnergyAuthError("bad password"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data_once()


@pytest.mark.asyncio
async def test_browser_transient_refresh_failure_is_update_failed():
    coordinator, _, _ = make_coordinator(AUTH_METHOD_BROWSER)
    coordinator.api.authenticate_with_refresh_token = AsyncMock(
        side_effect=RedEnergyAPIError("Token refresh failed with HTTP 503")
    )

    with pytest.raises(UpdateFailed) as exc:
        await coordinator._async_update_data_once()
    assert not isinstance(exc.value, ConfigEntryAuthFailed)


def test_rotated_refresh_token_is_persisted_to_entry():
    coordinator, hass, entry = make_coordinator(AUTH_METHOD_BROWSER)

    coordinator.api._set_refresh_token("rt-2")

    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["data"][CONF_REFRESH_TOKEN] == "rt-2"
    assert kwargs["data"]["username"] == "test@example.com"


def test_unchanged_refresh_token_is_not_rewritten():
    coordinator, hass, _ = make_coordinator(AUTH_METHOD_BROWSER)

    coordinator._async_persist_refresh_token("rt-1")

    hass.config_entries.async_update_entry.assert_not_called()


def test_password_entry_does_not_persist_refresh_tokens():
    coordinator, hass, _ = make_coordinator(AUTH_METHOD_PASSWORD, refresh_token=None)

    coordinator.api._set_refresh_token("rt-9")

    hass.config_entries.async_update_entry.assert_not_called()
