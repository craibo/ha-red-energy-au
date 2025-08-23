"""State management and restoration for Red Energy entities."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_entity_states"


class RedEnergyStateManager:
    """Manage entity state persistence and restoration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize state manager."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._entity_states: Dict[str, Dict[str, Any]] = {}
        self._restoration_data: Dict[str, Any] = {}
        self._state_history: Dict[str, List[Dict[str, Any]]] = {}
        self._max_history_entries = 100

    async def async_load_states(self) -> None:
        """Load saved states from storage."""
        try:
            data = await self._store.async_load()
            if data:
                self._entity_states = data.get("entity_states", {})
                self._restoration_data = data.get("restoration_data", {})
                self._state_history = data.get("state_history", {})
                _LOGGER.debug("Loaded %d entity states from storage", len(self._entity_states))
        except Exception as err:
            _LOGGER.error("Failed to load entity states: %s", err)
            self._entity_states = {}
            self._restoration_data = {}
            self._state_history = {}

    async def async_save_states(self) -> None:
        """Save current states to storage."""
        try:
            # Clean up old history entries before saving
            self._cleanup_old_history()
            
            data = {
                "entity_states": self._entity_states,
                "restoration_data": self._restoration_data,
                "state_history": self._state_history,
                "last_saved": dt_util.utcnow().isoformat()
            }
            await self._store.async_save(data)
            _LOGGER.debug("Saved %d entity states to storage", len(self._entity_states))
        except Exception as err:
            _LOGGER.error("Failed to save entity states: %s", err)

    def record_entity_state(
        self, 
        entity_id: str, 
        state: str, 
        attributes: Dict[str, Any]
    ) -> None:
        """Record entity state for restoration."""
        now = dt_util.utcnow()
        
        # Store current state
        self._entity_states[entity_id] = {
            "state": state,
            "attributes": dict(attributes),
            "last_updated": now.isoformat(),
            "domain": entity_id.split('.')[0]
        }
        
        # Add to history
        if entity_id not in self._state_history:
            self._state_history[entity_id] = []
        
        history_entry = {
            "state": state,
            "timestamp": now.isoformat(),
            "key_attributes": self._extract_key_attributes(attributes)
        }
        
        self._state_history[entity_id].append(history_entry)
        
        # Limit history size
        if len(self._state_history[entity_id]) > self._max_history_entries:
            self._state_history[entity_id] = self._state_history[entity_id][-self._max_history_entries:]

    def _extract_key_attributes(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key attributes for history tracking."""
        key_attrs = {}
        
        # Always include these attributes if present
        important_attrs = [
            "unit_of_measurement", "device_class", "state_class",
            "calculation_period", "peak_date", "usage_variation",
            "friendly_name", "icon"
        ]
        
        for attr in important_attrs:
            if attr in attributes:
                key_attrs[attr] = attributes[attr]
        
        return key_attrs

    def get_restoration_data(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get restoration data for an entity."""
        if entity_id not in self._entity_states:
            return None
        
        entity_data = self._entity_states[entity_id]
        
        # Check if data is too old (older than 7 days)
        try:
            last_updated = datetime.fromisoformat(entity_data["last_updated"])
            if dt_util.utcnow() - last_updated > timedelta(days=7):
                _LOGGER.debug("Restoration data for %s is too old, ignoring", entity_id)
                return None
        except (ValueError, KeyError):
            return None
        
        return {
            "state": entity_data["state"],
            "attributes": entity_data["attributes"]
        }

    def get_entity_history(
        self, 
        entity_id: str, 
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get entity state history for the specified time period."""
        if entity_id not in self._state_history:
            return []
        
        cutoff_time = dt_util.utcnow() - timedelta(hours=hours)
        recent_history = []
        
        for entry in self._state_history[entity_id]:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if entry_time >= cutoff_time:
                    recent_history.append(entry)
            except (ValueError, KeyError):
                continue
        
        return recent_history

    async def async_restore_entity_states(
        self, 
        entity_ids: List[str]
    ) -> Dict[str, bool]:
        """Restore states for multiple entities."""
        restoration_results = {}
        
        for entity_id in entity_ids:
            try:
                restoration_data = self.get_restoration_data(entity_id)
                if restoration_data:
                    # Set the restored state
                    self.hass.states.async_set(
                        entity_id,
                        restoration_data["state"],
                        restoration_data["attributes"]
                    )
                    restoration_results[entity_id] = True
                    _LOGGER.debug("Restored state for %s", entity_id)
                else:
                    restoration_results[entity_id] = False
            except Exception as err:
                _LOGGER.error("Failed to restore state for %s: %s", entity_id, err)
                restoration_results[entity_id] = False
        
        return restoration_results

    def mark_entity_for_restoration(
        self, 
        entity_id: str, 
        restoration_strategy: str = "last_known"
    ) -> None:
        """Mark entity for specific restoration strategy."""
        self._restoration_data[entity_id] = {
            "strategy": restoration_strategy,
            "marked_at": dt_util.utcnow().isoformat()
        }

    def _cleanup_old_history(self) -> None:
        """Clean up old history entries."""
        cutoff_time = dt_util.utcnow() - timedelta(days=30)
        entities_to_clean = []
        
        for entity_id, history in self._state_history.items():
            cleaned_history = []
            for entry in history:
                try:
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_time:
                        cleaned_history.append(entry)
                except (ValueError, KeyError):
                    continue
            
            if cleaned_history:
                self._state_history[entity_id] = cleaned_history
            else:
                entities_to_clean.append(entity_id)
        
        # Remove entities with no recent history
        for entity_id in entities_to_clean:
            del self._state_history[entity_id]
            if entity_id in self._entity_states:
                del self._entity_states[entity_id]
            if entity_id in self._restoration_data:
                del self._restoration_data[entity_id]

    async def async_handle_entity_unavailable(
        self, 
        entity_id: str, 
        restore_immediately: bool = False
    ) -> bool:
        """Handle entity becoming unavailable."""
        _LOGGER.debug("Entity %s became unavailable", entity_id)
        
        if restore_immediately:
            restoration_data = self.get_restoration_data(entity_id)
            if restoration_data:
                try:
                    self.hass.states.async_set(
                        entity_id,
                        restoration_data["state"],
                        restoration_data["attributes"]
                    )
                    _LOGGER.info("Immediately restored state for unavailable entity %s", entity_id)
                    return True
                except Exception as err:
                    _LOGGER.error("Failed to restore unavailable entity %s: %s", entity_id, err)
        
        return False

    def get_availability_stats(self) -> Dict[str, Any]:
        """Get entity availability statistics."""
        total_entities = len(self._entity_states)
        available_count = 0
        unavailable_count = 0
        
        for entity_id, entity_data in self._entity_states.items():
            current_state = self.hass.states.get(entity_id)
            if current_state and current_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                available_count += 1
            else:
                unavailable_count += 1
        
        return {
            "total_entities": total_entities,
            "available_entities": available_count,
            "unavailable_entities": unavailable_count,
            "availability_ratio": available_count / total_entities if total_entities > 0 else 0,
            "entities_with_history": len(self._state_history),
            "total_history_entries": sum(len(history) for history in self._state_history.values())
        }


class RedEnergyRestoreEntity(RestoreEntity):
    """Base class for Red Energy entities with state restoration."""

    def __init__(self, state_manager: RedEnergyStateManager, *args, **kwargs):
        """Initialize restore entity."""
        super().__init__(*args, **kwargs)
        self._state_manager = state_manager
        self._restored_state: Optional[State] = None
        self._restoration_successful = False

    async def async_added_to_hass(self) -> None:
        """Handle entity being added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Attempt to restore last state
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._restored_state = last_state
            self._restoration_successful = True
            _LOGGER.debug("Restored last state for %s: %s", self.entity_id, last_state.state)
        else:
            # Try custom restoration data
            restoration_data = self._state_manager.get_restoration_data(self.entity_id)
            if restoration_data:
                # Create a State object from restoration data
                self._restored_state = State(
                    self.entity_id,
                    restoration_data["state"],
                    restoration_data["attributes"]
                )
                self._restoration_successful = True
                _LOGGER.debug("Restored from state manager for %s", self.entity_id)

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity being removed from Home Assistant."""
        # Record final state before removal
        if self.state is not None:
            self._state_manager.record_entity_state(
                self.entity_id,
                str(self.state),
                self.extra_state_attributes or {}
            )
        
        await super().async_will_remove_from_hass()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Use restored state as available if no current data
        if not self._restoration_successful and self._restored_state:
            return True
        return super().available

    def _record_current_state(self) -> None:
        """Record current state for future restoration."""
        if self.state is not None:
            self._state_manager.record_entity_state(
                self.entity_id,
                str(self.state),
                self.extra_state_attributes or {}
            )

    async def async_update(self) -> None:
        """Update entity and record state."""
        await super().async_update()
        
        # Record state after successful update
        if hasattr(self, '_attr_native_value') and self._attr_native_value is not None:
            self._record_current_state()


class EntityAvailabilityManager:
    """Manage entity availability and recovery."""

    def __init__(self, hass: HomeAssistant, state_manager: RedEnergyStateManager) -> None:
        """Initialize availability manager."""
        self.hass = hass
        self._state_manager = state_manager
        self._unavailable_entities: Set[str] = set()
        self._recovery_attempts: Dict[str, int] = {}
        self._max_recovery_attempts = 3

    async def async_monitor_entity_availability(self, entity_ids: List[str]) -> None:
        """Monitor entity availability and attempt recovery."""
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            
            if not state or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                if entity_id not in self._unavailable_entities:
                    _LOGGER.warning("Entity %s became unavailable", entity_id)
                    self._unavailable_entities.add(entity_id)
                    self._recovery_attempts[entity_id] = 0
                
                # Attempt recovery if under max attempts
                if self._recovery_attempts.get(entity_id, 0) < self._max_recovery_attempts:
                    await self._attempt_entity_recovery(entity_id)
                    self._recovery_attempts[entity_id] += 1
            else:
                # Entity is available again
                if entity_id in self._unavailable_entities:
                    _LOGGER.info("Entity %s recovered and is now available", entity_id)
                    self._unavailable_entities.discard(entity_id)
                    self._recovery_attempts.pop(entity_id, None)

    async def _attempt_entity_recovery(self, entity_id: str) -> bool:
        """Attempt to recover an unavailable entity."""
        _LOGGER.debug("Attempting recovery for entity %s", entity_id)
        
        # Try state restoration first
        success = await self._state_manager.async_handle_entity_unavailable(
            entity_id, restore_immediately=True
        )
        
        if success:
            _LOGGER.info("Successfully recovered entity %s using state restoration", entity_id)
            return True
        
        # Additional recovery strategies can be added here
        # For now, we'll just log the attempt
        _LOGGER.debug("State restoration recovery failed for %s", entity_id)
        return False

    def get_unavailable_entities(self) -> List[str]:
        """Get list of currently unavailable entities."""
        return list(self._unavailable_entities)

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        return {
            "unavailable_count": len(self._unavailable_entities),
            "unavailable_entities": list(self._unavailable_entities),
            "recovery_attempts": dict(self._recovery_attempts),
            "entities_over_max_attempts": [
                entity_id for entity_id, attempts in self._recovery_attempts.items()
                if attempts >= self._max_recovery_attempts
            ]
        }