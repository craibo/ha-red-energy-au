"""Tests for browser (SSO / email-code) sign-in support in RedEnergyAPI (issue #103)."""
from __future__ import annotations

from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import aiohttp
import pytest

from custom_components.red_energy.api import (
    BrowserLogin,
    RedEnergyAPI,
    RedEnergyAPIError,
    RedEnergyAuthError,
    RedEnergyCallbackError,
)
from custom_components.red_energy.const import CLIENT_ID

DISCOVERY = {
    "authorization_endpoint": "https://login.example.com/oauth2/default/v1/authorize",
    "token_endpoint": "https://login.example.com/oauth2/default/v1/token",
}


class FakeResponse:
    """Minimal aiohttp response stand-in usable as an async context manager."""

    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def json(self, content_type: str | None = "application/json"):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def text(self):
        return str(self._payload)

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=self.status
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def make_api(post_response: FakeResponse | None = None) -> RedEnergyAPI:
    session = MagicMock()
    if post_response is not None:
        session.post = MagicMock(return_value=post_response)
    api = RedEnergyAPI(session)

    async def fake_discovery():
        return DISCOVERY

    api._get_discovery_data = fake_discovery
    return api


@pytest.mark.asyncio
async def test_create_browser_login_builds_pkce_authorize_url():
    api = make_api()
    login = await api.async_create_browser_login()

    assert isinstance(login, BrowserLogin)
    parsed = urlparse(login.auth_url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == DISCOVERY["authorization_endpoint"]
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert q["client_id"] == CLIENT_ID
    assert q["redirect_uri"] == RedEnergyAPI.REDIRECT_URI
    assert q["response_type"] == "code"
    assert "offline_access" in q["scope"].split()
    assert q["code_challenge_method"] == "S256"
    assert q["code_challenge"] == api._generate_code_challenge(login.code_verifier)
    assert q["state"] == login.state
    assert "sessionToken" not in q


@pytest.mark.asyncio
async def test_create_browser_login_survives_discovery_failure():
    """A network blip fetching discovery must not stop the sign-in link from
    being shown - otherwise a reauth flow aborts and the prompt disappears."""
    api = make_api()

    async def failing_discovery():
        raise aiohttp.ClientConnectionError("blip")

    api._get_discovery_data = failing_discovery
    login = await api.async_create_browser_login()

    assert login.auth_url.startswith(RedEnergyAPI.AUTHORIZE_URL + "?")
    q = {k: v[0] for k, v in parse_qs(urlparse(login.auth_url).query).items()}
    assert q["state"] == login.state


def test_fallback_authorize_url_is_under_discovery_issuer():
    assert RedEnergyAPI.AUTHORIZE_URL == (
        RedEnergyAPI.DISCOVERY_URL.removesuffix("/.well-known/openid-configuration")
        + "/v1/authorize"
    )


@pytest.mark.asyncio
async def test_create_browser_login_is_unique_per_call():
    api = make_api()
    a = await api.async_create_browser_login()
    b = await api.async_create_browser_login()
    assert a.state != b.state
    assert a.code_verifier != b.code_verifier


def test_parse_browser_callback_returns_code():
    url = "au.com.redenergy://callback?code=abc123&state=s-1"
    assert RedEnergyAPI.parse_browser_callback(f"  {url}\n", "s-1") == "abc123"


@pytest.mark.parametrize(
    "pasted",
    [
        "",
        "abc123",
        "https://login.redenergy.com.au/oauth2/default/v1/authorize?code=abc123&state=s-1",
        "au.com.redenergy://callback?state=s-1",
        "au.com.redenergy://callback?code=abc123&state=other-attempt",
        "au.com.redenergy://callback?code=abc123",
    ],
)
def test_parse_browser_callback_rejects_invalid_input(pasted):
    with pytest.raises(RedEnergyCallbackError) as exc:
        RedEnergyAPI.parse_browser_callback(pasted, "s-1")
    assert exc.value.reason == "invalid"


def test_parse_browser_callback_okta_error_is_auth_error_not_callback_error():
    url = "au.com.redenergy://callback?error=access_denied&error_description=User+cancelled&state=s-1"
    with pytest.raises(RedEnergyAuthError) as exc:
        RedEnergyAPI.parse_browser_callback(url, "s-1")
    assert not isinstance(exc.value, RedEnergyCallbackError)
    assert "access_denied" in str(exc.value)


@pytest.mark.asyncio
async def test_complete_browser_login_stores_tokens():
    api = make_api(FakeResponse(200, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}))
    login = BrowserLogin(auth_url="x", code_verifier="v" * 48, state="s-1")

    await api.async_complete_browser_login("au.com.redenergy://callback?code=c-1&state=s-1", login)

    assert api._access_token == "at-1"
    assert api.refresh_token == "rt-1"
    sent = api._session.post.call_args.kwargs["data"]
    assert sent["code"] == "c-1"
    assert sent["code_verifier"] == "v" * 48


@pytest.mark.asyncio
async def test_complete_browser_login_expired_code():
    api = make_api(FakeResponse(400, {"error": "invalid_grant", "error_description": "The authorization code is invalid or has expired."}))
    login = BrowserLogin(auth_url="x", code_verifier="v" * 48, state="s-1")

    with pytest.raises(RedEnergyCallbackError) as exc:
        await api.async_complete_browser_login("au.com.redenergy://callback?code=c-1&state=s-1", login)
    assert exc.value.reason == "expired"


@pytest.mark.asyncio
async def test_complete_browser_login_without_refresh_token_fails():
    api = make_api(FakeResponse(200, {"access_token": "at-1", "expires_in": 3600}))
    login = BrowserLogin(auth_url="x", code_verifier="v" * 48, state="s-1")

    with pytest.raises(RedEnergyAuthError, match="refresh token"):
        await api.async_complete_browser_login("au.com.redenergy://callback?code=c-1&state=s-1", login)


@pytest.mark.asyncio
async def test_authenticate_with_refresh_token_success():
    api = make_api(FakeResponse(200, {"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600}))

    assert await api.authenticate_with_refresh_token("rt-1") is True
    assert api._access_token == "at-2"
    assert api.refresh_token == "rt-2"
    assert api._session.post.call_args.kwargs["data"]["refresh_token"] == "rt-1"


@pytest.mark.asyncio
async def test_authenticate_with_missing_refresh_token_is_auth_error():
    api = make_api()
    with pytest.raises(RedEnergyAuthError):
        await api.authenticate_with_refresh_token(None)


@pytest.mark.asyncio
async def test_refresh_rejected_token_is_auth_error():
    api = make_api(FakeResponse(400, {"error": "invalid_grant"}))
    with pytest.raises(RedEnergyAuthError):
        await api.authenticate_with_refresh_token("rt-dead")


@pytest.mark.asyncio
async def test_refresh_server_error_is_not_auth_error():
    api = make_api(FakeResponse(503, aiohttp.ContentTypeError(MagicMock(), ())))
    with pytest.raises(RedEnergyAPIError) as exc:
        await api.authenticate_with_refresh_token("rt-1")
    assert not isinstance(exc.value, RedEnergyAuthError)


@pytest.mark.asyncio
async def test_listener_called_only_when_refresh_token_changes():
    api = make_api(FakeResponse(200, {"access_token": "at-2", "refresh_token": "rt-1", "expires_in": 3600}))
    seen: list[str] = []
    api.set_refresh_token_listener(seen.append)

    await api.authenticate_with_refresh_token("rt-1")  # Okta returned the same token
    assert seen == []

    api._session.post = MagicMock(return_value=FakeResponse(200, {"access_token": "at-3", "refresh_token": "rt-2", "expires_in": 3600}))
    await api._refresh_access_token()
    assert seen == ["rt-2"]
