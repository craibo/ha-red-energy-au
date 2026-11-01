"""Password-flow auth logging must never include secrets.

Users are asked to enable DEBUG logging and paste logs into public GitHub
issues, so the PKCE verifier, Okta sessionToken/stateToken and the
authorization code must not appear in any log record.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.red_energy.api import RedEnergyAPI, RedEnergyAuthError

SESSION_TOKEN = "sess-SECRET-123"
AUTH_CODE = "code-SECRET-456"
STATE_TOKEN = "state-SECRET-789"


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    async def json(self, content_type="application/json"):
        return self._payload

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_password_flow_debug_logs_contain_no_secrets(caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.red_energy")
    session = MagicMock()
    session.get = MagicMock(
        return_value=FakeResponse(
            302,
            headers={"Location": f"au.com.redenergy://callback?code={AUTH_CODE}&state=x"},
        )
    )
    api = RedEnergyAPI(session)
    seen_verifier: list[str] = []

    async def fake_session_token(username, password):
        return SESSION_TOKEN, "2099-01-01T00:00:00.000Z"

    async def fake_discovery():
        return {
            "authorization_endpoint": "https://login.example.com/authorize",
            "token_endpoint": "https://login.example.com/token",
        }

    async def fake_exchange(token_endpoint, auth_code, client_id, code_verifier):
        assert auth_code == AUTH_CODE
        seen_verifier.append(code_verifier)
        api._access_token = "at"

    api._get_session_token = fake_session_token
    api._get_discovery_data = fake_discovery
    api._exchange_code_for_tokens = fake_exchange

    assert await api.authenticate("test@example.com", "testpass")

    log_text = caplog.text
    assert seen_verifier and seen_verifier[0] not in log_text
    assert SESSION_TOKEN not in log_text
    assert AUTH_CODE not in log_text


@pytest.mark.asyncio
async def test_okta_non_success_status_log_omits_state_token(caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.red_energy")
    session = MagicMock()
    session.post = MagicMock(
        return_value=FakeResponse(
            200,
            payload={
                "status": "MFA_REQUIRED",
                "stateToken": STATE_TOKEN,
                "_embedded": {"factors": [{"factorType": "email"}]},
            },
        )
    )
    api = RedEnergyAPI(session)

    with pytest.raises(RedEnergyAuthError, match="MFA_REQUIRED"):
        await api._get_session_token("test@example.com", "testpass")

    assert STATE_TOKEN not in caplog.text
    assert "MFA_REQUIRED" in caplog.text
