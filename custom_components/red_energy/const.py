"""Constants for the Red Energy integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "red_energy"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_CLIENT_ID: Final = "client_id"

DEFAULT_NAME: Final = "Red Energy"
DEFAULT_SCAN_INTERVAL: Final = 300

ATTR_ACCOUNT_ID: Final = "account_id"
ATTR_SERVICE_TYPE: Final = "service_type"
ATTR_USAGE_DATE: Final = "usage_date"
ATTR_COST: Final = "cost"

SERVICE_TYPE_ELECTRICITY: Final = "electricity"
SERVICE_TYPE_GAS: Final = "gas"

API_TIMEOUT: Final = 30

# Configuration flow
STEP_USER: Final = "user"
STEP_ACCOUNT_SELECT: Final = "account_select"
STEP_SERVICE_SELECT: Final = "service_select"

# Error messages
ERROR_AUTH_FAILED: Final = "auth_failed"
ERROR_CANNOT_CONNECT: Final = "cannot_connect"
ERROR_INVALID_CLIENT_ID: Final = "invalid_client_id"
ERROR_UNKNOWN: Final = "unknown"
ERROR_NO_ACCOUNTS: Final = "no_accounts"

# Data keys
DATA_ACCOUNTS: Final = "accounts"
DATA_SELECTED_ACCOUNTS: Final = "selected_accounts"
DATA_CUSTOMER_DATA: Final = "customer_data"