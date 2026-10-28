# Browser Sign-In (Google / Apple / Microsoft / Email Code) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Red Energy customers who sign in with Google/Apple/Microsoft SSO or an emailed code (no password) set up the integration, by completing Red Energy's hosted Okta login in their own browser and pasting the resulting callback URL into Home Assistant (issue #103).

**Architecture:** A new config-flow path generates a PKCE authorization URL for the app's existing Okta client. The user signs in in their browser, which is redirected to `au.com.redenergy://callback?code=…&state=…` (not openable on desktop). The user pastes that URL back. The integration exchanges the code for tokens and stores **only the refresh token** in the config entry. From then on the coordinator authenticates with the refresh token, persists rotated refresh tokens, and raises `ConfigEntryAuthFailed` when Okta rejects it. That triggers HA's reauth flow, which re-runs the browser sign-in. Existing password entries are untouched.

**Tech Stack:** Python 3.14, Home Assistant 2026.3+ custom integration, aiohttp, voluptuous, pytest + pytest-asyncio.

**Spec:** No separate spec doc. The design is the "Design" section below, derived from the investigation of issue #103 (https://github.com/craibo/ha-red-energy-au/issues/103).

## Design (investigation findings this plan relies on)

- Red Energy's Okta org (`redenergy.okta.com` / `login.redenergy.com.au`) runs Okta Identity Engine (`"pipeline":"idx"`). Its hosted sign-in page offers Apple, Google and Microsoft IdPs and passwordless email (`"passwordlessAuth":true`).
- The app client `CLIENT_ID = "0oa1apu62kkqeet4C3l7"` only allows `authorization_code` and `refresh_token` grants. `/oauth2/default/v1/interact` returns `unauthorized_client`, so an in-HA email-code flow via the IDX API is **not possible**. Browser sign-in is the only route.
- `GET {authorization_endpoint}?client_id=…&redirect_uri=au.com.redenergy://callback&code_challenge=…` **without** a `sessionToken` returns the hosted login page (HTTP 200). That confirms the browser route works with this client and redirect URI.
- Today, refresh tokens live only in memory and every restart re-logs in with the stored password (`coordinator.py:202`, `:446`). There is no reauth flow. SSO users have no password, so the refresh token must be persisted.

## Global Constraints

- Work on branch `feat/browser-sign-in`. Never commit to `main`.
- The first commit bumps `custom_components/red_energy/manifest.json` `version` from `1.22.3` to `1.23.0` (minor: new feature).
- Commit messages use semantic prefixes (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). They are short, with no AI/Claude attribution and no mention of tests.
- Use only fake personal data in code, tests and docs: emails like `test@example.com`, account IDs like `1000001`, tokens like `rt-1`.
- Never log access tokens, refresh tokens, authorization codes or the full callback URL at INFO or above. Logging a callback URL even at DEBUG is forbidden because it contains a live code.
- Existing password config entries must keep working with no migration. A missing `auth_method` key means password. Do **not** bump `CURRENT_CONFIG_VERSION`.
- Run tests with `.venv/bin/pytest`. The baseline is 449 passing.
- Lint gate: `.venv/bin/flake8 custom_components --count --select=E9,F63,F7,F82 --show-source --statistics` must report 0.

## Review Focus

1. **The user pastes the callback URL too slowly.** The authorization code has expired, so Okta returns `400 invalid_grant` from the token endpoint. The user expects a clear "sign-in code expired, open the link again" error on the same form, not "cannot connect". This is pinned in Task 2 (`test_complete_browser_login_expired_code`) and Task 4 (`test_browser_step_expired_code_shows_error`).
2. **The user pastes the wrong thing**: the Okta page URL, a bare code, an empty string, or a URL from an older attempt whose `state` doesn't match. The user expects an "invalid callback URL" form error, and the form stays usable for a retry with the same sign-in link. This is pinned in Task 2 (`test_parse_browser_callback_rejects_*`) and Task 4 (`test_browser_step_invalid_callback_keeps_same_link`).
3. **Okta has a 5xx/HTML outage during a token refresh.** The user expects a transient `UpdateFailed` and the next poll to retry. It must **not** trigger a reauth prompt that forces them through browser sign-in again. This is pinned in Task 2 (`test_refresh_server_error_is_not_auth_error`) and Task 3 (`test_browser_transient_refresh_failure_is_update_failed`).
4. **Okta rotates the refresh token on every refresh.** If the new token isn't persisted before HA restarts, the old one is dead and the user is forced to reauth after every restart. This is pinned in Task 3 (`test_rotated_refresh_token_is_persisted_to_entry`).
5. **During reauth the user signs in as a different Red Energy customer.** The user expects the flow to abort with "wrong account" and leave the existing entry's token unchanged. This is pinned in Task 4 (`test_reauth_with_different_account_aborts`).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `custom_components/red_energy/api.py` | Modify | `BrowserLogin` dataclass, `RedEnergyCallbackError`, authorize-URL creation, callback parsing, code exchange, refresh-token login, refresh-token change listener, auth-vs-transient split in `_refresh_access_token` |
| `custom_components/red_energy/const.py` | Modify | `CONF_AUTH_METHOD`, `AUTH_METHOD_*`, `CONF_REFRESH_TOKEN`, `CONF_CALLBACK_URL`, `STEP_PASSWORD`, `STEP_BROWSER`, new error/abort keys |
| `custom_components/red_energy/coordinator.py` | Modify | `auth_method` / `refresh_token` kwargs, `_async_ensure_authenticated()`, refresh-token persistence, `ConfigEntryAuthFailed` for browser entries |
| `custom_components/red_energy/__init__.py` | Modify | Pass auth method and refresh token from entry data. `CONF_PASSWORD` becomes optional |
| `custom_components/red_energy/config_flow.py` | Modify | Menu on `user` step, `password` step (old form), `browser` step, `reauth`, shared account-info/entry helpers |
| `custom_components/red_energy/translations/en.json` | Modify | Menu, browser step instructions, new errors/aborts |
| `tests/test_api_browser_login.py` | Create | API-level tests |
| `tests/test_coordinator_browser_auth.py` | Create | Coordinator auth tests |
| `tests/test_config_flow_browser.py` | Create | Browser/reauth config-flow tests |
| `tests/test_config_flow.py` | Modify | Password tests move from `async_step_user` to `async_step_password` |
| `README.md`, `CLAUDE.md` | Modify | User docs for browser sign-in; architecture note |

---

### Task 1: Branch, version bump, and live feasibility check

This task proves the two assumptions the rest of the plan depends on:
- The callback URL can be captured from a desktop browser.
- Okta issues a refresh token for the `offline_access` scope.

It also records how long the code lives and whether refresh tokens rotate. It uses a throwaway script that is **not committed**.

**Files:**
- Modify: `custom_components/red_energy/manifest.json` (`"version": "1.22.3"` → `"1.23.0"`)
- Create (scratch, not committed): `$SCRATCH/browser_login_spike.py`, where `$SCRATCH` is the session scratchpad directory

**Interfaces:**
- Consumes: nothing
- Produces: recorded facts used in Task 4/5 copy, namely the capture method that works and whether refresh tokens rotate

- [ ] **Step 1: Create the branch and bump the version**

```bash
cd /Users/craibo/github/ha-red-energy-au
git checkout main && git pull origin main
git checkout -b feat/browser-sign-in
```

Edit `custom_components/red_energy/manifest.json`: change `"version": "1.22.3"` to `"version": "1.23.0"`.

```bash
git add custom_components/red_energy/manifest.json
git commit -m "chore: bump version to 1.23.0"
```

- [ ] **Step 2: Write the spike script**

```python
"""Throwaway: verify browser sign-in for Red Energy's Okta client. NOT committed."""
import asyncio, base64, hashlib, secrets, string, uuid
from urllib.parse import urlencode, urlparse, parse_qs
import aiohttp

CLIENT_ID = "0oa1apu62kkqeet4C3l7"
REDIRECT_URI = "au.com.redenergy://callback"
DISCOVERY = "https://login.redenergy.com.au/oauth2/default/.well-known/openid-configuration"

async def main():
    async with aiohttp.ClientSession() as s:
        d = await (await s.get(DISCOVERY)).json()
        alphabet = string.ascii_letters + string.digits + "-._~"
        verifier = "".join(secrets.choice(alphabet) for _ in range(48))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state = str(uuid.uuid4())
        url = d["authorization_endpoint"] + "?" + urlencode({
            "client_id": CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT_URI,
            "scope": "openid profile offline_access", "code_challenge": challenge,
            "code_challenge_method": "S256", "state": state, "nonce": str(uuid.uuid4()),
        })
        print("Open this in desktop Chrome with DevTools (Console tab) open:\n", url)
        cb = input("Paste the au.com.redenergy://callback?... URL: ").strip()
        q = parse_qs(urlparse(cb).query)
        assert q["state"][0] == state, "state mismatch"
        r = await s.post(d["token_endpoint"], data={
            "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": q["code"][0],
            "redirect_uri": REDIRECT_URI, "code_verifier": verifier})
        t = await r.json()
        print("token status", r.status, "keys", sorted(t), "expires_in", t.get("expires_in"))
        rt1 = t["refresh_token"]
        r2 = await s.post(d["token_endpoint"], data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": rt1})
        t2 = await r2.json()
        print("refresh status", r2.status, "rotated:", t2.get("refresh_token") not in (None, rt1))
        if t2.get("refresh_token") not in (None, rt1):
            r3 = await s.post(d["token_endpoint"], data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": rt1})
            print("old token reuse status", r3.status, (await r3.text())[:200])

asyncio.run(main())
```

- [ ] **Step 3: Run it with a real Red Energy login (the maintainer's account; the hosted page accepts password or email-code login)**

Run: `.venv/bin/python $SCRATCH/browser_login_spike.py`

Then:
1. Open the printed URL in desktop Chrome with DevTools → Console open.
2. Sign in.
3. Chrome logs `Failed to launch 'au.com.redenergy://callback?code=…&state=…' because the scheme does not have a registered handler.`
4. Copy that URL and paste it at the prompt.
5. If the Console shows nothing, use DevTools → Network with "Preserve log" ticked. Find the last `302` response and copy its `Location` header.

Expected output:
- `token status 200`, with keys including `refresh_token`
- `refresh status 200`
- a `rotated:` value (True or False)

Also time one deliberately slow paste (wait about 2 minutes) to see whether the code has expired (`400 invalid_grant`).

- [ ] **Step 4: Record findings and decide**

Append the findings to this plan under a new heading `## Spike Results`:
- the capture method that worked (Console message vs Network tab)
- whether a refresh token was issued
- whether it rotates and whether the old one still works
- the rough code lifetime

**Gate:** if no `refresh_token` is issued, or the callback URL cannot be captured in Chrome or Edge, STOP and report back. The rest of the plan depends on both.

Delete nothing. The scratch script is outside the repo.

---

### Task 2: API support for browser sign-in and refresh-token login

**Files:**
- Modify: `custom_components/red_energy/api.py` (imports at the top, exception classes at `:22-28`, `__init__` at `:48-55`, `_exchange_code_for_tokens` at `:284-287`, `_refresh_access_token` at `:506-540`; new methods placed after `test_credentials` at `:289`)
- Test: `tests/test_api_browser_login.py` (create)

**Interfaces:**
- Consumes: existing `RedEnergyAPI._get_discovery_data()`, `_generate_code_verifier()`, `_generate_code_challenge()`, `_exchange_code_for_tokens(token_endpoint, auth_code, client_id, code_verifier)`, `_auth_lock`
- Produces (used by Tasks 3 and 4):
  - `@dataclass(frozen=True) class BrowserLogin: auth_url: str; code_verifier: str; state: str`
  - `class RedEnergyCallbackError(RedEnergyAuthError)` with attribute `reason: str`, either `"invalid"` or `"expired"`
  - `async RedEnergyAPI.async_create_browser_login() -> BrowserLogin`
  - `@classmethod RedEnergyAPI.parse_browser_callback(callback_url: str, expected_state: str) -> str`, which returns the code
  - `async RedEnergyAPI.async_complete_browser_login(callback_url: str, login: BrowserLogin) -> None`
  - `async RedEnergyAPI.authenticate_with_refresh_token(refresh_token: str | None) -> bool`
  - `RedEnergyAPI.refresh_token` property (`str | None`)
  - `RedEnergyAPI.set_refresh_token_listener(listener: Callable[[str], None] | None) -> None`, called whenever a *new, different* refresh token is received
  - `_refresh_access_token` raises `RedEnergyAuthError` only for HTTP 400/401, and `RedEnergyAPIError` for any other non-200

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_browser_login.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_browser_login.py -v`
Expected: collection error, `ImportError: cannot import name 'BrowserLogin'`

- [ ] **Step 3: Implement in `api.py`**

Add to the imports at the top of `api.py`. Keep the existing imports; add only what's missing:

```python
from collections.abc import Callable
from dataclasses import dataclass
```

After `class RedEnergyAuthError` (around line 28), add:

```python
class RedEnergyCallbackError(RedEnergyAuthError):
    """The browser sign-in callback URL pasted by the user was unusable.

    reason is "invalid" (not a matching au.com.redenergy://callback URL) or
    "expired" (Okta rejected the code - usually pasted too late).
    """

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class BrowserLogin:
    """One pending browser sign-in attempt (issue #103)."""

    auth_url: str
    code_verifier: str
    state: str
```

In `RedEnergyAPI.__init__`, add after `self._auth_lock = asyncio.Lock()`:

```python
        self._refresh_token_listener: Callable[[str], None] | None = None
```

Add these methods directly after `test_credentials`:

```python
    @property
    def refresh_token(self) -> str | None:
        """Current OAuth2 refresh token, if any."""
        return self._refresh_token

    def set_refresh_token_listener(self, listener: Callable[[str], None] | None) -> None:
        """Register a callback for when Okta issues a new refresh token, so
        browser sign-in entries can persist rotated tokens."""
        self._refresh_token_listener = listener

    def _set_refresh_token(self, refresh_token: str | None) -> None:
        changed = refresh_token is not None and refresh_token != self._refresh_token
        self._refresh_token = refresh_token
        if changed and self._refresh_token_listener is not None:
            self._refresh_token_listener(refresh_token)

    async def async_create_browser_login(self) -> BrowserLogin:
        """Build a PKCE authorization URL for signing in through Red Energy's
        hosted Okta page (Google/Apple/Microsoft SSO or email code).

        Unlike authenticate(), no sessionToken is sent, so Okta shows its
        login page instead of redirecting immediately.
        """
        discovery_data = await self._get_discovery_data()
        code_verifier = self._generate_code_verifier()
        state = str(uuid.uuid4())
        params = {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': self.REDIRECT_URI,
            'scope': 'openid profile offline_access',
            'code_challenge': self._generate_code_challenge(code_verifier),
            'code_challenge_method': 'S256',
            'state': state,
            'nonce': str(uuid.uuid4()),
        }
        auth_url = f"{discovery_data['authorization_endpoint']}?{urlencode(params)}"
        return BrowserLogin(auth_url=auth_url, code_verifier=code_verifier, state=state)

    @classmethod
    def parse_browser_callback(cls, callback_url: str, expected_state: str) -> str:
        """Extract the authorization code from a pasted callback URL.

        Never log callback_url - it contains a live authorization code.
        """
        text = (callback_url or "").strip()
        if not text.startswith(cls.REDIRECT_URI):
            raise RedEnergyCallbackError(
                f"Callback URL must start with {cls.REDIRECT_URI}", "invalid"
            )
        params = parse_qs(urlparse(text).query)
        if "error" in params:
            error = params["error"][0]
            description = params.get("error_description", [""])[0]
            raise RedEnergyAuthError(f"Sign-in failed: {error} - {description}")
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        if not code:
            raise RedEnergyCallbackError("Callback URL has no authorization code", "invalid")
        if state != expected_state:
            raise RedEnergyCallbackError(
                "Callback URL is from a different sign-in attempt", "invalid"
            )
        return code

    async def async_complete_browser_login(self, callback_url: str, login: BrowserLogin) -> None:
        """Exchange a pasted callback URL's code for access/refresh tokens."""
        code = self.parse_browser_callback(callback_url, login.state)
        async with self._auth_lock:
            discovery_data = await self._get_discovery_data()
            try:
                await self._exchange_code_for_tokens(
                    discovery_data["token_endpoint"], code, CLIENT_ID, login.code_verifier
                )
            except aiohttp.ClientResponseError as err:
                if err.status in (400, 401):
                    raise RedEnergyCallbackError(
                        "Sign-in code was rejected or has expired", "expired"
                    ) from err
                raise
        if not self._refresh_token:
            raise RedEnergyAuthError(
                "Red Energy did not issue a refresh token for this sign-in"
            )

    async def authenticate_with_refresh_token(self, refresh_token: str | None) -> bool:
        """Obtain a fresh access token from a stored refresh token (browser
        sign-in entries have no password to fall back on)."""
        async with self._auth_lock:
            self._refresh_token = refresh_token
            await self._refresh_access_token()
        return True
```

Confirm that `aiohttp` is imported in `api.py`. If `grep -n "^import aiohttp" custom_components/red_energy/api.py` prints nothing, add `import aiohttp` with the other imports.

In `_exchange_code_for_tokens`, replace:

```python
                self._refresh_token = tokens.get('refresh_token')
```

with:

```python
                self._set_refresh_token(tokens.get('refresh_token'))
```

In `_refresh_access_token`, replace the block from `if response.status != 200:` through `self._refresh_token = tokens['refresh_token']` with:

```python
                if response.status != 200:
                    try:
                        error_data = await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, ValueError):
                        error_data = {"raw": (await response.text())[:500]}
                    # 400/401 mean Okta rejected the refresh token itself
                    # (expired/revoked) - only re-sign-in fixes that. Anything
                    # else (5xx, HTML outage page) is transient and must not
                    # force browser sign-in users through reauth.
                    if response.status in (400, 401):
                        raise RedEnergyAuthError(f"Token refresh rejected: {error_data}")
                    raise RedEnergyAPIError(
                        f"Token refresh failed with HTTP {response.status}: {error_data}"
                    )

                tokens = await response.json()

                self._access_token = tokens['access_token']
                if 'refresh_token' in tokens:
                    self._set_refresh_token(tokens['refresh_token'])
```

Keep the existing `expires_in` / `_token_expires` / debug-log lines that follow.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_browser_login.py -v`
Expected: all PASS

Run: `.venv/bin/pytest tests -q`
Expected: 449 + the new tests pass, 0 failures

- [ ] **Step 5: Commit**

```bash
git add custom_components/red_energy/api.py tests/test_api_browser_login.py
git commit -m "feat: add browser sign-in and refresh-token login to API client"
```

---

### Task 3: Coordinator and setup use the stored refresh token

**Files:**
- Modify: `custom_components/red_energy/const.py` (after `CONF_CLIENT_ID` at `:10`)
- Modify: `custom_components/red_energy/coordinator.py` (imports, `__init__` at `:53-88`, `:199-202`, `:395-397`, `:444-446`)
- Modify: `custom_components/red_energy/__init__.py` (`:13-18`, `:52-77`)
- Test: `tests/test_coordinator_browser_auth.py` (create)

**Interfaces:**
- Consumes: from Task 2, `RedEnergyAPI.authenticate_with_refresh_token`, `.refresh_token`, `.set_refresh_token_listener`, and `RedEnergyAuthError` semantics
- Produces:
  - const `CONF_AUTH_METHOD = "auth_method"`, `AUTH_METHOD_PASSWORD = "password"`, `AUTH_METHOD_BROWSER = "browser"`, `CONF_REFRESH_TOKEN = "refresh_token"`
  - `RedEnergyDataCoordinator(hass, username, password, selected_accounts, services, config_entry=None, auth_method=AUTH_METHOD_PASSWORD, refresh_token=None)`
  - `RedEnergyDataCoordinator._async_ensure_authenticated() -> None`
  - Browser entries raise `homeassistant.exceptions.ConfigEntryAuthFailed` when the refresh token is rejected

- [ ] **Step 1: Add the constants**

In `const.py`, after `CONF_CLIENT_ID: Final = "client_id"`:

```python

# Browser sign-in (Google/Apple/Microsoft SSO or emailed code, issue #103).
# Entries without CONF_AUTH_METHOD predate this and are password entries.
CONF_AUTH_METHOD: Final = "auth_method"
AUTH_METHOD_PASSWORD: Final = "password"
AUTH_METHOD_BROWSER: Final = "browser"
CONF_REFRESH_TOKEN: Final = "refresh_token"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_coordinator_browser_auth.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_coordinator_browser_auth.py -v`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'auth_method'`

- [ ] **Step 4: Implement in `coordinator.py`**

Imports: add `from homeassistant.core import callback` (or extend the existing `homeassistant.core` import) and `from homeassistant.exceptions import ConfigEntryAuthFailed`. Add `AUTH_METHOD_BROWSER`, `AUTH_METHOD_PASSWORD` and `CONF_REFRESH_TOKEN` to the existing `from .const import (...)` block.

Change `__init__`'s signature and add the auth fields:

```python
    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        selected_accounts: list[str],
        services: list[str],
        config_entry: ConfigEntry | None = None,
        auth_method: str = AUTH_METHOD_PASSWORD,
        refresh_token: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.username = username
        self.password = password
        self.auth_method = auth_method
        self._stored_refresh_token = refresh_token
        self.selected_accounts = selected_accounts
```

Directly after `self.api = RedEnergyAPI(session)`:

```python
        # Browser sign-in entries have no password: the refresh token is
        # their only credential, and Okta may rotate it on every refresh, so
        # every new one must be written back to the config entry.
        if auth_method == AUTH_METHOD_BROWSER:
            self.api.set_refresh_token_listener(self._async_persist_refresh_token)
```

Add the methods after `_async_update_data` (before `_async_update_data_once`):

```python
    async def _async_ensure_authenticated(self) -> None:
        """Log in if there's no access token yet (startup, or after reset)."""
        if self.api._access_token:
            return
        if self.auth_method == AUTH_METHOD_BROWSER:
            _LOGGER.info("Authenticating with Red Energy API using saved browser sign-in")
            await self.api.authenticate_with_refresh_token(
                self.api.refresh_token or self._stored_refresh_token
            )
        else:
            _LOGGER.info("Authenticating with Red Energy API")
            await self.api.authenticate(self.username, self.password)

    @callback
    def _async_persist_refresh_token(self, refresh_token: str) -> None:
        """Save a rotated refresh token so it survives a Home Assistant restart."""
        self._stored_refresh_token = refresh_token
        entry = self.config_entry
        if entry is None or entry.data.get(CONF_REFRESH_TOKEN) == refresh_token:
            return
        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_REFRESH_TOKEN: refresh_token}
        )
```

Note: there is no `add_update_listener` in this integration, so `async_update_entry` does not reload the entry. Do not add one.

In `_async_update_data_once`, replace:

```python
            # Ensure we're authenticated
            if not self.api._access_token:
                _LOGGER.info("Authenticating with Red Energy API")
                await self.api.authenticate(self.username, self.password)
```

with:

```python
            await self._async_ensure_authenticated()
```

and replace the auth handler:

```python
        except RedEnergyAuthError as err:
            _LOGGER.error("Authentication failed during update: %s", err)
            raise UpdateFailed(f"Authentication failed: {err}") from err
```

with:

```python
        except RedEnergyAuthError as err:
            _LOGGER.error("Authentication failed during update: %s", err)
            if self.auth_method == AUTH_METHOD_BROWSER:
                # The saved sign-in is dead and there's no password to retry
                # with - HA starts the reauth flow (browser sign-in again).
                raise ConfigEntryAuthFailed(
                    "Red Energy sign-in has expired - please sign in again"
                ) from err
            raise UpdateFailed(f"Authentication failed: {err}") from err
```

In `_bulk_update_data`, replace:

```python
            if not self.api._access_token:
                await self.api.authenticate(self.username, self.password)
```

with:

```python
            await self._async_ensure_authenticated()
```

- [ ] **Step 5: Implement in `__init__.py`**

Extend the `.const` import:

```python
from .const import (
    AUTH_METHOD_PASSWORD,
    CLIENT_ID,
    CONF_AUTH_METHOD,
    CONF_REFRESH_TOKEN,
    DATA_SELECTED_ACCOUNTS,
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
)
```

Replace `password = entry.data[CONF_PASSWORD]` with:

```python
    # Browser sign-in entries (issue #103) store a refresh token, not a password.
    password = entry.data.get(CONF_PASSWORD, "")
    auth_method = entry.data.get(CONF_AUTH_METHOD, AUTH_METHOD_PASSWORD)
```

Replace the coordinator construction with:

```python
    coordinator = RedEnergyDataCoordinator(
        hass,
        username,
        password,
        selected_accounts,
        services,
        config_entry=entry,
        auth_method=auth_method,
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
    )
```

Leave the `except UpdateFailed` around `async_config_entry_first_refresh()` as it is. `ConfigEntryAuthFailed` is not an `UpdateFailed`, so it propagates and HA starts reauth.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_coordinator_browser_auth.py -v`
Expected: all PASS

Run: `.venv/bin/pytest tests -q`
Expected: 0 failures. Existing coordinator tests construct without `auth_method`, so they get the password default.

- [ ] **Step 7: Commit**

```bash
git add custom_components/red_energy/const.py custom_components/red_energy/coordinator.py custom_components/red_energy/__init__.py tests/test_coordinator_browser_auth.py
git commit -m "feat: authenticate browser sign-in entries with persisted refresh token"
```

---

### Task 4: Config flow (sign-in method menu, browser step, reauth) and translations

**Files:**
- Modify: `custom_components/red_energy/const.py` (config-flow section at `:150-158`)
- Modify: `custom_components/red_energy/config_flow.py` (whole `validate_input` at `:54-135`, `ConfigFlow` at `:138-219`)
- Modify: `custom_components/red_energy/translations/en.json` (`config` section)
- Modify: `tests/test_config_flow.py` (password-form tests)
- Test: `tests/test_config_flow_browser.py` (create)

**Interfaces:**
- Consumes:
  - from Task 2: `RedEnergyAPI.async_create_browser_login() -> BrowserLogin`, `.async_complete_browser_login(callback_url, login)`, `.refresh_token`, `RedEnergyCallbackError.reason`
  - from Task 3: `CONF_AUTH_METHOD`, `AUTH_METHOD_PASSWORD`, `AUTH_METHOD_BROWSER`, `CONF_REFRESH_TOKEN`
- Produces:
  - consts `CONF_CALLBACK_URL = "callback_url"`, `STEP_PASSWORD = "password"`, `STEP_BROWSER = "browser"`, `ERROR_INVALID_CALLBACK = "invalid_callback"`, `ERROR_CALLBACK_EXPIRED = "callback_expired"`, `ABORT_WRONG_ACCOUNT = "wrong_account"`
  - flow steps `user` (menu), `password`, `browser`, `reauth`
  - module helper `async _async_fetch_account_info(api: RedEnergyAPI) -> dict[str, Any]` and `_browser_unique_id(customer_data: dict[str, Any]) -> str`

- [ ] **Step 1: Add the constants**

In `const.py`, replace the `# Configuration flow` and `# Error messages` blocks with:

```python
# Configuration flow
STEP_USER: Final = "user"
STEP_PASSWORD: Final = "password"
STEP_BROWSER: Final = "browser"
STEP_ACCOUNT_SELECT: Final = "account_select"
CONF_CALLBACK_URL: Final = "callback_url"

# Error messages
ERROR_AUTH_FAILED: Final = "auth_failed"
ERROR_CANNOT_CONNECT: Final = "cannot_connect"
ERROR_UNKNOWN: Final = "unknown"
ERROR_NO_ACCOUNTS: Final = "no_accounts"
ERROR_INVALID_CALLBACK: Final = "invalid_callback"
ERROR_CALLBACK_EXPIRED: Final = "callback_expired"
ABORT_WRONG_ACCOUNT: Final = "wrong_account"
```

- [ ] **Step 2: Move the existing password tests to the new step**

In `tests/test_config_flow.py`:
- Every call `flow.async_step_user(MOCK_USER_INPUT)` and `flow.async_step_user(...)` that submits credentials becomes `flow.async_step_password(...)`.
- In `test_form`, replace the body's assertions with a menu check:

```python
    result = await flow.async_step_user()
    assert result["type"] == "menu"
    assert result["menu_options"] == ["password", "browser"]

    result = await flow.async_step_password()
    assert result["type"] == "form"
    assert result["step_id"] == "password"
    assert result["errors"] == {}
```

Then run `grep -n "async_step_user" tests/test_config_flow.py`. The only remaining hit must be in `test_form`.

Add this regression test to the same file. Today `NoAccounts` raised inside `validate_input` is swallowed by its `except Exception` and shown as "Unexpected error":

```python
@pytest.mark.asyncio
async def test_validate_input_no_properties_raises_no_accounts():
    """An empty property list must surface as no_accounts, not unknown."""
    from custom_components.red_energy.config_flow import validate_input

    api = MagicMock()
    api.test_credentials = AsyncMock(return_value=True)
    api.get_customer_data = AsyncMock(return_value=MOCK_CUSTOMER_DATA)
    api.get_properties = AsyncMock(return_value=[])
    with patch("custom_components.red_energy.config_flow.RedEnergyAPI", return_value=api), patch(
        "custom_components.red_energy.config_flow.async_get_clientsession"
    ):
        with pytest.raises(NoAccounts):
            await validate_input(AsyncMock(), MOCK_USER_INPUT)
```

- [ ] **Step 3: Write the failing browser-flow tests**

Create `tests/test_config_flow_browser.py`:

```python
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
async def test_browser_step_okta_error_is_auth_failed(api):
    api.async_complete_browser_login.side_effect = RedEnergyAuthError("access_denied")
    flow = make_flow()
    await flow.async_step_browser()
    result = await flow.async_step_browser(CALLBACK)
    assert result["errors"] == {"base": ERROR_AUTH_FAILED}


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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config_flow_browser.py tests/test_config_flow.py -v`
Expected: FAIL with `ImportError` (new consts) or `AttributeError: ... async_step_browser` / `async_step_password`

- [ ] **Step 5: Implement in `config_flow.py`**

Imports:
- Add `import aiohttp` and `from collections.abc import Mapping`.
- Change the `.api` import to:

```python
from .api import (
    BrowserLogin,
    RedEnergyAPI,
    RedEnergyAPIError,
    RedEnergyAuthError,
    RedEnergyCallbackError,
)
```

- Add `validate_customer_data` to the `.data_validation` import, and delete the local `from .data_validation import validate_customer_data, validate_properties_data` inside `validate_input`.
- Add `ABORT_WRONG_ACCOUNT`, `AUTH_METHOD_BROWSER`, `AUTH_METHOD_PASSWORD`, `CONF_AUTH_METHOD`, `CONF_CALLBACK_URL`, `CONF_REFRESH_TOKEN`, `ERROR_CALLBACK_EXPIRED`, `ERROR_INVALID_CALLBACK`, `STEP_BROWSER` and `STEP_PASSWORD` to the `.const` import.

After `STEP_USER_DATA_SCHEMA`, add:

```python
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
```

In `validate_input`, replace everything from `# Get customer data and properties` down to the closing `}` of the returned dict with:

```python
        return await _async_fetch_account_info(api)
```

Then add `except NoAccounts: raise` as the **first** handler after the `try:` (before `except RedEnergyAuthError`):

```python
    except NoAccounts:
        raise
```

Replace the whole `ConfigFlow` class body (from `def __init__` through the end of `async_step_user`) with the following. Keep the `VERSION` lines and `async_get_options_flow` unchanged.

```python
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
```

- [ ] **Step 6: Update `translations/en.json`**

Replace the `"config"` object with the following. Before writing it, adjust the browser description's capture instructions to match the Task 1 spike results.

```json
  "config": {
    "step": {
      "user": {
        "title": "Red Energy Setup",
        "description": "How do you sign in to Red Energy?",
        "menu_options": {
          "password": "Email and password",
          "browser": "Google, Apple, Microsoft or emailed code"
        }
      },
      "password": {
        "title": "Red Energy Setup",
        "description": "Enter your Red Energy credentials.",
        "data": {
          "username": "Username (Email)",
          "password": "Password"
        }
      },
      "browser": {
        "title": "Sign in with your browser",
        "description": "Use a desktop browser (Chrome or Edge). On a phone with the Red Energy app installed, the app intercepts the sign-in.\n\n1. Press F12 to open the developer tools and select the **Console** tab.\n2. [Open the Red Energy sign-in page]({auth_url}) in the same tab and sign in with Google, Apple, Microsoft or an emailed code.\n3. The page won't change after sign-in. The Console shows an error starting `Failed to launch 'au.com.redenergy://callback?code=...`. Copy the address between the quotes, starting `au.com.redenergy://`.\n4. Paste it below **straight away** - it expires quickly.",
        "data": {
          "callback_url": "Callback URL (au.com.redenergy://callback?...)"
        }
      }
    },
    "error": {
      "auth_failed": "Invalid username or password",
      "cannot_connect": "Failed to connect to Red Energy. Check your internet connection.",
      "unknown": "Unexpected error occurred",
      "no_accounts": "No Red Energy accounts found for this user",
      "invalid_callback": "That isn't the callback URL from this sign-in. Copy the full address starting au.com.redenergy://callback?code= after signing in with the link above.",
      "callback_expired": "That sign-in code has expired. Open the sign-in link again and paste the new callback URL straight away."
    },
    "abort": {
      "already_configured": "Red Energy account is already configured",
      "cannot_connect": "Failed to connect to Red Energy. Check your internet connection.",
      "reauth_successful": "Signed in to Red Energy again successfully",
      "wrong_account": "You signed in as a different Red Energy customer than this integration was set up with."
    }
  },
```

Validate the JSON: `.venv/bin/python -c "import json;json.load(open('custom_components/red_energy/translations/en.json'))"` (no output means it's valid).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config_flow_browser.py tests/test_config_flow.py tests/test_config_flow_basic.py -v`
Expected: all PASS

Run: `.venv/bin/pytest tests -q`
Expected: 0 failures

Run: `.venv/bin/flake8 custom_components --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

- [ ] **Step 8: Commit**

```bash
git add custom_components/red_energy/const.py custom_components/red_energy/config_flow.py custom_components/red_energy/translations/en.json tests/test_config_flow.py tests/test_config_flow_browser.py
git commit -m "feat: add browser sign-in and reauth to config flow for SSO users"
```

---

### Task 5: Documentation and end-to-end verification

**Files:**
- Modify: `README.md` (`### Configuration` section at `:58-70`)
- Modify: `CLAUDE.md` (`### Authentication` section)

**Interfaces:**
- Consumes: the final flow behaviour from Tasks 2–4 and the Spike Results from Task 1
- Produces: user and maintainer docs

- [ ] **Step 1: Update `README.md`**

Replace step 3 of `### Configuration` with:

```markdown
3. Choose how you sign in to Red Energy:
   - **Email and password** — enter your Red Energy account email and password
   - **Google, Apple, Microsoft or emailed code** — for accounts without a password (see [Browser sign-in](#browser-sign-in) below)
```

Add this subsection directly before `## Important: Data Update Limitations`. Adjust the capture instructions to the Task 1 Spike Results.

```markdown
### Browser sign-in

If you sign in to Red Energy with Google, Apple or Microsoft, or with a code emailed to you, you have no password for the integration to use. Pick **Google, Apple, Microsoft or emailed code** during setup instead:

1. Use a desktop browser (Chrome or Edge). On a phone with the Red Energy app installed, the app intercepts the sign-in.
2. Press **F12** and select the **Console** tab.
3. Click the sign-in link shown in Home Assistant and sign in as normal.
4. The page won't change afterwards. The Console shows `Failed to launch 'au.com.redenergy://callback?code=...'`. Copy that address, starting `au.com.redenergy://`.
5. Paste it into Home Assistant straight away. The code expires quickly; if it does, open the link again.

Home Assistant then stays signed in by itself. If Red Energy ends the session (for example after a long outage or a password/security change), Home Assistant shows a **Re-authenticate** notification. Repeat the steps above.
```

- [ ] **Step 2: Update `CLAUDE.md`**

In `### Authentication`, after the numbered list and before "Okta client ID is hardcoded…", add:

```markdown
**Browser sign-in (issue #103)** — for SSO/email-code users with no password. The org is Okta Identity Engine, but `CLIENT_ID` only allows `authorization_code` + `refresh_token` grants, so the IDX/interaction-code API is unavailable. Instead `async_create_browser_login()` builds a PKCE authorize URL without a `sessionToken`. The user signs in on the hosted page and pastes the `au.com.redenergy://callback?code=…` URL. `async_complete_browser_login()` exchanges it. These entries store `auth_method: "browser"` + `refresh_token` (no password). The coordinator logs in with `authenticate_with_refresh_token()`, persists rotated tokens via `set_refresh_token_listener`, and raises `ConfigEntryAuthFailed` (→ `async_step_reauth`) only when the token endpoint returns 400/401. Entries without `auth_method` are password entries, so no config migration is needed.
```

- [ ] **Step 3: Full verification**

Run: `.venv/bin/pytest tests -q`
Expected: 0 failures. Record the total count.

Run: `.venv/bin/flake8 custom_components --count --select=E9,F63,F7,F82 --show-source --statistics`
Expected: `0`

Run: `git grep -nE "refresh_token|callback_url" -- custom_components | grep -i "_LOGGER\.\(info\|warning\|error\)"`
Expected: no line logs a token or callback URL value. Lines that only log error text are fine.

- [ ] **Step 4: Manual end-to-end in a real Home Assistant (maintainer)**

Install the branch build into a test HA instance (copy `custom_components/red_energy`, restart). Then check each of these:
1. Add the integration, choose **Google, Apple, Microsoft or emailed code**, sign in, paste the callback URL. The entry is created and sensors populate.
2. Restart HA. The entry loads without prompting. `.storage/core.config_entries` shows `"auth_method": "browser"` and a `refresh_token`, and no `password`.
3. If the spike showed rotation: after the next hourly token refresh, the stored `refresh_token` value has changed.
4. Paste a garbage URL. The form shows the "isn't the callback URL" error and the same link.
5. Corrupt the stored `refresh_token` (stop HA, edit `.storage/core.config_entries`, start HA). A **Re-authenticate** notification appears, and completing browser sign-in restores the entry.
6. Existing password entry: still loads and polls unchanged.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document browser sign-in for SSO and email-code accounts"
```

- [ ] **Step 6: Open the PR**

```bash
git push -u origin feat/browser-sign-in
gh pr create --title "feat: browser sign-in for SSO and email-code accounts" --body "$(cat <<'EOF'
Closes #103

- Add a sign-in method menu to setup: email/password, or Google/Apple/Microsoft/emailed code via the user's browser
- Browser sign-in uses a PKCE authorize URL on Red Energy's hosted Okta page; the user pastes the `au.com.redenergy://callback` URL back
- Browser entries store only a refresh token; rotated tokens are persisted to the config entry
- A rejected refresh token (HTTP 400/401) triggers Home Assistant's reauth flow; transient token-endpoint errors no longer count as auth failures
- `NoAccounts` during password setup now shows "no accounts" instead of "unexpected error"
- Existing password entries are unchanged, with no config migration

Commits:
- `chore: bump version to 1.23.0`
- `feat: add browser sign-in and refresh-token login to API client`
- `feat: authenticate browser sign-in entries with persisted refresh token`
- `feat: add browser sign-in and reauth to config flow for SSO users`
- `docs: document browser sign-in for SSO and email-code accounts`
EOF
)"
```

Expected: PR URL printed. Share it as a clickable link.

## Spike Results

Run 2026-10-29 with the maintainer's Red Energy login on desktop Chrome.

- **Callback capture:** works. The `au.com.redenergy://callback?code=…&state=…` URL was copied from the desktop browser and the `state` matched.
- **Code exchange:** `200`, returning `access_token`, `id_token`, `refresh_token`, `scope`, `token_type`, with `expires_in: 3600`. `offline_access` is granted, so a refresh token **is** issued.
- **Code lifetime:** the exchange succeeded 140 s after the link was generated, and that time includes the user signing in. The exact lifetime was not measured, so the UI copy still says "paste straight away".
- **Refresh:** `200`, with a new access token. **The refresh token rotates on every refresh.** That makes Task 3's persistence (`_async_persist_refresh_token`) mandatory, not optional.
- **Reuse of the pre-rotation refresh token** immediately afterwards: `200`, so Okta allows a grace period. Don't rely on it; always persist the newest token.
- **API access:** `GET /v1/properties` with the browser-login access token returned `200`, so the browser login has the same API access as the password login.

**Gate: passed.**
