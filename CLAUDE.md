# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration for Red Energy (Australian energy provider) that polls a private API for electricity and gas usage data. Deployed via HACS. Current version: 1.7.7.

## Branch Workflow

Always work on a feature/fix branch — never commit directly to `main`. Create a PR to merge into `main`.

When starting a new branch, bump the `version` field in `custom_components/red_energy/manifest.json` as the first commit, following semantic versioning (MAJOR.MINOR.PATCH): PATCH for bug fixes, MINOR for new features, MAJOR for breaking changes.

## Commands

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_coordinator.py -v

# Run a single test
pytest tests/test_coordinator.py::TestCoordinator::test_update -v

# Lint (syntax errors only — strict)
flake8 custom_components --count --select=E9,F63,F7,F82 --show-source --statistics

# Lint (full — max-complexity=10, max-line-length=127)
flake8 custom_components --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Type checking
mypy custom_components/red_energy --ignore-missing-imports
```

CI runs Python 3.11 and 3.12. pytest and mypy failures are `continue-on-error: true` in CI.

## Architecture

All integration code lives in `custom_components/red_energy/`.

### Authentication

Red Energy uses **OAuth2 PKCE via Okta** (redenergy.okta.com). The flow in `api.py`:
1. POST credentials → Okta session token (`https://redenergy.okta.com/api/v1/authn`)
2. Fetch OAuth2 endpoints from discovery URL (`https://login.redenergy.com.au/oauth2/default/.well-known/openid-configuration`)
3. Generate PKCE code_verifier (48-char random) / code_challenge (SHA256)
4. Exchange sessionToken + PKCE challenge → authorization code
5. Exchange code → access + refresh tokens
6. Bearer token on all API calls; auto-refresh on expiry (default 1hr)

Okta client ID is hardcoded in `const.py`. VPN must be disabled when authenticating. Users must capture `client_id` from the Red Energy mobile app.

### Data Flow

```
config_flow.py       → validates credentials, discovers properties, stores config entry
coordinator.py       → polls API on schedule (default 30min), caches data in self.data
sensor.py            → CoordinatorEntity subclasses that read from coordinator.data
```

**Important**: Red Energy's API only updates usage data once daily (~3am AEST). Polling more frequently than 30 minutes has no benefit.

### Key API Endpoints (via `api.py`)

Base URL: `https://selfservice.services.retail.energy/v1`

- `GET /customers/current` — customer info
- `GET /properties` — property/account list
- `GET /usage/interval?consumerNumber=X&fromDate=Y&toDate=Z` — daily summaries with 48 half-hourly intervals per day

### API Field Mappings

The Red Energy API uses non-standard field names:

| API Field | Internal Field | Notes |
|-----------|---------------|-------|
| `consumers` | `services` | Array of utility services |
| `utility: "E"` | `type: "electricity"` | Utility code mapping |
| `utility: "G"` | `type: "gas"` | Utility code mapping |
| `consumerNumber` | `consumer_number` | camelCase → snake_case |
| `status: "ON"` | `active: true` | String → bool |
| `accountNumber` | `id` | Primary property identifier |
| `suburb` | `city` | Australian terminology |
| `displayAddresses.shortForm` | `name` | Preferred property display name |

Address fields can be `null` in the API — always use `(data.get("field") or "").strip()` not `data.get("field", "").strip()`.

### Usage Data Structure

The `/usage/interval` endpoint returns an **array of daily summaries**, each with 48 half-hourly intervals:

```json
[
  {
    "usageDate": "2025-09-06",
    "halfHours": [
      {
        "intervalStart": "2025-09-06T00:00:00+10:00",
        "primaryConsumptionTariffComponent": "OFFPEAK",
        "consumptionKwh": 0.128,
        "generationKwh": 0.0,
        "consumptionDollar": 0.03,
        "generationDollar": 0.0
      }
    ],
    "consumptionDollar": 1.65,
    "generationDollar": -0.3279,
    "carbonEmissionTonne": 0.0057
  }
]
```

`api.py` transforms this via `_transform_usage_data()` and `_normalize_usage_entry()`. Each normalized entry includes `import_usage`, `export_usage`, `import_cost`, `export_credit`, time-period breakdowns (peak/offpeak/shoulder), `max_demand_kw`, and `carbon_emission_tonne`.

### Sensor Architecture (`sensor.py`)

Two tiers of sensors per service (electricity or gas) per property:

- **Core sensors** (22 per service, always created): daily/total import/export usage and cost, account metadata, billing dates
- **Advanced sensors** (13 per service, optional toggle): time-of-use breakdown (peak/offpeak/shoulder), peak demand, carbon emissions

Unique IDs follow the pattern: `{domain}_{entry_id}_{property_id}_{service_type}_{sensor_type}`

`TOTAL` state-class sensors (`total_import_usage`, `total_export_usage`, `total_import_cost`, `total_export_credit`) set `last_reset` to `lastBillDate` so HA's Energy Dashboard statistics reset correctly at the billing period boundary.

### Billing Period

`coordinator.py:_get_usage_period_dates()` reads `lastBillDate` from the service metadata and uses it as the start date for the usage fetch. Falls back to 30 days if missing or invalid.

### Stage 5 Components

Production enhancements loaded by `__init__.py` at setup time:

| File | Role |
|------|------|
| `state_manager.py` | Persists entity states to disk; restores on HA restart |
| `device_manager.py` | Manages device registry entries per property |
| `error_recovery.py` | Circuit breaker + retry with exponential backoff |
| `performance.py` | Timing and memory metrics |
| `config_migration.py` | Migrates config entries v1→v6 automatically |

### Supporting Files

- `data_validation.py` — validates and transforms all API responses before coordinator stores them
- `services.py` — implements `red_energy.refresh_data`, `red_energy.update_credentials`, `red_energy.export_data`
- `button.py` — exposes refresh/export/credential-update actions as HA button entities
- `energy.py` — registers sensors with the HA Energy Dashboard
- `diagnostics.py` — provides debug data for HA diagnostics download

## Testing

Tests use pytest with mocks; no live API calls. Key test infrastructure:

- `tests/conftest.py` — shared fixtures
- `tests/test_mocks.py` — mock API responses and fake property/usage data

When adding sensors, update both `sensor.py` and the corresponding sensor tests. When changing API response handling, update `data_validation.py` and `test_data_validation_errors.py`.

## HACS

`hacs.json` accepts only `name`, `country`, and `homeassistant` keys — do not add `domains` or `iot_class` there (those belong in `manifest.json`). Required GitHub repository topics: `home-assistant`, `homeassistant`, `custom-component`, `integration`.

## Enable Debug Logging

To diagnose issues, add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.red_energy: debug
```

The API client logs the full raw `/usage/interval` response at DEBUG level on the first call, useful for diagnosing data mapping issues.
