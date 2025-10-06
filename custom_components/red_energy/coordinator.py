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
from .data_validation import (
    DataValidationError,
    validate_customer_data,
    validate_properties_data,
    validate_usage_data,
)
from .error_recovery import RedEnergyErrorRecoverySystem, ErrorType
from .performance import PerformanceMonitor, DataProcessor
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
        
        # Initialize Stage 5 enhancements
        self._error_recovery = RedEnergyErrorRecoverySystem(hass)
        self._performance_monitor = PerformanceMonitor(hass)
        self._data_processor = DataProcessor(self._performance_monitor)
        self.update_failures = 0
        self.services = services
        
        # Initialize API client
        session = async_get_clientsession(hass)
        # Use real Red Energy API
        self.api = RedEnergyAPI(session)
        
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
                _LOGGER.info("Authenticating with Red Energy API")
                await self.api.authenticate(self.username, self.password, self.client_id)
            
            # Get customer and property data if not cached
            if not self._customer_data:
                raw_customer_data = await self.api.get_customer_data()
                _LOGGER.info("=" * 80)
                _LOGGER.info("RAW CUSTOMER API RESPONSE:")
                _LOGGER.info("Type: %s", type(raw_customer_data))
                _LOGGER.info("Data: %s", raw_customer_data)
                _LOGGER.info("=" * 80)
                self._customer_data = validate_customer_data(raw_customer_data)
                _LOGGER.info("Validated customer data - ID: %s, Name: %s", 
                            self._customer_data.get("id"), self._customer_data.get("name"))
                
                raw_properties = await self.api.get_properties()
                _LOGGER.info("=" * 80)
                _LOGGER.info("RAW PROPERTIES API RESPONSE:")
                _LOGGER.info("Type: %s", type(raw_properties))
                _LOGGER.info("Count: %d", len(raw_properties) if isinstance(raw_properties, list) else 0)
                _LOGGER.info("Data: %s", raw_properties)
                _LOGGER.info("=" * 80)
                self._properties = validate_properties_data(raw_properties)
                _LOGGER.info("Validated %d properties:", len(self._properties))
                for prop in self._properties:
                    _LOGGER.info("  - Property ID: %s, Name: %s, Services: %s", 
                                prop.get("id"), prop.get("name"), 
                                [s.get("type") for s in prop.get("services", [])])
            
            # Log selected accounts configuration
            _LOGGER.info("=" * 80)
            _LOGGER.info("COORDINATOR CONFIGURATION:")
            _LOGGER.info("Selected accounts: %s (type: %s)", self.selected_accounts, type(self.selected_accounts))
            _LOGGER.info("Configured services: %s", self.services)
            _LOGGER.info("Total properties available: %d", len(self._properties))
            property_ids = [str(p.get("id")) for p in self._properties]
            _LOGGER.info("Available property IDs: %s (types: %s)", property_ids, [type(pid) for pid in property_ids])
            _LOGGER.info("=" * 80)
            
            # Fetch usage data for selected accounts and services
            usage_data = {}
            
            matched_properties = 0
            skipped_properties = 0
            
            for property_data in self._properties:
                property_id = property_data.get("id")
                property_name = property_data.get("name", "Unknown")
                
                _LOGGER.info("Processing property: ID='%s' (type: %s), Name='%s'", property_id, type(property_id), property_name)
                
                # Convert to string for comparison since selected_accounts are strings
                property_id_str = str(property_id)
                if property_id_str not in self.selected_accounts:
                    _LOGGER.warning(
                        "Property '%s' (ID: %s) not in selected_accounts %s - SKIPPING",
                        property_name, property_id, self.selected_accounts
                    )
                    skipped_properties += 1
                    continue
                
                matched_properties += 1
                _LOGGER.info("Property '%s' (ID: %s) MATCHED - fetching usage data", property_name, property_id_str)
                
                property_services = property_data.get("services", [])
                _LOGGER.info("  Property has %d services: %s", 
                            len(property_services),
                            [s.get("type") for s in property_services])
                property_usage = {}
                
                for service in property_services:
                    service_type = service.get("type")
                    consumer_number = service.get("consumer_number")
                    is_active = service.get("active", True)
                    
                    _LOGGER.info("  Processing service: type=%s, consumer_number=%s, active=%s", 
                                service_type, consumer_number, is_active)
                    
                    if not consumer_number:
                        _LOGGER.warning("    Service %s has no consumer_number - SKIPPING", service_type)
                        continue
                    
                    if service_type not in self.services:
                        _LOGGER.info("    Service %s not in configured services %s - SKIPPING", 
                                    service_type, self.services)
                        continue
                    
                    if not is_active:
                        _LOGGER.info("    Service %s is inactive - SKIPPING", service_type)
                        continue
                    
                    _LOGGER.info("    Service %s MATCHED - fetching usage data", service_type)
                    
                    try:
                        # Get usage data for the last 30 days
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=30)
                        
                        _LOGGER.info("    Calling API get_usage_data: consumer=%s, from=%s, to=%s",
                                    consumer_number, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                        
                        raw_usage = await self.api.get_usage_data(
                            consumer_number, start_date, end_date
                        )
                        
                        _LOGGER.info("    Raw usage API response type: %s", type(raw_usage))
                        _LOGGER.info("    Raw usage API response: %s", raw_usage)
                        
                        # Validate usage data
                        validated_usage = validate_usage_data(raw_usage)
                        
                        property_usage[service_type] = {
                            "consumer_number": consumer_number,
                            "usage_data": validated_usage,
                            "last_updated": end_date.isoformat(),
                        }
                        
                        _LOGGER.info(
                            "    ✓ Successfully fetched %s usage for property %s: %s total usage, %s total cost",
                            service_type,
                            property_id,
                            validated_usage.get("total_usage", 0),
                            validated_usage.get("total_cost", 0)
                        )
                        
                    except (RedEnergyAPIError, DataValidationError) as err:
                        _LOGGER.error(
                            "    ✗ Failed to fetch/validate %s usage for property %s: %s",
                            service_type,
                            property_id,
                            err,
                            exc_info=True
                        )
                        # Don't fail the entire update for one service error
                        continue
                
                if property_usage:
                    usage_data[property_id_str] = {
                        "property": property_data,
                        "services": property_usage,
                    }
                    _LOGGER.info("✓ Successfully collected usage data for property '%s' with %d services", 
                                property_name, len(property_usage))
                else:
                    _LOGGER.warning("✗ No usage data collected for property '%s'", property_name)
            
            _LOGGER.info("=" * 80)
            _LOGGER.info("DATA COLLECTION SUMMARY:")
            _LOGGER.info("Total properties processed: %d", len(self._properties))
            _LOGGER.info("Properties matched: %d", matched_properties)
            _LOGGER.info("Properties skipped: %d", skipped_properties)
            _LOGGER.info("Properties with usage data: %d", len(usage_data))
            _LOGGER.info("=" * 80)
            
            if not usage_data:
                available_ids = [str(p.get('id')) for p in self._properties]
                error_msg = (
                    f"No usage data retrieved for any configured services. "
                    f"Processed {len(self._properties)} properties, "
                    f"matched {matched_properties}, skipped {skipped_properties}. "
                    f"Selected accounts: {self.selected_accounts}, "
                    f"Available property IDs: {available_ids}"
                )
                _LOGGER.error(error_msg)
                raise UpdateFailed(error_msg)
            
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
    
    async def _bulk_update_data(self) -> Dict[str, Any]:
        """Handle bulk data updates for multiple accounts efficiently."""
        try:
            # Ensure authentication
            if not self.api._access_token:
                await self.api.authenticate(self.username, self.password, self.client_id)
            
            # Get base data if needed
            if not self._customer_data:
                raw_customer_data = await self.api.get_customer_data()
                self._customer_data = validate_customer_data(raw_customer_data)
                
                raw_properties = await self.api.get_properties()
                self._properties = validate_properties_data(raw_properties)
            
            # Use bulk processor for multiple accounts
            usage_data = await self._data_processor.batch_process_properties(
                {prop["id"]: {"property": prop, "services": {}} for prop in self._properties if prop["id"] in self.selected_accounts},
                self.selected_accounts,
                self.services
            )
            
            # Fetch actual usage data concurrently
            usage_tasks = []
            for property_data in self._properties:
                property_id = property_data.get("id")
                if property_id not in self.selected_accounts:
                    continue
                
                task = asyncio.create_task(
                    self._fetch_property_usage(property_data),
                    name=f"fetch_usage_{property_id}"
                )
                usage_tasks.append((property_id, task))
            
            # Wait for all tasks with error handling
            final_usage_data = {}
            for property_id, task in usage_tasks:
                try:
                    property_usage = await task
                    if property_usage:
                        final_usage_data[property_id] = property_usage
                except Exception as err:
                    _LOGGER.error("Failed to fetch usage for property %s: %s", property_id, err)
                    continue
            
            if not final_usage_data:
                raise UpdateFailed("No usage data retrieved for any configured services")
            
            return {
                "customer": self._customer_data,
                "properties": self._properties,
                "usage_data": final_usage_data,
                "last_update": datetime.now().isoformat(),
            }
            
        except Exception as err:
            await self._error_recovery.async_handle_error(
                err, ErrorType.COORDINATOR_UPDATE, {"coordinator": self}
            )
            raise
    
    async def _fetch_property_usage(self, property_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch usage data for a single property."""
        property_id = property_data.get("id")
        property_services = property_data.get("services", [])
        property_usage = {}
        
        for service in property_services:
            service_type = service.get("type")
            consumer_number = service.get("consumer_number")
            
            if not consumer_number or service_type not in self.services:
                continue
            
            if not service.get("active", True):
                continue
            
            try:
                # Get usage data for the last 30 days
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                raw_usage = await self.api.get_usage_data(
                    consumer_number, start_date, end_date
                )
                
                validated_usage = validate_usage_data(raw_usage)
                
                property_usage[service_type] = {
                    "consumer_number": consumer_number,
                    "usage_data": validated_usage,
                    "last_updated": end_date.isoformat(),
                }
                
            except Exception as err:
                await self._error_recovery.async_handle_error(
                    err, ErrorType.API_DATA_INVALID, 
                    {"property_id": property_id, "service_type": service_type}
                )
                continue
        
        if property_usage:
            return {
                "property": property_data,
                "services": property_usage,
            }
        
        return None
    
    async def _fetch_usage_data_optimized(self) -> Dict[str, Any]:
        """Fetch usage data with performance optimizations."""
        usage_data = {}
        
        # Use data processor for optimized calculations
        for property_data in self._properties:
            property_id = property_data.get("id")
            if property_id not in self.selected_accounts:
                continue
            
            property_usage = await self._fetch_property_usage(property_data)
            if property_usage:
                usage_data[property_id] = property_usage
        
        return usage_data
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for the coordinator."""
        return self._performance_monitor.get_performance_stats()
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error recovery statistics."""
        return self._error_recovery.get_error_statistics()

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

    def get_service_metadata(self, property_id: str, service_type: str) -> Optional[Dict[str, Any]]:
        """Get service metadata (NMI, meter type, solar, etc.) for a property and service."""
        property_data = self.get_property_data(property_id)
        if not property_data:
            return None
        
        property_info = property_data.get("property", {})
        services = property_info.get("services", [])
        
        service_metadata = next(
            (s for s in services if s.get("type") == service_type),
            None
        )
        
        return service_metadata

    def get_latest_import_usage(self, property_id: str, service_type: str) -> Optional[float]:
        """Get the most recent daily import usage."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        return usage_data[-1].get("import_usage", 0.0)

    def get_latest_export_usage(self, property_id: str, service_type: str) -> Optional[float]:
        """Get the most recent daily export usage."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        return usage_data[-1].get("export_usage", 0.0)

    def get_total_import_usage(self, property_id: str, service_type: str) -> Optional[float]:
        """Get total import usage over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("import_usage", 0) for entry in usage_data)

    def get_total_export_usage(self, property_id: str, service_type: str) -> Optional[float]:
        """Get total export usage over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("export_usage", 0) for entry in usage_data)

    def get_period_import_usage(self, property_id: str, service_type: str, period: str) -> Optional[float]:
        """Get total import usage for specific time period (PEAK/OFFPEAK/SHOULDER)."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        field_name = f"{period.lower()}_import_usage"
        return sum(entry.get(field_name, 0) for entry in usage_data)

    def get_period_export_usage(self, property_id: str, service_type: str, period: str) -> Optional[float]:
        """Get total export usage for specific time period (PEAK/OFFPEAK/SHOULDER)."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        field_name = f"{period.lower()}_export_usage"
        return sum(entry.get(field_name, 0) for entry in usage_data)

    def get_total_import_cost(self, property_id: str, service_type: str) -> Optional[float]:
        """Get total import cost over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("import_cost", 0) for entry in usage_data)

    def get_total_export_credit(self, property_id: str, service_type: str) -> Optional[float]:
        """Get total export credit over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("export_credit", 0) for entry in usage_data)

    def get_net_total_cost(self, property_id: str, service_type: str) -> Optional[float]:
        """Get net total cost (import - export) over period."""
        import_cost = self.get_total_import_cost(property_id, service_type)
        export_credit = self.get_total_export_credit(property_id, service_type)
        
        if import_cost is None or export_credit is None:
            return None
        
        return import_cost - export_credit

    def get_max_demand_data(self, property_id: str, service_type: str) -> Optional[Dict[str, Any]]:
        """Get maximum demand data (kW and timestamp)."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        max_demand_kw = 0.0
        max_demand_time = None
        max_demand_date = None
        
        for entry in usage_data:
            demand = entry.get("max_demand_kw", 0.0)
            if demand > max_demand_kw:
                max_demand_kw = demand
                max_demand_time = entry.get("max_demand_time")
                max_demand_date = entry.get("date")
        
        return {
            "max_demand_kw": max_demand_kw,
            "max_demand_time": max_demand_time,
            "max_demand_date": max_demand_date
        }

    def get_total_carbon_emission(self, property_id: str, service_type: str) -> Optional[float]:
        """Get total carbon emissions over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("carbon_emission_tonne", 0) for entry in usage_data)