"""Constants for the Red Energy integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "red_energy"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_CLIENT_ID: Final = "client_id"

DEFAULT_NAME: Final = "Red Energy"
DEFAULT_SCAN_INTERVAL: Final = 300

# Polling intervals (seconds)
SCAN_INTERVAL_OPTIONS: Final = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
}

# Advanced sensor types
SENSOR_TYPE_DAILY_AVERAGE: Final = "daily_average"
SENSOR_TYPE_MONTHLY_AVERAGE: Final = "monthly_average"
SENSOR_TYPE_PEAK_USAGE: Final = "peak_usage"
SENSOR_TYPE_EFFICIENCY: Final = "efficiency"

# Configuration options
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_ENABLE_ADVANCED_SENSORS: Final = "enable_advanced_sensors"
CONF_COST_THRESHOLDS: Final = "cost_thresholds"
CONF_USAGE_THRESHOLDS: Final = "usage_thresholds"

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