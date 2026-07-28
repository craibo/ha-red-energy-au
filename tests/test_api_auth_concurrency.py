"""Tests for concurrent authenticate() calls not racing each other."""
import asyncio
import pytest
from unittest.mock import AsyncMock
from custom_components.red_energy.api import RedEnergyAPI


@pytest.fixture
def api_client():
    """Create API client for testing."""
    session = AsyncMock()
    return RedEnergyAPI(session)


@pytest.mark.asyncio
async def test_concurrent_authenticate_calls_do_not_overlap(api_client, monkeypatch):
    """Two concurrent authenticate() calls must not execute the Okta flow in parallel.

    A shared aiohttp session means overlapping auth flows can corrupt Okta's
    session/cookie state and cause the authorization redirect to fail. The
    fix serializes authenticate() so a second caller waits for the first
    in-flight attempt instead of racing it.
    """
    concurrent_calls = 0
    max_concurrent = 0

    async def fake_get_session_token(username, password):
        nonlocal concurrent_calls, max_concurrent
        concurrent_calls += 1
        max_concurrent = max(max_concurrent, concurrent_calls)
        await asyncio.sleep(0.01)
        concurrent_calls -= 1
        return "session_token", "2099-01-01T00:00:00.000Z"

    async def fake_get_discovery_data():
        return {
            "authorization_endpoint": "https://example.okta.com/authorize",
            "token_endpoint": "https://example.okta.com/token",
        }

    async def fake_get_authorization_code(auth_endpoint, session_token, client_id, code_challenge):
        return "auth_code"

    async def fake_exchange_code_for_tokens(token_endpoint, auth_code, client_id, code_verifier):
        api_client._access_token = "access_token"
        api_client._refresh_token = "refresh_token"

    monkeypatch.setattr(api_client, "_get_session_token", fake_get_session_token)
    monkeypatch.setattr(api_client, "_get_discovery_data", fake_get_discovery_data)
    monkeypatch.setattr(api_client, "_get_authorization_code", fake_get_authorization_code)
    monkeypatch.setattr(api_client, "_exchange_code_for_tokens", fake_exchange_code_for_tokens)

    results = await asyncio.gather(
        api_client.authenticate("user", "pass"),
        api_client.authenticate("user", "pass"),
    )

    assert results == [True, True]
    assert max_concurrent == 1


@pytest.mark.asyncio
async def test_authenticate_clears_stale_auth_cookies_before_starting(monkeypatch):
    """A fresh authenticate() call must clear any leftover Okta/Red Energy
    session cookies before starting the /authn -> /authorize handshake.

    Home Assistant's global aiohttp session is reused across every config
    entry reload, so cookies from a previous, now-abandoned auth attempt
    (e.g. a stale JSESSIONID) can linger and desync Okta's server-side
    session state from the fresh sessionToken/PKCE parameters being sent,
    causing /authorize to return an HTML error page instead of a redirect.
    """
    session = AsyncMock()
    session.cookie_jar = AsyncMock()
    api = RedEnergyAPI(session)

    async def fake_get_session_token(username, password):
        return "session_token", "2099-01-01T00:00:00.000Z"

    async def fake_get_discovery_data():
        return {
            "authorization_endpoint": "https://example.okta.com/authorize",
            "token_endpoint": "https://example.okta.com/token",
        }

    async def fake_get_authorization_code(auth_endpoint, session_token, client_id, code_challenge):
        return "auth_code"

    async def fake_exchange_code_for_tokens(token_endpoint, auth_code, client_id, code_verifier):
        api._access_token = "access_token"
        api._refresh_token = "refresh_token"

    monkeypatch.setattr(api, "_get_session_token", fake_get_session_token)
    monkeypatch.setattr(api, "_get_discovery_data", fake_get_discovery_data)
    monkeypatch.setattr(api, "_get_authorization_code", fake_get_authorization_code)
    monkeypatch.setattr(api, "_exchange_code_for_tokens", fake_exchange_code_for_tokens)

    result = await api.authenticate("user", "pass")

    assert result is True
    assert session.cookie_jar.clear_domain.call_count == len(RedEnergyAPI.OKTA_COOKIE_DOMAINS)
    cleared_domains = {call.args[0] for call in session.cookie_jar.clear_domain.call_args_list}
    assert cleared_domains == set(RedEnergyAPI.OKTA_COOKIE_DOMAINS)
