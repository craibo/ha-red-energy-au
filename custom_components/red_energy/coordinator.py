"""DataUpdateCoordinator for Red Energy."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RedEnergyAPI, RedEnergyAPIError, RedEnergyAuthError
from .mock_api import MockRedEnergyAPI
from .data_validation import (
    DataValidationError,
    validate_customer_data,
    validate_properties_data,
    validate_usage_data,
)
from .const import (
    CONF_CLIENT_ID,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
)

_LOGGER = logging.getLogger(__name__)


class RedEnergyDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Red Energy data."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        client_id: str,
        selected_accounts: List[str],
        services: List[str],
    ) -> None:
        """Initialize the coordinator."""
        self.username = username
        self.password = password
        self.client_id = client_id
        self.selected_accounts = selected_accounts
        self.services = services
        
        # Initialize API client
        session = async_get_clientsession(hass)
        # TODO: Replace with RedEnergyAPI for production
        self.api = MockRedEnergyAPI(session)
        
        self._customer_data: Optional[Dict[str, Any]] = None
        self._properties: List[Dict[str, Any]] = []
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Red Energy API."""
        try:
            # Ensure we're authenticated
            if not self.api._access_token:
                _LOGGER.debug("Authenticating with Red Energy API")
                await self.api.authenticate(self.username, self.password, self.client_id)
            
            # Get customer and property data if not cached
            if not self._customer_data:
                raw_customer_data = await self.api.get_customer_data()
                self._customer_data = validate_customer_data(raw_customer_data)
                
                raw_properties = await self.api.get_properties()
                self._properties = validate_properties_data(raw_properties)
            
            # Fetch usage data for selected accounts and services
            usage_data = {}
            
            for property_data in self._properties:
                property_id = property_data.get("id")
                if property_id not in self.selected_accounts:
                    continue
                
                property_services = property_data.get("services", [])
                property_usage = {}
                
                for service in property_services:
                    service_type = service.get("type")
                    consumer_number = service.get("consumer_number")
                    
                    if not consumer_number or service_type not in self.services:
                        continue
                    
                    if not service.get("active", True):
                        _LOGGER.debug("Skipping inactive service %s for property %s", service_type, property_id)
                        continue
                    
                    try:
                        # Get usage data for the last 30 days
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=30)
                        
                        raw_usage = await self.api.get_usage_data(
                            consumer_number, start_date, end_date
                        )
                        
                        # Validate usage data
                        validated_usage = validate_usage_data(raw_usage)
                        
                        property_usage[service_type] = {
                            "consumer_number": consumer_number,
                            "usage_data": validated_usage,
                            "last_updated": end_date.isoformat(),
                        }
                        
                        _LOGGER.debug(
                            "Fetched %s usage data for property %s: %s total usage",
                            service_type,
                            property_id,
                            service_usage.get("total_usage", 0)
                        )
                        
                    except (RedEnergyAPIError, DataValidationError) as err:
                        _LOGGER.error(
                            "Failed to fetch/validate %s usage for property %s: %s",
                            service_type,
                            property_id,
                            err
                        )
                        # Don't fail the entire update for one service error
                        continue
                
                if property_usage:
                    usage_data[property_id] = {
                        "property": property_data,
                        "services": property_usage,
                    }
            
            if not usage_data:
                raise UpdateFailed("No usage data retrieved for any configured services")
            
            return {
                "customer": self._customer_data,
                "properties": self._properties,
                "usage_data": usage_data,
                "last_update": datetime.now().isoformat(),
            }
            
        except RedEnergyAuthError as err:
            _LOGGER.error("Authentication failed during update: %s", err)
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except RedEnergyAPIError as err:
            _LOGGER.error("API error during update: %s", err)
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error during update")
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def async_refresh_credentials(
        self, username: str, password: str, client_id: str
    ) -> bool:
        """Refresh credentials and test authentication."""
        try:
            # Update credentials
            self.username = username
            self.password = password
            self.client_id = client_id
            
            # Clear cached auth token to force re-authentication
            self.api._access_token = None
            self.api._refresh_token = None
            self.api._token_expires = None
            
            # Test new credentials
            success = await self.api.authenticate(username, password, client_id)
            if success:
                # Clear cached data to force refresh
                self._customer_data = None
                self._properties = []
                
                # Trigger data refresh
                await self.async_refresh()
                
            return success
            
        except Exception as err:
            _LOGGER.error("Failed to refresh credentials: %s", err)
            return False

    async def async_update_account_selection(
        self, selected_accounts: List[str], services: List[str]
    ) -> None:
        """Update account and service selection."""
        self.selected_accounts = selected_accounts
        self.services = services
        
        # Trigger data refresh with new selection
        await self.async_refresh()

    def get_property_data(self, property_id: str) -> Optional[Dict[str, Any]]:
        """Get cached property data by ID."""
        if not self.data or "usage_data" not in self.data:
            return None
        
        return self.data["usage_data"].get(property_id)

    def get_service_usage(self, property_id: str, service_type: str) -> Optional[Dict[str, Any]]:
        """Get usage data for a specific property and service."""
        property_data = self.get_property_data(property_id)
        if not property_data:
            return None
        
        return property_data.get("services", {}).get(service_type)

    def get_latest_usage(self, property_id: str, service_type: str) -> Optional[float]:
        """Get the most recent usage value for a property and service."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        # Return the latest day's usage
        return usage_data[-1].get("usage", 0.0)

    def get_total_cost(self, property_id: str, service_type: str) -> Optional[float]:
        """Get the total cost for a property and service."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        return service_data["usage_data"].get("total_cost", 0.0)

    def get_total_usage(self, property_id: str, service_type: str) -> Optional[float]:
        """Get the total usage for a property and service."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        return service_data["usage_data"].get("total_usage", 0.0)