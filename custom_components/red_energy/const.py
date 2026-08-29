"""Constants for the Red Energy integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "red_energy"

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_CLIENT_ID: Final = "client_id"

CLIENT_ID: Final = "0oa1apu62kkqeet4C3l7"

DEFAULT_NAME: Final = "Red Energy"
DEFAULT_SCAN_INTERVAL: Final = 1800

# Device information
MANUFACTURER: Final = "Red Energy"

# Polling intervals (seconds)
SCAN_INTERVAL_OPTIONS: Final = {
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "2hour": 7200,
    "4hour": 14400,
}

# Advanced sensor types
SENSOR_TYPE_DAILY_AVERAGE: Final = "daily_average"
SENSOR_TYPE_MONTHLY_AVERAGE: Final = "monthly_average"
SENSOR_TYPE_PEAK_USAGE: Final = "peak_usage"
SENSOR_TYPE_EFFICIENCY: Final = "efficiency"
# Forward-looking estimates, not Red Energy's own figures (issues #75, #77).
# "Projected" (not "Current Period") distinguishes these forecast sensors
# from the actual/to-date SENSOR_TYPE_CURRENT_PERIOD_NET_COST sensor above.
SENSOR_TYPE_PROJECTED_NET_COST: Final = "projected_net_cost"
SENSOR_TYPE_PROJECTED_CHARGES: Final = "projected_charges"

# Breakdown sensor types - Daily (CORE)
SENSOR_TYPE_DAILY_IMPORT_USAGE: Final = "daily_import_usage"
SENSOR_TYPE_DAILY_EXPORT_USAGE: Final = "daily_export_usage"

# Breakdown sensor types - Current billing period to date (CORE)
# Named "current_period_*", not "total_*" - these reset every billing
# cycle (see _get_last_bill_reset) and only ever represent a partial sum
# accruing since lastBillDate, never a complete/lifetime total (issue #78).
SENSOR_TYPE_CURRENT_PERIOD_IMPORT_USAGE: Final = "current_period_import_usage"
SENSOR_TYPE_CURRENT_PERIOD_EXPORT_USAGE: Final = "current_period_export_usage"

# Breakdown sensor types - Current billing period to date, cost (CORE)
SENSOR_TYPE_CURRENT_PERIOD_IMPORT_COST: Final = "current_period_import_cost"
SENSOR_TYPE_CURRENT_PERIOD_EXPORT_CREDIT: Final = "current_period_export_credit"
SENSOR_TYPE_CURRENT_PERIOD_NET_COST: Final = "current_period_net_cost"

# Breakdown sensor types - Time period import (ADVANCED)
SENSOR_TYPE_PEAK_IMPORT_USAGE: Final = "peak_import_usage"
SENSOR_TYPE_OFFPEAK_IMPORT_USAGE: Final = "offpeak_import_usage"
SENSOR_TYPE_SHOULDER_IMPORT_USAGE: Final = "shoulder_import_usage"

# Breakdown sensor types - Time period export (ADVANCED)
SENSOR_TYPE_PEAK_EXPORT_USAGE: Final = "peak_export_usage"
SENSOR_TYPE_OFFPEAK_EXPORT_USAGE: Final = "offpeak_export_usage"
SENSOR_TYPE_SHOULDER_EXPORT_USAGE: Final = "shoulder_export_usage"

# Breakdown sensor types - Demand and environmental (ADVANCED)
SENSOR_TYPE_MAX_DEMAND: Final = "max_demand"
SENSOR_TYPE_CARBON_EMISSION: Final = "carbon_emission_tonne"

# CL2 (Controlled Load 2) / TOU inference sensors - only created for
# accounts whose plan has an unambiguous CL2 rate (see issue #61)
SENSOR_TYPE_CL2_ENERGY: Final = "cl2_inferred_energy"
SENSOR_TYPE_CORRECTED_PEAK_IMPORT: Final = "corrected_peak_import"
SENSOR_TYPE_CORRECTED_SHOULDER_IMPORT: Final = "corrected_shoulder_import"
SENSOR_TYPE_CORRECTED_OFFPEAK_IMPORT: Final = "corrected_offpeak_import"
SENSOR_TYPE_CL2_COST: Final = "cl2_inferred_cost"
SENSOR_TYPE_RECONSTRUCTED_IMPORT_COST: Final = "reconstructed_import_cost"

# Time period values (from API)
TIME_PERIOD_PEAK: Final = "PEAK"
TIME_PERIOD_OFFPEAK: Final = "OFFPEAK"
TIME_PERIOD_SHOULDER: Final = "SHOULDER"

# Service metadata sensor types
SENSOR_TYPE_NMI: Final = "nmi"
SENSOR_TYPE_METER_TYPE: Final = "meter_type"
SENSOR_TYPE_SOLAR: Final = "solar"
SENSOR_TYPE_PRODUCT_NAME: Final = "energy_plan"
SENSOR_TYPE_DISTRIBUTOR: Final = "distributor"
SENSOR_TYPE_BALANCE: Final = "balance"
SENSOR_TYPE_ARREARS: Final = "arrears"
SENSOR_TYPE_LAST_BILL_DATE: Final = "last_bill_date"
SENSOR_TYPE_NEXT_BILL_DATE: Final = "next_bill_date"
SENSOR_TYPE_BILLING_FREQUENCY: Final = "billing_frequency"
SENSOR_TYPE_JURISDICTION: Final = "jurisdiction"
SENSOR_TYPE_CHARGE_CLASS: Final = "charge_class"
SENSOR_TYPE_STATUS: Final = "status"
SENSOR_TYPE_ADDRESS: Final = "address"
SENSOR_TYPE_PAYMENT_TYPE: Final = "payment_type"
SENSOR_TYPE_RATE_PREFIX: Final = "rate"
SENSOR_TYPE_BILLING_PERIOD_SERVICE_CHARGE: Final = "billing_period_service_charge"

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

# Red Energy's consumptionDollar/import_cost field is ex-GST (see api.py's
# _normalize_usage_entry docstring); every cost/estimate/projection sensor
# in this integration must be GST-inclusive, so this uplifts the import
# component wherever it's read. generationDollar/export_credit (FIT/solar
# export credit) has no GST component and is never uplifted.
GST_MULTIPLIER: Final = 1.10

# Configuration flow
STEP_USER: Final = "user"
STEP_ACCOUNT_SELECT: Final = "account_select"

# Error messages
ERROR_AUTH_FAILED: Final = "auth_failed"
ERROR_CANNOT_CONNECT: Final = "cannot_connect"
ERROR_UNKNOWN: Final = "unknown"
ERROR_NO_ACCOUNTS: Final = "no_accounts"

# Data keys
DATA_ACCOUNTS: Final = "accounts"
DATA_SELECTED_ACCOUNTS: Final = "selected_accounts"
DATA_CUSTOMER_DATA: Final = "customer_data"