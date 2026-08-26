"""DataUpdateCoordinator for Red Energy."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RedEnergyAPI, RedEnergyAPIError, RedEnergyAuthError
from .cl2_inference import infer_cl2_interval, resolve_rate_roles
from .data_validation import (
    DataValidationError,
    validate_customer_data,
    validate_properties_data,
    validate_usage_data,
)
from .error_recovery import RedEnergyErrorRecoverySystem, ErrorType
from .performance import PerformanceMonitor, DataProcessor
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GST_MULTIPLIER,
)

_LOGGER = logging.getLogger(__name__)


class RedEnergyDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Red Energy data."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        selected_accounts: list[str],
        services: list[str],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.username = username
        self.password = password
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

        self._customer_data: dict[str, Any] | None = None
        self._properties: list[dict[str, Any]] = []
        # Track last calendar day we refreshed metadata (customer/properties)
        self._last_metadata_refresh_date: date | None = None

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    def _get_billing_period_start(self, service: dict[str, Any]) -> datetime:
        """Resolve the current billing period's start date.

        lastBillDate is the final day of the *previous* billing period, so
        the new period's usage starts the following day - otherwise that
        day's usage/cost is double-counted across both periods. Falls back
        to a 30-day window when lastBillDate is missing, invalid, in the
        future, or implausibly old (>90 days).
        """
        end_date = datetime.now()
        start_date = None

        last_bill_date = service.get("lastBillDate")
        if last_bill_date:
            try:
                start_date = datetime.strptime(last_bill_date, "%Y-%m-%d") + timedelta(days=1)

                if start_date > end_date:
                    _LOGGER.warning("lastBillDate %s is in the future, falling back to 30-day period", last_bill_date)
                    start_date = None
                elif (end_date - start_date).days > 90:
                    _LOGGER.warning("lastBillDate %s is >90 days old (%d days), this may be a long billing period",
                                  last_bill_date, (end_date - start_date).days)
                else:
                    _LOGGER.info("Using billing period: %s to %s (%d days)",
                               start_date.strftime('%Y-%m-%d'),
                               end_date.strftime('%Y-%m-%d'),
                               (end_date - start_date).days)

            except (ValueError, TypeError) as err:
                _LOGGER.warning("Invalid lastBillDate format '%s': %s, falling back to 30-day period", last_bill_date, err)
                start_date = None

        if start_date is None:
            start_date = end_date - timedelta(days=30)
            _LOGGER.info("Using 30-day fallback period: %s to %s",
                       start_date.strftime('%Y-%m-%d'),
                       end_date.strftime('%Y-%m-%d'))

        return start_date

    def _get_usage_period_dates(self, service: dict[str, Any]) -> tuple[datetime, datetime]:
        end_date = datetime.now()
        start_date = self._get_billing_period_start(service)
        return start_date, end_date

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Red Energy API."""
        try:
            # Ensure we're authenticated
            if not self.api._access_token:
                _LOGGER.info("Authenticating with Red Energy API")
                await self.api.authenticate(self.username, self.password)
            
            # Refresh metadata (customer/properties) once per calendar day or on first run
            if self._should_refresh_metadata_today() or not self._customer_data:
                await self._async_refresh_metadata()
            
            # Log selected accounts configuration
            _LOGGER.debug("=" * 80)
            _LOGGER.debug("COORDINATOR CONFIGURATION:")
            _LOGGER.debug("Selected accounts: %s (type: %s)", self.selected_accounts, type(self.selected_accounts))
            _LOGGER.debug("Configured services: %s", self.services)
            _LOGGER.debug("Total properties available: %d", len(self._properties))
            property_ids = [str(p.get("id")) for p in self._properties]
            _LOGGER.debug("Available property IDs: %s (types: %s)", property_ids, [type(pid) for pid in property_ids])
            _LOGGER.debug("Selected accounts types: %s", [type(sa) for sa in self.selected_accounts])
            _LOGGER.debug("Property ID types: %s", [type(p.get("id")) for p in self._properties])
            _LOGGER.debug("=" * 80)
            
            # Fetch usage data for selected accounts and services
            usage_data = {}
            
            matched_properties = 0
            skipped_properties = 0
            
            for property_data in self._properties:
                property_id = property_data.get("id")
                property_name = property_data.get("name", "Unknown")
                
                _LOGGER.debug("Processing property: ID='%s' (type: %s), Name='%s'", property_id, type(property_id), property_name)
                
                # Convert to string for comparison since selected_accounts are strings
                property_id_str = str(property_id)
                if property_id_str not in self.selected_accounts:
                    _LOGGER.info(
                        "Property '%s' (ID: %s) not in selected_accounts %s - SKIPPING",
                        property_name, property_id, self.selected_accounts
                    )
                    skipped_properties += 1
                    continue
                
                matched_properties += 1
                _LOGGER.debug("Property '%s' (ID: %s) MATCHED - fetching usage data", property_name, property_id_str)
                
                property_services = property_data.get("services", [])
                _LOGGER.debug("  Property has %d services: %s", 
                            len(property_services),
                            [s.get("type") for s in property_services])
                property_usage = {}
                
                for service in property_services:
                    service_type = service.get("type")
                    consumer_number = service.get("consumer_number")
                    is_active = service.get("active", True)
                    
                    _LOGGER.debug("  Processing service: type=%s, consumer_number=%s, active=%s", 
                                service_type, consumer_number, is_active)
                    
                    if not consumer_number:
                        _LOGGER.warning("    Service %s has no consumer_number - SKIPPING", service_type)
                        continue
                    
                    if service_type not in self.services:
                        _LOGGER.debug("    Service %s not in configured services %s - SKIPPING", 
                                    service_type, self.services)
                        continue
                    
                    if not is_active:
                        _LOGGER.debug("    Service %s is inactive - SKIPPING", service_type)
                        continue
                    
                    _LOGGER.debug("    Service %s MATCHED - fetching usage data", service_type)
                    
                    try:
                        start_date, end_date = self._get_usage_period_dates(service)
                        
                        _LOGGER.debug("    Calling API get_usage_data: consumer=%s, from=%s, to=%s",
                                    consumer_number, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                        
                        raw_usage = await self.api.get_usage_data(
                            consumer_number, start_date, end_date
                        )
                        
                        _LOGGER.debug("    Raw usage API response type: %s", type(raw_usage))
                        _LOGGER.debug("    Raw usage API response: %s", raw_usage)
                        
                        # Check if API returned an error response
                        if isinstance(raw_usage, dict) and raw_usage.get("error"):
                            error_message = raw_usage.get("error_message", "Unknown error")
                            # BASIC/manual-read gas meters don't have half-hourly
                            # interval usage - the API returns this as an error
                            # for every request, which is expected, not a failure.
                            is_no_interval_usage = "does not have interval usages" in error_message
                            log_method = _LOGGER.info if is_no_interval_usage else _LOGGER.warning
                            log_method(
                                "API returned error for %s service (consumer %s): %s - %s. "
                                "Skipping this service but continuing with others.",
                                service_type,
                                consumer_number,
                                error_message,
                                raw_usage.get("error_details", "No details")
                            )
                            # Skip this service but continue with others
                            continue
                        
                        # Validate usage data
                        validated_usage = validate_usage_data(raw_usage)
                        
                        period_days = (end_date - start_date).days
                        
                        property_usage[service_type] = {
                            "consumer_number": consumer_number,
                            "usage_data": validated_usage,
                            "last_updated": end_date.isoformat(),
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "period_days": period_days,
                        }
                        
                        _LOGGER.info(
                            "    Successfully fetched %s usage for property %s: %s total usage, %s total cost",
                            service_type,
                            property_id,
                            validated_usage.get("total_usage", 0),
                            validated_usage.get("total_cost", 0)
                        )
                        
                    except (RedEnergyAPIError, DataValidationError) as err:
                        _LOGGER.error(
                            "    Failed to fetch/validate %s usage for property %s: %s",
                            service_type,
                            property_id,
                            err,
                            exc_info=True
                        )
                        # Don't fail the entire update for one service error
                        continue
                
                # Always record the property, even if no service returned usage
                # data (e.g. a BASIC/manual-read gas meter, which never has
                # interval usage). Its metadata (NMI, balance, bill dates, etc.)
                # is still valid, so the device and metadata-only sensors must
                # still be created - only usage-dependent sensors go unavailable.
                usage_data[property_id_str] = {
                    "property": property_data,
                    "services": property_usage,
                }
                if property_usage:
                    _LOGGER.info("Successfully collected usage data for property '%s' with %d services",
                                property_name, len(property_usage))
                else:
                    _LOGGER.info(
                        "No usage data collected for property '%s' - metadata-only sensors will still be created",
                        property_name,
                    )
            
            _LOGGER.debug("=" * 80)
            _LOGGER.debug("DATA COLLECTION SUMMARY:")
            _LOGGER.debug("Total properties processed: %d", len(self._properties))
            _LOGGER.debug("Properties matched: %d", matched_properties)
            _LOGGER.debug("Properties skipped: %d", skipped_properties)
            _LOGGER.debug("Properties with usage data: %d", len(usage_data))
            _LOGGER.debug("=" * 80)
            
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
                _LOGGER.error("DEBUG: selected_accounts types: %s", [type(sa) for sa in self.selected_accounts])
                _LOGGER.error("DEBUG: property ID types: %s", [type(p.get('id')) for p in self._properties])
                _LOGGER.error("DEBUG: string comparison test: %s", [str(sa) in available_ids for sa in self.selected_accounts])
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
    
    def _should_refresh_metadata_today(self) -> bool:
        """Return True if we haven't refreshed metadata today (calendar day)."""
        today = datetime.now(timezone.utc).date()
        if self._last_metadata_refresh_date is None:
            return True
        return self._last_metadata_refresh_date != today
    
    async def _async_refresh_metadata(self) -> None:
        """Refresh customer and properties metadata and update last refresh date."""
        _LOGGER.info("Refreshing Red Energy metadata (customer and properties)")
        raw_customer_data = await self.api.get_customer_data()
        _LOGGER.debug("=" * 80)
        _LOGGER.debug("RAW CUSTOMER API RESPONSE:")
        _LOGGER.debug("Type: %s", type(raw_customer_data))
        _LOGGER.debug("Data: %s", raw_customer_data)
        _LOGGER.debug("=" * 80)
        self._customer_data = validate_customer_data(raw_customer_data)
        _LOGGER.info("Validated customer data - ID: %s, Name: %s", 
                    self._customer_data.get("id"), self._customer_data.get("name"))

        raw_properties = await self.api.get_properties()
        _LOGGER.debug("=" * 80)
        _LOGGER.debug("RAW PROPERTIES API RESPONSE:")
        _LOGGER.debug("Type: %s", type(raw_properties))
        _LOGGER.debug("Count: %d", len(raw_properties) if isinstance(raw_properties, list) else 0)
        _LOGGER.debug("Data: %s", raw_properties)
        _LOGGER.debug("=" * 80)
        self._properties = validate_properties_data(raw_properties)
        _LOGGER.info("Validated %d properties", len(self._properties))
        for prop in self._properties:
            _LOGGER.debug("  - Property ID: %s, Name: %s, Services: %s", 
                        prop.get("id"), prop.get("name"), 
                        [s.get("type") for s in prop.get("services", [])])
        self._last_metadata_refresh_date = datetime.now(timezone.utc).date()

    async def async_refresh_metadata_and_usage(self) -> None:
        """Manually trigger metadata refresh and then request full data refresh."""
        await self._async_refresh_metadata()
        await self.async_request_refresh()
    
    async def _bulk_update_data(self) -> dict[str, Any]:
        """Handle bulk data updates for multiple accounts efficiently."""
        try:
            # Ensure authentication
            if not self.api._access_token:
                await self.api.authenticate(self.username, self.password)
            
            # Get base data if needed
            if not self._customer_data:
                raw_customer_data = await self.api.get_customer_data()
                self._customer_data = validate_customer_data(raw_customer_data)
                
                raw_properties = await self.api.get_properties()
                self._properties = validate_properties_data(raw_properties)
            
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
    
    async def _fetch_property_usage(self, property_data: dict[str, Any]) -> dict[str, Any] | None:
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
                start_date, end_date = self._get_usage_period_dates(service)
                
                raw_usage = await self.api.get_usage_data(
                    consumer_number, start_date, end_date
                )
                
                # Check if API returned an error response
                if isinstance(raw_usage, dict) and raw_usage.get("error"):
                    error_message = raw_usage.get("error_message", "Unknown error")
                    # BASIC/manual-read gas meters don't have half-hourly
                    # interval usage - the API returns this as an error for
                    # every request, which is expected, not a failure.
                    is_no_interval_usage = "does not have interval usages" in error_message
                    log_method = _LOGGER.info if is_no_interval_usage else _LOGGER.warning
                    log_method(
                        "API returned error for %s service (consumer %s): %s - %s. "
                        "Skipping this service but continuing with others.",
                        service_type,
                        consumer_number,
                        error_message,
                        raw_usage.get("error_details", "No details")
                    )
                    # Skip this service but continue with others
                    continue
                
                validated_usage = validate_usage_data(raw_usage)
                
                period_days = (end_date - start_date).days
                
                property_usage[service_type] = {
                    "consumer_number": consumer_number,
                    "usage_data": validated_usage,
                    "last_updated": end_date.isoformat(),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "period_days": period_days,
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
    
    async def _fetch_usage_data_optimized(self) -> dict[str, Any]:
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
    
    def get_performance_metrics(self) -> dict[str, Any]:
        """Get performance metrics for the coordinator."""
        return self._performance_monitor.get_performance_stats()
    
    def get_error_statistics(self) -> dict[str, Any]:
        """Get error recovery statistics."""
        return self._error_recovery.get_error_statistics()

    async def async_refresh_credentials(
        self, username: str, password: str
    ) -> bool:
        """Refresh credentials and test authentication."""
        try:
            # Update credentials
            self.username = username
            self.password = password
            
            # Clear cached auth token to force re-authentication
            self.api._access_token = None
            self.api._refresh_token = None
            self.api._token_expires = None
            
            # Test new credentials
            success = await self.api.authenticate(username, password)
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
        self, selected_accounts: list[str], services: list[str]
    ) -> None:
        """Update account and service selection."""
        self.selected_accounts = selected_accounts
        self.services = services
        
        # Trigger data refresh with new selection
        await self.async_refresh()

    def get_property_data(self, property_id: str) -> dict[str, Any] | None:
        """Get cached property data by ID."""
        if not self.data or "usage_data" not in self.data:
            return None
        
        return self.data["usage_data"].get(str(property_id))

    def get_service_usage(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Get usage data for a specific property and service."""
        property_data = self.get_property_data(property_id)
        if not property_data:
            return None
        
        return property_data.get("services", {}).get(service_type)

    def get_latest_usage(self, property_id: str, service_type: str) -> float | None:
        """Get the most recent usage value for a property and service."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        # Return the latest day's usage
        return usage_data[-1].get("usage", 0.0)

    def get_total_cost(self, property_id: str, service_type: str) -> float | None:
        """Get the total (GST-exclusive, net of export credit) cost for a property and service.

        Delegates to get_net_total_cost, which sums import_cost/export_credit
        directly, rather than reading the pre-aggregated usage_data["total_cost"]
        field - both are ex-GST on the import side, but computing it here
        keeps this and get_net_total_cost as a single source of truth rather
        than two aggregations that could drift apart.
        """
        return self.get_net_total_cost(property_id, service_type)

    def get_total_usage(self, property_id: str, service_type: str) -> float | None:
        """Get the total usage for a property and service."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        return service_data["usage_data"].get("total_usage", 0.0)

    def get_service_metadata(self, property_id: str, service_type: str) -> dict[str, Any] | None:
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

    def get_service_rates(self, property_id: str, service_type: str) -> list[dict[str, Any]]:
        """Get the validated tariff rates list for a property and service."""
        metadata = self.get_service_metadata(property_id, service_type)
        if not metadata:
            return []

        return metadata.get("rates", [])

    def _find_service_charge_rate(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Find the daily service/supply charge rate for a property and service.

        Identified by a bare "day" unit (case-insensitive) - real payloads
        use rate type "F" for both this charge (unit "Day") and demand
        charges (unit "KW/day"), so type alone can't distinguish them and
        isn't used here; unit is compared case-insensitively since the API
        has been observed to send both "day" and "Day". If more than one
        rate matches, the first in list order is used.
        """
        rates = self.get_service_rates(property_id, service_type)
        return next(
            (r for r in rates if isinstance(r.get("unit"), str) and r["unit"].lower() == "day"),
            None,
        )

    def get_billing_period_service_charge(self, property_id: str, service_type: str) -> float | None:
        """Get the accumulated service charge from the billing period start
        through the latest completed usageDate, inclusive.

        Uses the latest completed usageDate as the period end - not
        datetime.now() - so a day with no confirmed usage data yet is
        never counted as a represented day.
        """
        rate = self._find_service_charge_rate(property_id, service_type)
        if rate is None:
            return None

        latest_usage_date_str = self.get_latest_usage_date(property_id, service_type)
        if not latest_usage_date_str:
            return None

        try:
            billing_period_end = datetime.strptime(latest_usage_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

        service_metadata = self.get_service_metadata(property_id, service_type) or {}
        billing_period_start = self._get_billing_period_start(service_metadata).date()

        if billing_period_end < billing_period_start:
            return None

        represented_day_count = (billing_period_end - billing_period_start).days + 1
        return rate["rate_incl_gst_dollars"] * represented_day_count

    def get_projected_charges(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Estimate the current billing cycle's total charge, GST-inclusive.

        Red Energy's API has no "projected charges" field (see issue #75) -
        this linearly extrapolates GST-inclusive net cost-to-date across the
        full billing cycle:

            net_cost_to_date / days_elapsed * days_in_cycle

        net_cost_to_date is (import_cost * GST_MULTIPLIER) - export_credit,
        computed here rather than via get_total_cost/get_net_total_cost -
        those are GST-exclusive (feed Current Period Import Cost/Net Cost,
        which disclose their ex-GST basis via a "gst_basis" attribute) -
        uplifting their already-net result would incorrectly inflate the
        export_credit component too, since it has no GST component itself.

        days_elapsed uses the latest completed usageDate as the period end
        (not datetime.now()) so a day with no confirmed usage yet is never
        counted, matching get_billing_period_service_charge. days_in_cycle
        requires nextBillDate - unlike billing_period_start, which falls
        back to a 30-day window, there's no sane fallback for the cycle's
        end date, so a missing/invalid/non-later nextBillDate returns None.

        Returns a dict with "projected_charges", "net_cost_to_date",
        "days_elapsed", and "days_in_cycle" so sensor attributes can be
        sourced from the same calculation rather than re-deriving it.
        """
        import_cost_ex_gst = self.get_total_import_cost(property_id, service_type)
        export_credit = self.get_total_export_credit(property_id, service_type)
        if import_cost_ex_gst is None or export_credit is None:
            return None
        net_cost_to_date = (import_cost_ex_gst * GST_MULTIPLIER) - export_credit

        latest_usage_date_str = self.get_latest_usage_date(property_id, service_type)
        if not latest_usage_date_str:
            return None

        try:
            billing_period_end = datetime.strptime(latest_usage_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

        service_metadata = self.get_service_metadata(property_id, service_type) or {}
        billing_period_start = self._get_billing_period_start(service_metadata).date()

        if billing_period_end < billing_period_start:
            return None

        days_elapsed = (billing_period_end - billing_period_start).days + 1

        next_bill_date_str = service_metadata.get("nextBillDate")
        if not next_bill_date_str:
            return None

        try:
            next_bill_date = datetime.strptime(next_bill_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

        # nextBillDate is an exclusive boundary - the first day of the *next*
        # cycle, not a chargeable day of this one - symmetric with lastBillDate
        # being excluded via the +1 day in billing_period_start above. Using
        # billing_period_start (not lastBillDate) as the cycle_days anchor
        # keeps both boundaries treated the same way (issue #70 follow-up).
        days_in_cycle = (next_bill_date - billing_period_start).days
        if days_in_cycle <= 0:
            return None

        return {
            "projected_charges": net_cost_to_date / days_elapsed * days_in_cycle,
            "net_cost_to_date": net_cost_to_date,
            "days_elapsed": days_elapsed,
            "days_in_cycle": days_in_cycle,
        }

    def get_estimated_current_period_charges(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Estimate the full billing cycle's total charge, energy + service charge (issue #77).

        get_projected_charges alone is energy-only (net usage cost), not a
        full bill estimate - it excludes the daily service/supply charge.
        This adds that charge, projected across the same days_in_cycle:

            estimated_charges = projected_net_cost + (service_charge_rate * days_in_cycle)

        Both terms are GST-inclusive (get_projected_charges computes its
        own GST-inclusive net_cost_to_date; rate_incl_gst_dollars already
        is), so no further GST adjustment is needed here.

        Returns None when there's no daily service-charge rate (some plans
        don't have one) or when the underlying net-cost projection itself
        is unavailable.
        """
        rate = self._find_service_charge_rate(property_id, service_type)
        if rate is None:
            return None

        projection = self.get_projected_charges(property_id, service_type)
        if projection is None:
            return None

        estimated_service_charge = rate["rate_incl_gst_dollars"] * projection["days_in_cycle"]

        return {
            "estimated_charges": projection["projected_charges"] + estimated_service_charge,
            "estimated_net_cost": projection["projected_charges"],
            "estimated_service_charge": estimated_service_charge,
            "days_in_cycle": projection["days_in_cycle"],
            "service_rate_incl_gst": rate["rate_incl_gst_dollars"],
        }

    def get_cl2_inference(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Aggregate CL2/TOU inference across a service's usage period.

        Returns None when there's no usage data, or when the account's plan
        rates don't unambiguously resolve all four roles - PEAK, OFFPEAK,
        SHOULDER, and CL2 (resolve_rate_roles() left one or more roles in
        "unresolved_roles") - most accounts have no controlled load, so
        this is the normal case for them, not an error.

        Uses the account's *current* plan rates for every interval in the
        period, including days earlier in the billing cycle - there is no
        historical rate-change data available anywhere in the API, so a
        mid-period rate change will skew inference for days before it. This
        is a known, documented limitation, not something this method can
        detect or correct for.
        """
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None

        daily_entries = service_data["usage_data"].get("usage_data", [])
        if not daily_entries:
            return None

        rates = self.get_service_rates(property_id, service_type)
        role_resolution = resolve_rate_roles(rates)
        if role_resolution["unresolved_roles"]:
            return None

        rates_incl_gst = role_resolution["rates_incl_gst"]
        cl2_rate_incl_gst = role_resolution["cl2_rate_incl_gst"]

        cl2_energy_kwh = 0.0
        corrected_peak_kwh = 0.0
        corrected_shoulder_kwh = 0.0
        corrected_offpeak_kwh = 0.0
        cl2_cost = 0.0
        reconstructed_import_cost = 0.0
        api_import_cost = 0.0
        accepted_interval_count = 0
        rejected_interval_count = 0
        rejection_reasons: dict[str, int] = {}

        for daily_entry in daily_entries:
            intervals = daily_entry.get("intervals", [])
            if not isinstance(intervals, list):
                continue

            for interval in intervals:
                result = infer_cl2_interval(interval, rates_incl_gst, cl2_rate_incl_gst)

                if not result["accepted"]:
                    rejected_interval_count += 1
                    reason = result["reason"] or "unknown"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    continue

                accepted_interval_count += 1
                cl2_energy_kwh += result["cl2_kwh"]
                cl2_cost += result["cl2_kwh"] * cl2_rate_incl_gst
                reconstructed_import_cost += result["reconstructed_cost"]
                api_import_cost += result["api_cost"]

                tariff_component = interval.get("tariff_component")
                if tariff_component == "PEAK":
                    corrected_peak_kwh += result["tou_kwh"]
                elif tariff_component == "SHOULDER":
                    corrected_shoulder_kwh += result["tou_kwh"]
                elif tariff_component == "OFFPEAK":
                    corrected_offpeak_kwh += result["tou_kwh"]

        return {
            "cl2_energy_kwh": round(cl2_energy_kwh, 3),
            "corrected_peak_kwh": round(corrected_peak_kwh, 3),
            "corrected_shoulder_kwh": round(corrected_shoulder_kwh, 3),
            "corrected_offpeak_kwh": round(corrected_offpeak_kwh, 3),
            "cl2_cost": round(cl2_cost, 2),
            "reconstructed_import_cost": round(reconstructed_import_cost, 2),
            "api_import_cost": round(api_import_cost, 2),
            "reconciliation_difference": round(reconstructed_import_cost - api_import_cost, 2),
            "accepted_interval_count": accepted_interval_count,
            "rejected_interval_count": rejected_interval_count,
            "rejection_reasons": rejection_reasons,
            "rates_used": {**rates_incl_gst, "CL2": cl2_rate_incl_gst},
            "rates_source": "current plan rates (no historical rate data available)",
        }

    def _get_latest_usage_entry(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Return the usage_data entry with the latest usageDate.

        Selects by max date rather than assuming the API returns entries
        in order, so results stay correct if the API ever returns them
        out of order.
        """
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None

        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None

        dated_entries = [entry for entry in usage_data if entry.get("date")]
        if not dated_entries:
            return usage_data[-1]

        return max(dated_entries, key=lambda entry: entry["date"])

    def get_latest_usage_date(self, property_id: str, service_type: str) -> str | None:
        """Get the usageDate of the most recent daily usage entry."""
        entry = self._get_latest_usage_entry(property_id, service_type)
        return entry.get("date") if entry else None

    def get_latest_import_usage(self, property_id: str, service_type: str) -> float | None:
        """Get the most recent daily import usage."""
        entry = self._get_latest_usage_entry(property_id, service_type)
        return entry.get("import_usage", 0.0) if entry else None

    def get_latest_export_usage(self, property_id: str, service_type: str) -> float | None:
        """Get the most recent daily export usage."""
        entry = self._get_latest_usage_entry(property_id, service_type)
        return entry.get("export_usage", 0.0) if entry else None

    def get_total_import_usage(self, property_id: str, service_type: str) -> float | None:
        """Get total import usage over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("import_usage", 0) for entry in usage_data)

    def get_total_export_usage(self, property_id: str, service_type: str) -> float | None:
        """Get total export usage over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("export_usage", 0) for entry in usage_data)

    def get_period_import_usage(self, property_id: str, service_type: str, period: str) -> float | None:
        """Get total import usage for specific time period (PEAK/OFFPEAK/SHOULDER)."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        field_name = f"{period.lower()}_import_usage"
        return sum(entry.get(field_name, 0) for entry in usage_data)

    def get_period_export_usage(self, property_id: str, service_type: str, period: str) -> float | None:
        """Get total export usage for specific time period (PEAK/OFFPEAK/SHOULDER)."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        field_name = f"{period.lower()}_export_usage"
        return sum(entry.get(field_name, 0) for entry in usage_data)

    def get_total_import_cost(self, property_id: str, service_type: str) -> float | None:
        """Get total import cost over period, GST-exclusive.

        entry["import_cost"] is sourced from consumptionDollar, which Red
        Energy's API returns ex-GST (see api.py's _normalize_usage_entry
        docstring) and is returned here as-is. Feeds Current Period Import
        Cost / Current Period Net Cost, which are ex-GST and disclose this
        via a "gst_basis" attribute. get_projected_charges applies its own
        GST uplift for the forward-looking Projected Net Cost/Charges
        sensors, which are GST-inclusive.
        """
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None

        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("import_cost", 0) for entry in usage_data)

    def get_total_export_credit(self, property_id: str, service_type: str) -> float | None:
        """Get total export credit over period.

        Not GST-uplifted: generationDollar (FIT/solar export credit) is not
        a GST-bearing supply, so entry["export_credit"] has no GST component
        to add or strip.
        """
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None

        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("export_credit", 0) for entry in usage_data)

    def get_net_total_cost(self, property_id: str, service_type: str) -> float | None:
        """Get net total cost (GST-exclusive import - export credit) over period."""
        import_cost = self.get_total_import_cost(property_id, service_type)
        export_credit = self.get_total_export_credit(property_id, service_type)

        if import_cost is None or export_credit is None:
            return None

        return import_cost - export_credit

    def get_max_demand_data(self, property_id: str, service_type: str) -> dict[str, Any] | None:
        """Get maximum demand data (kW and timestamp)."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        if not usage_data:
            return None
        
        max_demand_kw = None
        max_demand_time = None
        max_demand_date = None

        for entry in usage_data:
            demand = entry.get("max_demand_kw")
            if demand is None:
                continue
            if max_demand_kw is None or demand > max_demand_kw:
                max_demand_kw = demand
                max_demand_time = entry.get("max_demand_time")
                max_demand_date = entry.get("date")

        if max_demand_kw is None:
            return None

        return {
            "max_demand_kw": max_demand_kw,
            "max_demand_time": max_demand_time,
            "max_demand_date": max_demand_date
        }

    def get_total_carbon_emission(self, property_id: str, service_type: str) -> float | None:
        """Get total carbon emissions over period."""
        service_data = self.get_service_usage(property_id, service_type)
        if not service_data or "usage_data" not in service_data:
            return None
        
        usage_data = service_data["usage_data"].get("usage_data", [])
        return sum(entry.get("carbon_emission_tonne", 0) for entry in usage_data)

    def get_latest_import_cost(self, property_id: str, service_type: str) -> float | None:
        """Get the most recent daily import cost, GST-exclusive (see get_total_import_cost)."""
        entry = self._get_latest_usage_entry(property_id, service_type)
        return entry.get("import_cost", 0.0) if entry else None

    def get_latest_export_credit(self, property_id: str, service_type: str) -> float | None:
        """Get the most recent daily export credit."""
        entry = self._get_latest_usage_entry(property_id, service_type)
        return entry.get("export_credit", 0.0) if entry else None
