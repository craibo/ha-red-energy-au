"""Configuration validation and migration system for Red Energy integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CLIENT_ID,
    CONF_ENABLE_ADVANCED_SENSORS,
    CONF_SCAN_INTERVAL,
    DATA_SELECTED_ACCOUNTS,
    DOMAIN,
    SCAN_INTERVAL_OPTIONS,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
)

_LOGGER = logging.getLogger(__name__)

# Configuration version tracking
CONFIG_VERSION_1 = 1  # Initial version
CONFIG_VERSION_2 = 2  # Added advanced sensors and polling options
CONFIG_VERSION_3 = 3  # Added performance optimizations and device management
CURRENT_CONFIG_VERSION = CONFIG_VERSION_3


class ConfigValidationError(Exception):
    """Configuration validation error."""


class RedEnergyConfigMigrator:
    """Handle configuration migration between versions."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize config migrator."""
        self.hass = hass

    async def async_migrate_config_entry(self, config_entry: ConfigEntry) -> bool:
        """Migrate config entry to current version."""
        current_version = config_entry.version
        
        if current_version == CURRENT_CONFIG_VERSION:
            _LOGGER.debug("Config entry %s is already at current version", config_entry.entry_id)
            return True
        
        _LOGGER.info(
            "Migrating config entry %s from version %d to %d",
            config_entry.entry_id, current_version, CURRENT_CONFIG_VERSION
        )
        
        migration_success = True
        
        try:
            # Migrate from version 1 to 2
            if current_version < CONFIG_VERSION_2:
                migration_success &= await self._migrate_v1_to_v2(config_entry)
            
            # Migrate from version 2 to 3
            if current_version < CONFIG_VERSION_3:
                migration_success &= await self._migrate_v2_to_v3(config_entry)
            
            if migration_success:
                # Update version in config entry
                self.hass.config_entries.async_update_entry(
                    config_entry,
                    version=CURRENT_CONFIG_VERSION
                )
                _LOGGER.info("Successfully migrated config entry %s", config_entry.entry_id)
            else:
                _LOGGER.error("Failed to migrate config entry %s", config_entry.entry_id)
            
        except Exception as err:
            _LOGGER.error("Error during config migration: %s", err)
            migration_success = False
        
        return migration_success

    async def _migrate_v1_to_v2(self, config_entry: ConfigEntry) -> bool:
        """Migrate from version 1 to 2."""
        _LOGGER.debug("Migrating config entry from v1 to v2")
        
        try:
            # Add new configuration options with defaults
            new_data = dict(config_entry.data)
            new_options = dict(config_entry.options)
            
            # Add advanced sensors option (disabled by default for existing users)
            if CONF_ENABLE_ADVANCED_SENSORS not in new_options:
                new_options[CONF_ENABLE_ADVANCED_SENSORS] = False
            
            # Add scan interval option (5 minutes default)
            if CONF_SCAN_INTERVAL not in new_options:
                new_options[CONF_SCAN_INTERVAL] = "5min"
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                config_entry,
                data=new_data,
                options=new_options
            )
            
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to migrate v1 to v2: %s", err)
            return False

    async def _migrate_v2_to_v3(self, config_entry: ConfigEntry) -> bool:
        """Migrate from version 2 to 3."""
        _LOGGER.debug("Migrating config entry from v2 to v3")
        
        try:
            # Add performance and device management options
            new_options = dict(config_entry.options)
            
            # Add performance optimization options
            performance_defaults = {
                "enable_performance_monitoring": True,
                "memory_optimization_enabled": True,
                "bulk_processing_enabled": True,
                "state_restoration_enabled": True,
            }
            
            for key, default_value in performance_defaults.items():
                if key not in new_options:
                    new_options[key] = default_value
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                config_entry,
                options=new_options
            )
            
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to migrate v2 to v3: %s", err)
            return False


class RedEnergyConfigValidator:
    """Validate Red Energy configuration."""

    def __init__(self) -> None:
        """Initialize config validator."""
        self._validation_schemas = self._create_validation_schemas()

    def _create_validation_schemas(self) -> Dict[str, vol.Schema]:
        """Create validation schemas for different configuration aspects."""
        
        # Base configuration schema
        base_config_schema = vol.Schema({
            vol.Required(CONF_USERNAME): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
            vol.Required(CONF_CLIENT_ID): cv.string,
            vol.Required(DATA_SELECTED_ACCOUNTS): vol.All(cv.ensure_list, [cv.string]),
            vol.Required("services"): vol.All(
                cv.ensure_list, 
                [vol.In([SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS])]
            ),
        })
        
        # Options schema
        options_schema = vol.Schema({
            vol.Optional(CONF_ENABLE_ADVANCED_SENSORS, default=False): cv.boolean,
            vol.Optional(CONF_SCAN_INTERVAL, default="5min"): vol.In(list(SCAN_INTERVAL_OPTIONS.keys())),
            vol.Optional("enable_performance_monitoring", default=True): cv.boolean,
            vol.Optional("memory_optimization_enabled", default=True): cv.boolean,
            vol.Optional("bulk_processing_enabled", default=True): cv.boolean,
            vol.Optional("state_restoration_enabled", default=True): cv.boolean,
        }, extra=vol.ALLOW_EXTRA)
        
        # Account validation schema
        account_schema = vol.Schema({
            vol.Required("id"): cv.string,
            vol.Required("name"): cv.string,
            vol.Optional("address", default={}): dict,
            vol.Optional("services", default=[]): vol.All(
                cv.ensure_list,
                [vol.In([SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS])]
            ),
        })
        
        return {
            "base_config": base_config_schema,
            "options": options_schema,
            "account": account_schema,
        }

    def validate_config_entry(self, config_entry: ConfigEntry) -> Tuple[bool, List[str]]:
        """Validate a complete config entry."""
        errors = []
        
        try:
            # Validate base configuration
            self._validation_schemas["base_config"](config_entry.data)
        except vol.Error as err:
            errors.append(f"Base configuration validation failed: {err}")
        
        try:
            # Validate options
            self._validation_schemas["options"](config_entry.options)
        except vol.Error as err:
            errors.append(f"Options validation failed: {err}")
        
        # Additional validation checks
        validation_errors = self._perform_additional_validation(config_entry)
        errors.extend(validation_errors)
        
        return len(errors) == 0, errors

    def _perform_additional_validation(self, config_entry: ConfigEntry) -> List[str]:
        """Perform additional validation checks."""
        errors = []
        
        # Check that at least one account is selected
        selected_accounts = config_entry.data.get(DATA_SELECTED_ACCOUNTS, [])
        if not selected_accounts:
            errors.append("At least one account must be selected")
        
        # Check that at least one service is selected
        services = config_entry.data.get("services", [])
        if not services:
            errors.append("At least one service type must be selected")
        
        # Validate scan interval
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, "5min")
        if scan_interval not in SCAN_INTERVAL_OPTIONS:
            errors.append(f"Invalid scan interval: {scan_interval}")
        
        # Check for reasonable number of accounts (performance consideration)
        if len(selected_accounts) > 10:
            errors.append("Maximum of 10 accounts supported for optimal performance")
        
        return errors

    def validate_account_data(self, account_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate individual account data."""
        errors = []
        
        try:
            self._validation_schemas["account"](account_data)
        except vol.Error as err:
            errors.append(f"Account validation failed: {err}")
        
        return len(errors) == 0, errors

    def validate_credentials(
        self, 
        username: str, 
        password: str, 
        client_id: str
    ) -> Tuple[bool, List[str]]:
        """Validate credential format and content."""
        errors = []
        
        # Username validation (email format)
        if not username or "@" not in username:
            errors.append("Username must be a valid email address")
        
        # Password validation
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters long")
        
        # Client ID validation
        if not client_id or len(client_id) < 10:
            errors.append("Client ID must be at least 10 characters long")
        
        return len(errors) == 0, errors

    def suggest_configuration_improvements(
        self, 
        config_entry: ConfigEntry
    ) -> List[str]:
        """Suggest configuration improvements."""
        suggestions = []
        
        # Check if advanced sensors are disabled
        if not config_entry.options.get(CONF_ENABLE_ADVANCED_SENSORS, False):
            suggestions.append(
                "Enable advanced sensors for detailed usage analytics and efficiency monitoring"
            )
        
        # Check scan interval
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, "5min")
        if scan_interval == "1min":
            suggestions.append(
                "Consider using 5-minute polling interval to reduce API load and improve reliability"
            )
        elif scan_interval in ["30min", "1hour"]:
            suggestions.append(
                "Consider using shorter polling intervals (5-15 minutes) for more timely data updates"
            )
        
        # Check number of accounts
        selected_accounts = config_entry.data.get(DATA_SELECTED_ACCOUNTS, [])
        if len(selected_accounts) > 5:
            suggestions.append(
                "Large number of accounts may impact performance - consider creating separate integrations"
            )
        
        # Check services selection
        services = config_entry.data.get("services", [])
        if len(services) == 1:
            other_service = SERVICE_TYPE_GAS if services[0] == SERVICE_TYPE_ELECTRICITY else SERVICE_TYPE_ELECTRICITY
            suggestions.append(
                f"Consider enabling {other_service} monitoring if available for comprehensive energy tracking"
            )
        
        return suggestions


class ConfigHealthChecker:
    """Check configuration health and detect potential issues."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize config health checker."""
        self.hass = hass

    async def async_check_integration_health(
        self, 
        config_entry: ConfigEntry
    ) -> Dict[str, Any]:
        """Perform comprehensive health check of the integration configuration."""
        health_report = {
            "status": "healthy",
            "issues": [],
            "warnings": [],
            "suggestions": [],
            "performance_metrics": {},
        }
        
        # Basic configuration validation
        validator = RedEnergyConfigValidator()
        is_valid, validation_errors = validator.validate_config_entry(config_entry)
        
        if not is_valid:
            health_report["status"] = "unhealthy"
            health_report["issues"].extend(validation_errors)
        
        # Check coordinator health
        coordinator_health = await self._check_coordinator_health(config_entry)
        health_report["performance_metrics"].update(coordinator_health)
        
        # Check entity states
        entity_health = await self._check_entity_health(config_entry)
        health_report["performance_metrics"].update(entity_health)
        
        # Generate suggestions
        suggestions = validator.suggest_configuration_improvements(config_entry)
        health_report["suggestions"].extend(suggestions)
        
        # Determine overall health status
        if health_report["issues"]:
            health_report["status"] = "unhealthy"
        elif health_report["warnings"]:
            health_report["status"] = "degraded"
        
        return health_report

    async def _check_coordinator_health(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Check data coordinator health."""
        metrics = {
            "coordinator_status": "unknown",
            "last_update_success": False,
            "update_failures": 0,
        }
        
        try:
            entry_data = self.hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
            if entry_data and "coordinator" in entry_data:
                coordinator = entry_data["coordinator"]
                
                metrics["coordinator_status"] = "active"
                metrics["last_update_success"] = coordinator.last_update_success
                metrics["update_failures"] = getattr(coordinator, 'update_failures', 0)
                
                if coordinator.data:
                    metrics["data_available"] = True
                    metrics["accounts_with_data"] = len(coordinator.data.get("usage_data", {}))
                else:
                    metrics["data_available"] = False
        
        except Exception as err:
            _LOGGER.error("Error checking coordinator health: %s", err)
            metrics["coordinator_status"] = "error"
        
        return metrics

    async def _check_entity_health(self, config_entry: ConfigEntry) -> Dict[str, Any]:
        """Check entity health and availability."""
        from homeassistant.helpers import entity_registry as er
        
        entity_registry = er.async_get(self.hass)
        entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
        
        metrics = {
            "total_entities": len(entities),
            "available_entities": 0,
            "unavailable_entities": 0,
            "unknown_entities": 0,
        }
        
        for entity in entities:
            state = self.hass.states.get(entity.entity_id)
            if state:
                if state.state == "unavailable":
                    metrics["unavailable_entities"] += 1
                elif state.state == "unknown":
                    metrics["unknown_entities"] += 1
                else:
                    metrics["available_entities"] += 1
        
        # Calculate availability ratio
        if metrics["total_entities"] > 0:
            metrics["availability_ratio"] = metrics["available_entities"] / metrics["total_entities"]
        else:
            metrics["availability_ratio"] = 0
        
        return metrics

    def generate_health_summary(self, health_report: Dict[str, Any]) -> str:
        """Generate a human-readable health summary."""
        status = health_report["status"]
        issues_count = len(health_report["issues"])
        warnings_count = len(health_report["warnings"])
        
        summary = f"Integration Health: {status.upper()}\n"
        
        if issues_count > 0:
            summary += f"• {issues_count} critical issues found\n"
        
        if warnings_count > 0:
            summary += f"• {warnings_count} warnings\n"
        
        # Performance metrics
        metrics = health_report["performance_metrics"]
        if "availability_ratio" in metrics:
            availability_pct = metrics["availability_ratio"] * 100
            summary += f"• Entity availability: {availability_pct:.1f}%\n"
        
        if "accounts_with_data" in metrics:
            summary += f"• Accounts with data: {metrics['accounts_with_data']}\n"
        
        # Suggestions
        suggestions_count = len(health_report["suggestions"])
        if suggestions_count > 0:
            summary += f"• {suggestions_count} optimization suggestions available\n"
        
        return summary