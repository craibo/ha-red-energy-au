# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration for Red Energy (Australian energy provider) that polls a private API for electricity and gas usage data. Deployed via HACS. Current version: 1.7.5.

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
1. POST credentials → Okta session token
2. Generate PKCE code_verifier/challenge
3. Exchange sessionToken + challenge → authorization code
4. Exchange code → access + refresh tokens
5. Bearer token on all API calls; auto-refresh on expiry

Okta client ID is hardcoded in `const.py`. VPN must be disabled when authenticating.

### Data Flow

```
config_flow.py       → validates credentials, discovers properties, stores config entry
coordinator.py       → polls API on schedule (default 30min), caches data in self.data
sensor.py            → CoordinatorEntity subclasses that read from coordinator.data
```

**Important**: Red Energy's API only updates usage data once daily (~3am AEST). Polling more frequently than 30 minutes has no benefit.

### Key API Endpoints (via `api.py`)

- `GET /customers/{accountId}` — customer info
- `GET /customers/{accountId}/properties` — property/account list
- `GET /properties/{propertyId}/usage/{serviceType}` — usage data (electricity/gas)

API response field names are non-standard (e.g. `consumers` not `services`, energy type codes `E`/`G`).

### Sensor Architecture (`sensor.py`)

Two tiers of sensors per service (electricity or gas) per property:

- **Core sensors** (22 per service, always created): usage/cost totals, account metadata, billing dates
- **Advanced sensors** (13 per service, optional toggle): time-of-use breakdown, peak demand, statistics, carbon emissions

Unique IDs follow the pattern: `{property_id}_{service_type}_{sensor_type}`

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
- `energy.py` — registers sensors with the HA Energy Dashboard
- `diagnostics.py` — provides debug data for HA diagnostics download

## Testing

Tests use pytest with mocks; no live API calls. Key test infrastructure:

- `tests/conftest.py` — shared fixtures
- `tests/test_mocks.py` — mock API responses and fake property/usage data

When adding sensors, update both `sensor.py` and the corresponding sensor tests. When changing API response handling, update `data_validation.py` and `test_data_validation_errors.py`.

## Developer Reference

Detailed documentation on authentication, API structure, and billing period logic lives in `.cursor/rules/`:
- `red-energy-authentication.mdc` — OAuth2 flow details and troubleshooting
- `red-energy-api-structure.mdc` — field mappings, validation rules
- `billing-period-calculation.mdc` — how billing period dates are derived from `lastBillDate`
