"""Tests for _async_update_data's transient-network-error retry behaviour.

See https://github.com/craibo/ha-red-energy-au/issues/93's follow-up
discussion: a DNS blip or connection reset during a poll previously had to
wait the full 30-minute update_interval before the next attempt, since HA's
DataUpdateCoordinator has no backoff of its own. _async_update_data now
retries a few times within the same cycle for exactly those transient error
types, leaving auth/API/session-closed errors to fail fast as before.
"""
import logging
from datetime import datetime, timezone

import aiohttp
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import UPDATE_RETRY_ATTEMPTS


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    return hass


@pytest.fixture
def coordinator(mock_hass):
    with patch(
        "custom_components.red_energy.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        coordinator = RedEnergyDataCoordinator(
            hass=mock_hass,
            username="test_user",
            password="test_pass",
            selected_accounts=["prop1"],
            services=["electricity"],
        )
    coordinator.api = AsyncMock()
    coordinator.api._access_token = "test_token"
    return coordinator


@pytest.mark.asyncio
async def test_retries_transient_client_error_then_succeeds(coordinator, caplog):
    """A ClientError on the first attempt(s) is retried, not surfaced immediately."""
    caplog.set_level(logging.WARNING)
    success_result = {"usage_data": {"prop1": {}}}

    call_count = 0

    async def flaky_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise aiohttp.ClientConnectionError("Cannot connect to host")
        return success_result

    with patch.object(coordinator, "_async_update_data_once", side_effect=flaky_once):
        with patch("custom_components.red_energy.coordinator.asyncio.sleep", new=AsyncMock()):
            result = await coordinator._async_update_data()

    assert result == success_result
    assert call_count == 2
    assert "Transient error fetching red_energy data" in caplog.text


@pytest.mark.asyncio
async def test_retries_timeout_error_then_succeeds(coordinator):
    """A bare TimeoutError (e.g. asyncio.timeout expiry) is retried the same way."""
    success_result = {"usage_data": {"prop1": {}}}
    call_count = 0

    async def flaky_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TimeoutError("timed out")
        return success_result

    with patch.object(coordinator, "_async_update_data_once", side_effect=flaky_once):
        with patch("custom_components.red_energy.coordinator.asyncio.sleep", new=AsyncMock()):
            result = await coordinator._async_update_data()

    assert result == success_result
    assert call_count == 2


@pytest.mark.asyncio
async def test_gives_up_after_exhausting_retry_attempts(coordinator):
    """Persistent transient errors are still raised once retries run out - not swallowed."""
    with patch.object(
        coordinator,
        "_async_update_data_once",
        side_effect=aiohttp.ClientConnectionError("Cannot connect to host"),
    ):
        with patch("custom_components.red_energy.coordinator.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            with pytest.raises(aiohttp.ClientConnectionError):
                await coordinator._async_update_data()

    # Retries happen between attempts only, not after the final failed attempt.
    assert mock_sleep.await_count == UPDATE_RETRY_ATTEMPTS - 1


@pytest.mark.asyncio
async def test_does_not_retry_auth_error(coordinator):
    """Auth failures are wrapped as UpdateFailed by _async_update_data_once and
    must fail immediately - retrying can't fix bad credentials."""
    with patch.object(
        coordinator,
        "_async_update_data_once",
        side_effect=UpdateFailed("Authentication failed: bad credentials"),
    ):
        with patch("custom_components.red_energy.coordinator.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()

    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_retry_closed_session_error(coordinator):
    """A closed aiohttp session (RuntimeError, e.g. HA shutting down mid-poll)
    must fail immediately - an in-cycle retry can't succeed while the shared
    client session stays closed."""
    with patch.object(
        coordinator,
        "_async_update_data_once",
        side_effect=RuntimeError("Session is closed"),
    ):
        with patch("custom_components.red_energy.coordinator.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            with pytest.raises(RuntimeError, match="Session is closed"):
                await coordinator._async_update_data()

    mock_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_update_data_once_propagates_client_error_unwrapped(coordinator):
    """_async_update_data_once must let aiohttp.ClientError/TimeoutError through
    as-is (not wrapped in UpdateFailed), so the retry loop in
    _async_update_data can recognize and retry them."""
    coordinator._customer_data = {"id": "customer1"}
    coordinator._last_metadata_refresh_date = datetime.now(timezone.utc).date()
    coordinator._properties = [
        {
            "id": "prop1",
            "name": "Property 1",
            "services": [
                {"type": "electricity", "consumer_number": "123", "active": True},
            ],
        }
    ]
    coordinator.api.get_usage_data = AsyncMock(
        side_effect=aiohttp.ClientConnectionError("DNS timeout")
    )

    with pytest.raises(aiohttp.ClientConnectionError):
        await coordinator._async_update_data_once()
