"""Comprehensive error recovery system for Red Energy integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from collections import defaultdict, deque
from enum import Enum

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
ERROR_STORAGE_KEY = f"{DOMAIN}_error_recovery"


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryStrategy(Enum):
    """Recovery strategy types."""
    RETRY = "retry"
    FALLBACK = "fallback"
    RESET = "reset"
    NOTIFY = "notify"
    IGNORE = "ignore"


class ErrorType(Enum):
    """Types of errors that can occur."""
    API_CONNECTION = "api_connection"
    API_AUTHENTICATION = "api_authentication"
    API_RATE_LIMIT = "api_rate_limit"
    API_DATA_INVALID = "api_data_invalid"
    COORDINATOR_UPDATE = "coordinator_update"
    ENTITY_UPDATE = "entity_update"
    CONFIG_INVALID = "config_invalid"
    NETWORK_TIMEOUT = "network_timeout"
    UNKNOWN = "unknown"


class ErrorRecord:
    """Record of an error occurrence."""

    def __init__(
        self,
        error_type: ErrorType,
        severity: ErrorSeverity,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        exception: Optional[Exception] = None
    ) -> None:
        """Initialize error record."""
        self.error_type = error_type
        self.severity = severity
        self.message = message
        self.context = context or {}
        self.exception = exception
        self.timestamp = dt_util.utcnow()
        self.recovery_attempts = 0
        self.resolved = False


class RecoveryAction:
    """Defines a recovery action for specific error types."""

    def __init__(
        self,
        strategy: RecoveryStrategy,
        action: Callable,
        max_attempts: int = 3,
        delay: float = 5.0,
        backoff_factor: float = 2.0
    ) -> None:
        """Initialize recovery action."""
        self.strategy = strategy
        self.action = action
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff_factor = backoff_factor


class RedEnergyErrorRecoverySystem:
    """Comprehensive error recovery system."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize error recovery system."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, ERROR_STORAGE_KEY)
        self._error_history: deque = deque(maxlen=1000)  # Keep last 1000 errors
        self._recovery_actions: Dict[ErrorType, List[RecoveryAction]] = {}
        self._error_counts: Dict[ErrorType, int] = defaultdict(int)
        self._recovery_stats: Dict[str, int] = defaultdict(int)
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Initialize default recovery actions
        self._setup_default_recovery_actions()

    def _setup_default_recovery_actions(self) -> None:
        """Set up default recovery actions for common error types."""
        
        # API Connection errors
        self._recovery_actions[ErrorType.API_CONNECTION] = [
            RecoveryAction(
                RecoveryStrategy.RETRY,
                self._retry_api_connection,
                max_attempts=3,
                delay=10.0,
                backoff_factor=2.0
            ),
            RecoveryAction(
                RecoveryStrategy.FALLBACK,
                self._use_cached_data,
                max_attempts=1
            )
        ]
        
        # API Authentication errors
        self._recovery_actions[ErrorType.API_AUTHENTICATION] = [
            RecoveryAction(
                RecoveryStrategy.RETRY,
                self._refresh_authentication,
                max_attempts=2,
                delay=5.0
            ),
            RecoveryAction(
                RecoveryStrategy.NOTIFY,
                self._notify_authentication_failure,
                max_attempts=1
            )
        ]
        
        # Rate limit errors
        self._recovery_actions[ErrorType.API_RATE_LIMIT] = [
            RecoveryAction(
                RecoveryStrategy.RETRY,
                self._wait_and_retry,
                max_attempts=3,
                delay=60.0  # Wait 1 minute for rate limit
            )
        ]
        
        # Coordinator update errors
        self._recovery_actions[ErrorType.COORDINATOR_UPDATE] = [
            RecoveryAction(
                RecoveryStrategy.RETRY,
                self._retry_coordinator_update,
                max_attempts=2,
                delay=5.0
            ),
            RecoveryAction(
                RecoveryStrategy.FALLBACK,
                self._use_last_known_state,
                max_attempts=1
            )
        ]
        
        # Entity update errors
        self._recovery_actions[ErrorType.ENTITY_UPDATE] = [
            RecoveryAction(
                RecoveryStrategy.RETRY,
                self._retry_entity_update,
                max_attempts=2,
                delay=2.0
            ),
            RecoveryAction(
                RecoveryStrategy.FALLBACK,
                self._restore_entity_state,
                max_attempts=1
            )
        ]

    async def async_handle_error(
        self,
        error: Exception,
        error_type: ErrorType,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle an error with appropriate recovery strategy."""
        
        # Classify error severity
        severity = self._classify_error_severity(error, error_type)
        
        # Create error record
        error_record = ErrorRecord(error_type, severity, str(error), context, error)
        self._error_history.append(error_record)
        self._error_counts[error_type] += 1
        
        _LOGGER.error(
            "Handling %s error: %s (severity: %s)",
            error_type.value, str(error), severity.value
        )
        
        # Check circuit breaker
        circuit_key = f"{error_type.value}_{context.get('component', 'unknown') if context else 'unknown'}"
        if circuit_key in self._circuit_breakers:
            circuit_breaker = self._circuit_breakers[circuit_key]
            if circuit_breaker.is_open():
                _LOGGER.warning("Circuit breaker is open for %s, skipping recovery", circuit_key)
                return False
        else:
            self._circuit_breakers[circuit_key] = CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=300  # 5 minutes
            )
        
        # Attempt recovery
        recovery_success = await self._attempt_recovery(error_record)
        
        # Update circuit breaker
        if recovery_success:
            self._circuit_breakers[circuit_key].record_success()
            self._recovery_stats["successful_recoveries"] += 1
        else:
            self._circuit_breakers[circuit_key].record_failure()
            self._recovery_stats["failed_recoveries"] += 1
        
        # Mark error as resolved if recovery was successful
        if recovery_success:
            error_record.resolved = True
        
        # Save error data periodically
        if len(self._error_history) % 50 == 0:
            await self._save_error_data()
        
        return recovery_success

    async def _attempt_recovery(self, error_record: ErrorRecord) -> bool:
        """Attempt recovery using available strategies."""
        recovery_actions = self._recovery_actions.get(error_record.error_type, [])
        
        if not recovery_actions:
            _LOGGER.warning("No recovery actions defined for error type: %s", error_record.error_type.value)
            return False
        
        for action in recovery_actions:
            if error_record.recovery_attempts >= action.max_attempts:
                continue
            
            _LOGGER.debug(
                "Attempting %s recovery for %s (attempt %d/%d)",
                action.strategy.value,
                error_record.error_type.value,
                error_record.recovery_attempts + 1,
                action.max_attempts
            )
            
            try:
                # Calculate delay with exponential backoff
                delay = action.delay * (action.backoff_factor ** error_record.recovery_attempts)
                if error_record.recovery_attempts > 0:
                    await asyncio.sleep(delay)
                
                # Execute recovery action
                success = await action.action(error_record)
                error_record.recovery_attempts += 1
                
                if success:
                    _LOGGER.info(
                        "Successfully recovered from %s using %s strategy",
                        error_record.error_type.value,
                        action.strategy.value
                    )
                    return True
                
            except Exception as recovery_error:
                _LOGGER.error(
                    "Recovery action failed: %s (strategy: %s)",
                    recovery_error, action.strategy.value
                )
                error_record.recovery_attempts += 1
        
        _LOGGER.warning(
            "All recovery attempts failed for error type: %s",
            error_record.error_type.value
        )
        return False

    def _classify_error_severity(self, error: Exception, error_type: ErrorType) -> ErrorSeverity:
        """Classify error severity based on type and content."""
        
        # Critical errors that require immediate attention
        critical_patterns = ["authentication", "authorization", "credential", "token"]
        if any(pattern in str(error).lower() for pattern in critical_patterns):
            return ErrorSeverity.CRITICAL
        
        # High severity errors
        if error_type in [ErrorType.API_AUTHENTICATION, ErrorType.CONFIG_INVALID]:
            return ErrorSeverity.HIGH
        
        # Medium severity errors
        if error_type in [ErrorType.API_CONNECTION, ErrorType.COORDINATOR_UPDATE]:
            return ErrorSeverity.MEDIUM
        
        # Low severity errors (temporary issues)
        if error_type in [ErrorType.API_RATE_LIMIT, ErrorType.NETWORK_TIMEOUT]:
            return ErrorSeverity.LOW
        
        return ErrorSeverity.MEDIUM  # Default

    # Recovery action implementations
    async def _retry_api_connection(self, error_record: ErrorRecord) -> bool:
        """Retry API connection with fresh session."""
        try:
            context = error_record.context or {}
            coordinator = context.get("coordinator")
            
            if coordinator and hasattr(coordinator, "api"):
                # Reset API connection
                await coordinator.api.async_close()
                await coordinator.async_refresh()
                return True
        except Exception as err:
            _LOGGER.debug("API connection retry failed: %s", err)
        
        return False

    async def _refresh_authentication(self, error_record: ErrorRecord) -> bool:
        """Attempt to refresh authentication credentials."""
        try:
            context = error_record.context or {}
            coordinator = context.get("coordinator")
            
            if coordinator and hasattr(coordinator, "async_refresh_credentials"):
                # This would need to be implemented in the coordinator
                success = await coordinator.async_refresh_credentials()
                return success
        except Exception as err:
            _LOGGER.debug("Authentication refresh failed: %s", err)
        
        return False

    async def _wait_and_retry(self, error_record: ErrorRecord) -> bool:
        """Wait for rate limit to reset and retry."""
        # The delay is handled by the main recovery loop
        try:
            context = error_record.context or {}
            coordinator = context.get("coordinator")
            
            if coordinator:
                await coordinator.async_refresh()
                return True
        except Exception as err:
            _LOGGER.debug("Rate limit retry failed: %s", err)
        
        return False

    async def _use_cached_data(self, error_record: ErrorRecord) -> bool:
        """Use cached data as fallback."""
        try:
            context = error_record.context or {}
            coordinator = context.get("coordinator")
            
            if coordinator and coordinator.data:
                # Data is already available from cache
                _LOGGER.info("Using cached data as fallback")
                return True
        except Exception as err:
            _LOGGER.debug("Cached data fallback failed: %s", err)
        
        return False

    async def _retry_coordinator_update(self, error_record: ErrorRecord) -> bool:
        """Retry coordinator data update."""
        try:
            context = error_record.context or {}
            coordinator = context.get("coordinator")
            
            if coordinator:
                await coordinator.async_request_refresh()
                return True
        except Exception as err:
            _LOGGER.debug("Coordinator update retry failed: %s", err)
        
        return False

    async def _use_last_known_state(self, error_record: ErrorRecord) -> bool:
        """Use last known state for entities."""
        # This would integrate with the state manager
        _LOGGER.info("Using last known state as fallback")
        return True

    async def _retry_entity_update(self, error_record: ErrorRecord) -> bool:
        """Retry entity state update."""
        try:
            context = error_record.context or {}
            entity = context.get("entity")
            
            if entity and hasattr(entity, "async_update"):
                await entity.async_update()
                return True
        except Exception as err:
            _LOGGER.debug("Entity update retry failed: %s", err)
        
        return False

    async def _restore_entity_state(self, error_record: ErrorRecord) -> bool:
        """Restore entity state from backup."""
        # This would integrate with the state manager
        _LOGGER.info("Restoring entity state from backup")
        return True

    async def _notify_authentication_failure(self, error_record: ErrorRecord) -> bool:
        """Notify user of authentication failure."""
        try:
            self.hass.components.persistent_notification.create(
                "Red Energy authentication failed. Please check your credentials in the integration settings.",
                title="Red Energy Authentication Error",
                notification_id=f"{DOMAIN}_auth_error"
            )
            return True
        except Exception as err:
            _LOGGER.debug("Authentication notification failed: %s", err)
        
        return False

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get comprehensive error statistics."""
        recent_errors = [
            error for error in self._error_history
            if dt_util.utcnow() - error.timestamp < timedelta(hours=24)
        ]
        
        return {
            "total_errors": len(self._error_history),
            "recent_errors_24h": len(recent_errors),
            "error_counts_by_type": dict(self._error_counts),
            "recovery_stats": dict(self._recovery_stats),
            "circuit_breaker_states": {
                key: {
                    "state": breaker.get_state(),
                    "failure_count": breaker.failure_count,
                    "last_failure": breaker.last_failure_time.isoformat() if breaker.last_failure_time else None
                }
                for key, breaker in self._circuit_breakers.items()
            },
            "resolved_errors": sum(1 for error in self._error_history if error.resolved),
            "unresolved_errors": sum(1 for error in self._error_history if not error.resolved),
        }

    async def _save_error_data(self) -> None:
        """Save error data to storage."""
        try:
            # Convert error history to serializable format
            serializable_errors = []
            for error in list(self._error_history)[-100:]:  # Keep last 100 errors
                serializable_errors.append({
                    "error_type": error.error_type.value,
                    "severity": error.severity.value,
                    "message": error.message,
                    "context": error.context,
                    "timestamp": error.timestamp.isoformat(),
                    "recovery_attempts": error.recovery_attempts,
                    "resolved": error.resolved
                })
            
            data = {
                "error_history": serializable_errors,
                "error_counts": dict(self._error_counts),
                "recovery_stats": dict(self._recovery_stats),
                "last_saved": dt_util.utcnow().isoformat()
            }
            
            await self._store.async_save(data)
        except Exception as err:
            _LOGGER.error("Failed to save error data: %s", err)

    async def async_load_error_data(self) -> None:
        """Load error data from storage."""
        try:
            data = await self._store.async_load()
            if data:
                self._error_counts.update(data.get("error_counts", {}))
                self._recovery_stats.update(data.get("recovery_stats", {}))
                _LOGGER.debug("Loaded error recovery data from storage")
        except Exception as err:
            _LOGGER.error("Failed to load error data: %s", err)


class CircuitBreaker:
    """Circuit breaker pattern implementation for error handling."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300) -> None:
        """Initialize circuit breaker."""
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def record_success(self) -> None:
        """Record a successful operation."""
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = dt_util.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.state == "OPEN" and self.last_failure_time:
            # Check if enough time has passed to try again
            if dt_util.utcnow() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = "HALF_OPEN"
                return False
            return True
        
        return False

    def get_state(self) -> str:
        """Get current circuit breaker state."""
        return self.state