"""Red Energy API client for Home Assistant integration."""
from __future__ import annotations

import json
import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, parse_qs, urlparse
import hashlib
import base64

import aiohttp
import async_timeout

from .const import API_TIMEOUT, CLIENT_ID

_LOGGER = logging.getLogger(__name__)

class RedEnergyAPIError(Exception):
    """Base Red Energy API exception."""


class RedEnergyAuthError(RedEnergyAPIError):
    """Red Energy authentication exception."""


class RedEnergyAPI:
    """Red Energy API client."""
    
    DISCOVERY_URL = "https://login.redenergy.com.au/oauth2/default/.well-known/openid-configuration"
    REDIRECT_URI = "au.com.redenergy://callback"
    BASE_API_URL = "https://selfservice.services.retail.energy/v1"
    OKTA_AUTH_URL = "https://redenergy.okta.com/api/v1/authn"
    
    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._session = session
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._logged_entry_mapping: bool = False
        
    async def authenticate(self, username: str, password: str) -> bool:
        """Authenticate with Red Energy using Okta session token and OAuth2 PKCE flow."""
        try:
            _LOGGER.debug("Starting Red Energy authentication")
            
            # Step 1: Get Okta session token
            session_token, session_expires = await self._get_session_token(username, password)
            _LOGGER.debug("Obtained session token, expires: %s", session_expires)
            
            # Step 2: Get OAuth2 endpoints from discovery URL
            discovery_data = await self._get_discovery_data()
            auth_endpoint = discovery_data["authorization_endpoint"]
            token_endpoint = discovery_data["token_endpoint"]
            
            # Step 3: Generate PKCE parameters
            code_verifier = self._generate_code_verifier()
            code_challenge = self._generate_code_challenge(code_verifier)
            _LOGGER.debug("Generated PKCE - Verifier: %s, Challenge: %s", code_verifier, code_challenge)
            
            # Step 4: Get authorization code using session token
            auth_code = await self._get_authorization_code(
                auth_endpoint, session_token, CLIENT_ID, code_challenge
            )
            
            # Step 5: Exchange authorization code for access/refresh tokens
            await self._exchange_code_for_tokens(
                token_endpoint, auth_code, CLIENT_ID, code_verifier
            )
            
            _LOGGER.debug("Red Energy authentication successful - access token acquired, expires: %s", self._token_expires)
            return True
            
        except RedEnergyAuthError:
            # Re-raise RedEnergyAuthError as-is (already logged above)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error during authentication: %s", err, exc_info=True)
            raise RedEnergyAuthError(f"Authentication failed due to unexpected error: {err}") from err
    
    async def _get_discovery_data(self) -> Dict[str, Any]:
        """Get OAuth2 discovery data."""
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.get(self.DISCOVERY_URL) as response:
                response.raise_for_status()
                return await response.json()
    
    def _generate_code_verifier(self) -> str:
        """Generate PKCE code verifier."""
        # Generate 48 character random string matching authlib's generate_token(48)
        # Uses URL-safe characters as per RFC 7636: [a-zA-Z0-9\-\.\_\~]
        alphabet = string.ascii_letters + string.digits + '-._~'
        return ''.join(secrets.choice(alphabet) for _ in range(48))
    
    def _generate_code_challenge(self, verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')
    
    async def _get_session_token(self, username: str, password: str) -> tuple[str, str]:
        """Get Okta session token using username/password."""
        payload = {
            "username": username,
            "password": password,
            "options": {
                "warnBeforePasswordExpired": False,
                "multiOptionalFactorEnroll": False
            }
        }
        
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.post(self.OKTA_AUTH_URL, json=payload) as response:
                if response.status != 200:
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get("errorSummary", "Authentication failed")
                        error_code = error_data.get("errorCode", "Unknown")
                        _LOGGER.error(
                            "Okta authentication failed - HTTP %s: %s (Code: %s). "
                            "This usually means invalid username/password. Full error: %s",
                            response.status, error_msg, error_code, error_data
                        )
                        raise RedEnergyAuthError(f"Okta authentication failed: {error_msg} (Code: {error_code})")
                    except Exception as parse_err:
                        response_text = await response.text()
                        _LOGGER.error(
                            "Okta authentication failed - HTTP %s. Unable to parse error response: %s. Raw response: %s",
                            response.status, parse_err, response_text[:500]
                        )
                        raise RedEnergyAuthError(f"Okta authentication failed with HTTP {response.status}")
                
                data = await response.json()
                status = data.get("status")
                if status != "SUCCESS":
                    _LOGGER.error(
                        "Okta authentication failed - Status: %s. Full response: %s. "
                        "This may indicate MFA required, account locked, or other Okta-specific issues.",
                        status, data
                    )
                    raise RedEnergyAuthError(f"Authentication failed - Status: {status}")
                
                return data["sessionToken"], data["expiresAt"]
    
    async def _get_authorization_code(
        self, 
        auth_endpoint: str, 
        session_token: str,
        client_id: str,
        code_challenge: str
    ) -> str:
        """Get authorization code using session token and PKCE challenge."""
        # Generate state and nonce for OAuth2 security (matching working project)
        state = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        _LOGGER.debug("Generated OAuth2 - State: %s, Nonce: %s", state, nonce)
        
        # Build authorization URL exactly like the working project
        base_params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': self.REDIRECT_URI,
            'scope': 'openid profile offline_access',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        extra_params = {
            'sessionToken': session_token,
            'state': state,
            'nonce': nonce
        }
        
        # Combine all parameters like OAuth2Session.create_authorization_url() would
        all_params = {**base_params, **extra_params}
        auth_url = f"{auth_endpoint}?{urlencode(all_params)}"
        _LOGGER.debug("Authorization URL: %s", auth_url)
        
        # Make request to authorization endpoint - this should redirect
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.get(auth_url, allow_redirects=False) as response:
                _LOGGER.debug("Authorization response status: %s, headers: %s", response.status, dict(response.headers))
                
                location = response.headers.get("Location", "")
                if not location:
                    response_text = await response.text()
                    _LOGGER.error(
                        "No redirect location found in authorization response. "
                        "Status: %s, Response: %s. This may indicate invalid client_id or session_token.",
                        response.status, response_text[:500]
                    )
                    raise RedEnergyAuthError("No redirect location found in authorization response")
                
                # Parse authorization code from redirect URL
                parsed_url = urlparse(location)
                query_params = parse_qs(parsed_url.query)
                auth_code = query_params.get("code", [None])[0]
                _LOGGER.debug("Authorization redirect - Location: %s, Code: %s", location, auth_code)
                
                if not auth_code:
                    error = query_params.get("error", ["Unknown error"])[0]
                    error_description = query_params.get("error_description", [""])[0]
                    _LOGGER.error(
                        "Authorization failed - Error: %s, Description: %s, Full params: %s. "
                        "This may indicate invalid client_id, expired session_token, or OAuth2 configuration issues.",
                        error, error_description, query_params
                    )
                    raise RedEnergyAuthError(f"Authorization failed: {error} - {error_description}")
                
                return auth_code
    
    async def _exchange_code_for_tokens(
        self,
        token_endpoint: str,
        auth_code: str,
        client_id: str,
        code_verifier: str
    ) -> None:
        """Exchange authorization code for access and refresh tokens."""
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': client_id,
            'code': auth_code,
            'redirect_uri': self.REDIRECT_URI,
            'code_verifier': code_verifier,
        }
        
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.post(
                token_endpoint,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            ) as response:
                if response.status != 200:
                    try:
                        error_data = await response.json()
                        _LOGGER.error(
                            "Token exchange failed - HTTP %s: %s. Full error: %s. "
                            "This may indicate invalid authorization code, client_id, or code_verifier.",
                            response.status, error_data.get('error_description', 'Unknown error'), error_data
                        )
                    except Exception:
                        response_text = await response.text()
                        _LOGGER.error(
                            "Token exchange failed - HTTP %s. Raw response: %s",
                            response.status, response_text[:500]
                        )
                    response.raise_for_status()
                
                tokens = await response.json()
                _LOGGER.debug("Token exchange successful, received tokens with expires_in: %s", tokens.get('expires_in'))
                
                self._access_token = tokens['access_token']
                self._refresh_token = tokens.get('refresh_token')
                expires_in = tokens.get('expires_in', 3600)
                self._token_expires = datetime.now() + timedelta(seconds=expires_in)
    
    async def test_credentials(self, username: str, password: str) -> bool:
        """Test if credentials are valid by attempting full authentication."""
        try:
            _LOGGER.debug("Testing credentials for user: %s", username)
            # Perform full authentication to get access token
            return await self.authenticate(username, password)
        except RedEnergyAuthError as err:
            _LOGGER.debug("Credential test failed with RedEnergyAuthError: %s", err)
            return False
        except Exception as err:
            _LOGGER.error("Unexpected error during credential test for user %s: %s", username, err, exc_info=True)
            return False
    
    async def get_customer_data(self) -> Dict[str, Any]:
        """Get current customer data."""
        await self._ensure_valid_token()
        
        url = f"{self.BASE_API_URL}/customers/current"
        headers = {'Authorization': f'Bearer {self._access_token}'}
        
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
    
    async def get_properties(self) -> List[Dict[str, Any]]:
        """Get customer properties/accounts."""
        await self._ensure_valid_token()
        
        url = f"{self.BASE_API_URL}/properties"
        headers = {'Authorization': f'Bearer {self._access_token}'}
        
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                return data if isinstance(data, list) else data.get('properties', [])
    
    async def get_usage_data(
        self, 
        consumer_number: str, 
        from_date: datetime, 
        to_date: datetime
    ) -> Dict[str, Any]:
        """Get usage interval data."""
        await self._ensure_valid_token()
        
        url = f"{self.BASE_API_URL}/usage/interval"
        params = {
            'consumerNumber': consumer_number,
            'fromDate': from_date.strftime('%Y-%m-%d'),
            'toDate': to_date.strftime('%Y-%m-%d')
        }
        headers = {'Authorization': f'Bearer {self._access_token}'}
        
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                raw_data = await response.json()
                
                # Enhanced logging for investigation
                _LOGGER.debug("=" * 80)
                _LOGGER.debug("RAW USAGE API RESPONSE - DETAILED ANALYSIS")
                _LOGGER.debug("=" * 80)
                _LOGGER.debug("Request Parameters:")
                _LOGGER.debug("  Consumer Number: %s", consumer_number)
                _LOGGER.debug("  Date Range: %s to %s", params['fromDate'], params['toDate'])
                _LOGGER.debug("")
                _LOGGER.debug("Response Analysis:")
                _LOGGER.debug("  Data Type: %s", type(raw_data).__name__)
                
                if isinstance(raw_data, list):
                    _LOGGER.debug("  Array Length: %d items", len(raw_data))
                    if raw_data:
                        _LOGGER.debug("  First Item Type: %s", type(raw_data[0]).__name__)
                        if isinstance(raw_data[0], dict):
                            _LOGGER.debug("  First Item Keys: %s", list(raw_data[0].keys()))
                elif isinstance(raw_data, dict):
                    _LOGGER.debug("  Dictionary Keys: %s", list(raw_data.keys()))
                    for key, value in raw_data.items():
                        if isinstance(value, list):
                            _LOGGER.debug("    - %s: list with %d items", key, len(value))
                        elif isinstance(value, dict):
                            _LOGGER.debug("    - %s: dict with keys %s", key, list(value.keys()))
                        else:
                            _LOGGER.debug("    - %s: %s = %s", key, type(value).__name__, value)
                
                _LOGGER.debug("")
                _LOGGER.debug("Complete JSON Response (pretty-printed):")
                try:
                    pretty_json = json.dumps(raw_data, indent=2, default=str)
                    # Split by lines to log each line separately (better for log viewing)
                    for line in pretty_json.split('\n')[:100]:  # Limit to first 100 lines
                        _LOGGER.debug("  %s", line)
                    if len(pretty_json.split('\n')) > 100:
                        _LOGGER.debug("  ... (truncated, %d total lines)", len(pretty_json.split('\n')))
                except Exception as err:
                    _LOGGER.debug("  Unable to pretty-print JSON: %s", err)
                    _LOGGER.debug("  Raw data: %s", raw_data)
                
                _LOGGER.debug("=" * 80)
                
                # Transform API response to expected format
                return self._transform_usage_data(raw_data, consumer_number, from_date, to_date)
    
    async def _ensure_valid_token(self) -> None:
        """Ensure we have a valid access token."""
        if not self._access_token:
            _LOGGER.error(
                "No access token available. This indicates authentication was not completed properly. "
                "Token expires: %s, Refresh token available: %s",
                self._token_expires, bool(self._refresh_token)
            )
            raise RedEnergyAuthError("No access token available")
        
        if self._token_expires and datetime.now() >= self._token_expires:
            if self._refresh_token:
                await self._refresh_access_token()
            else:
                raise RedEnergyAuthError("Token expired and no refresh token available")
    
    async def _refresh_access_token(self) -> None:
        """Refresh the access token using refresh token."""
        if not self._refresh_token:
            raise RedEnergyAuthError("No refresh token available")
        
        # Get token endpoint from discovery
        discovery_data = await self._get_discovery_data()
        token_endpoint = discovery_data["token_endpoint"]
        
        token_data = {
            'grant_type': 'refresh_token',
            'refresh_token': self._refresh_token,
            'client_id': CLIENT_ID,
        }
        
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.post(
                token_endpoint,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            ) as response:
                if response.status != 200:
                    error_data = await response.json()
                    raise RedEnergyAuthError(f"Token refresh failed: {error_data}")
                
                tokens = await response.json()
                
                self._access_token = tokens['access_token']
                if 'refresh_token' in tokens:
                    self._refresh_token = tokens['refresh_token']
                
                expires_in = tokens.get('expires_in', 3600)
                self._token_expires = datetime.now() + timedelta(seconds=expires_in)
                
                _LOGGER.debug("Access token refreshed successfully")
    
    def _transform_usage_data(
        self, 
        raw_data: Any, 
        consumer_number: str, 
        from_date: datetime, 
        to_date: datetime
    ) -> Dict[str, Any]:
        """Transform Red Energy API usage data to expected format."""
        from_date_str = from_date.strftime('%Y-%m-%d')
        to_date_str = to_date.strftime('%Y-%m-%d')
        
        # Case 1: Data is None or empty
        if raw_data is None:
            _LOGGER.warning("API returned None for usage data - returning empty structure")
            return {
                "consumer_number": str(consumer_number),
                "from_date": from_date_str,
                "to_date": to_date_str,
                "usage_data": []
            }
        
        # Case 2: Data is already in expected format (has consumer_number and usage_data)
        if isinstance(raw_data, dict) and "consumer_number" in raw_data and "usage_data" in raw_data:
            _LOGGER.debug("API data already in expected format")
            return raw_data
        
        # Case 3: Data is a list of usage entries (most common API format)
        if isinstance(raw_data, list):
            _LOGGER.debug("API returned list of %d usage entries - transforming", len(raw_data))
            normalized_entries = [self._normalize_usage_entry(entry) for entry in raw_data]
            return {
                "consumer_number": str(consumer_number),
                "from_date": from_date_str,
                "to_date": to_date_str,
                "usage_data": normalized_entries
            }
        
        # Case 4: Data is a dict with different field names - try to extract usage data
        if isinstance(raw_data, dict):
            # Look for common variations of usage data fields
            usage_entries = (
                raw_data.get("usage_data") or
                raw_data.get("usageData") or
                raw_data.get("data") or
                raw_data.get("intervals") or
                raw_data.get("usage") or
                raw_data.get("entries") or
                []
            )
            
            # If we found usage entries as a list, use them
            if isinstance(usage_entries, list):
                _LOGGER.debug("Extracted %d usage entries from dict format", len(usage_entries))
                normalized_entries = [self._normalize_usage_entry(entry) for entry in usage_entries]
                return {
                    "consumer_number": str(consumer_number),
                    "from_date": from_date_str,
                    "to_date": to_date_str,
                    "usage_data": normalized_entries
                }
            
            # Otherwise, the dict might be a single usage entry - wrap it in a list
            _LOGGER.debug("API returned single dict entry - wrapping in list")
            normalized_entry = self._normalize_usage_entry(raw_data)
            return {
                "consumer_number": str(consumer_number),
                "from_date": from_date_str,
                "to_date": to_date_str,
                "usage_data": [normalized_entry]
            }
        
        # Case 5: Unexpected format - log error but return empty structure
        _LOGGER.error(
            "Unexpected usage data format: type=%s, data=%s - returning empty structure",
            type(raw_data), raw_data
        )
        return {
            "consumer_number": str(consumer_number),
            "from_date": from_date_str,
            "to_date": to_date_str,
            "usage_data": []
        }
    
    def _normalize_usage_entry(self, entry: Any) -> Dict[str, Any]:
        """Normalize a single usage entry with comprehensive breakdowns.
        
        Extracts detailed breakdown data from halfHours array including:
        - Separate import (consumption) and export (generation) totals
        - Time period breakdowns (PEAK/OFFPEAK/SHOULDER)
        - Max demand tracking
        - Carbon emissions
        
        Red Energy returns daily summaries with:
        - usageDate: the date
        - halfHours: array of 48 30-minute intervals
        - consumptionDollar: daily total cost (excl GST)
        - generationDollar: daily solar credit
        - maxDemandDetail: max demand information
        - carbonEmissionTonne: daily carbon emissions
        """
        if not isinstance(entry, dict):
            _LOGGER.warning("Usage entry is not a dict: %s, returning empty entry", type(entry))
            return self._empty_entry()
        
        # Log the first entry to help debug field mapping
        if not self._logged_entry_mapping:
            _LOGGER.debug("=" * 80)
            _LOGGER.debug("USAGE ENTRY FIELD MAPPING (First Entry)")
            _LOGGER.debug("=" * 80)
            _LOGGER.debug("Original Entry Structure:")
            try:
                # Log just the keys and top-level values, not the huge halfHours array
                summary = {k: (f"[{len(v)} items]" if isinstance(v, list) else v) 
                          for k, v in entry.items()}
                pretty_entry = json.dumps(summary, indent=2, default=str)
                for line in pretty_entry.split('\n'):
                    _LOGGER.debug("  %s", line)
            except Exception:
                _LOGGER.debug("  %s", entry)
            self._logged_entry_mapping = True
        
        # Extract date from usageDate field
        date_value = entry.get("usageDate", "")
        half_hours = entry.get("halfHours", [])
        
        # Initialize accumulators
        import_usage = 0.0
        export_usage = 0.0
        
        # Time period breakdowns
        peak_import = 0.0
        offpeak_import = 0.0
        shoulder_import = 0.0
        peak_export = 0.0
        offpeak_export = 0.0
        shoulder_export = 0.0
        
        # Max demand tracking
        max_demand_kw = 0.0
        max_demand_time = None
        
        # Process each 30-minute interval (48 per day)
        if isinstance(half_hours, list):
            for interval in half_hours:
                if not isinstance(interval, dict):
                    continue
                
                # Extract interval data
                consumption = float(interval.get("consumptionKwh", 0.0))
                generation = float(interval.get("generationKwh", 0.0))
                period = interval.get("primaryConsumptionTariffComponent", "").upper()
                
                # Accumulate totals
                import_usage += consumption
                export_usage += generation
                
                # Accumulate by time period
                if period == "PEAK":
                    peak_import += consumption
                    peak_export += generation
                elif period == "OFFPEAK":
                    offpeak_import += consumption
                    offpeak_export += generation
                elif period == "SHOULDER":
                    shoulder_import += consumption
                    shoulder_export += generation
                
                # Track max demand from interval detail
                demand_detail = interval.get("demandDetail", {})
                if isinstance(demand_detail, dict):
                    demand_kw = float(demand_detail.get("demandKw", 0.0))
                    if demand_kw > max_demand_kw:
                        max_demand_kw = demand_kw
                        max_demand_time = interval.get("intervalStart")
        
        # Extract daily costs from summary
        import_cost = float(entry.get("consumptionDollar", 0.0))
        generation_dollar = float(entry.get("generationDollar", 0.0))
        export_credit = abs(generation_dollar)  # Convert to positive value
        net_cost = import_cost - export_credit
        
        # Extract carbon emissions from daily summary
        carbon_emission = float(entry.get("carbonEmissionTonne", 0.0))
        
        # Check for max demand from daily summary (may be more accurate)
        max_demand_detail = entry.get("maxDemandDetail", {})
        if isinstance(max_demand_detail, dict) and max_demand_detail:
            daily_max_demand = float(max_demand_detail.get("demandKw", 0.0))
            if daily_max_demand > max_demand_kw:
                max_demand_kw = daily_max_demand
                max_demand_time = max_demand_detail.get("intervalStart")
        
        _LOGGER.debug(
            "Normalized entry for %s: import=%.3f kWh, export=%.3f kWh, "
            "import_cost=$%.2f, export_credit=$%.2f, net=$%.2f, "
            "peak_import=%.3f, offpeak_import=%.3f, shoulder_import=%.3f",
            date_value, import_usage, export_usage,
            import_cost, export_credit, net_cost,
            peak_import, offpeak_import, shoulder_import
        )
        
        return {
            # Backward compatibility
            "date": str(date_value),
            "usage": round(import_usage - export_usage, 3),  # Net usage
            "cost": round(net_cost, 2),
            "unit": "kWh",
            
            # Import/Export totals
            "import_usage": round(import_usage, 3),
            "export_usage": round(export_usage, 3),
            "import_cost": round(import_cost, 2),
            "export_credit": round(export_credit, 2),
            "net_cost": round(net_cost, 2),
            
            # Time period import breakdowns
            "peak_import_usage": round(peak_import, 3),
            "offpeak_import_usage": round(offpeak_import, 3),
            "shoulder_import_usage": round(shoulder_import, 3),
            
            # Time period export breakdowns
            "peak_export_usage": round(peak_export, 3),
            "offpeak_export_usage": round(offpeak_export, 3),
            "shoulder_export_usage": round(shoulder_export, 3),
            
            # Demand and environmental
            "max_demand_kw": round(max_demand_kw, 3),
            "max_demand_time": max_demand_time,
            "carbon_emission_tonne": round(carbon_emission, 6)
        }
    
    def _empty_entry(self) -> Dict[str, Any]:
        """Return an empty entry structure with all fields initialized to zero."""
        return {
            "date": "",
            "usage": 0.0,
            "cost": 0.0,
            "unit": "kWh",
            "import_usage": 0.0,
            "export_usage": 0.0,
            "import_cost": 0.0,
            "export_credit": 0.0,
            "net_cost": 0.0,
            "peak_import_usage": 0.0,
            "offpeak_import_usage": 0.0,
            "shoulder_import_usage": 0.0,
            "peak_export_usage": 0.0,
            "offpeak_export_usage": 0.0,
            "shoulder_export_usage": 0.0,
            "max_demand_kw": 0.0,
            "max_demand_time": None,
            "carbon_emission_tonne": 0.0
        }
    
    def _find_source_key(self, entry: Dict[str, Any], possible_keys: List[str]) -> str:
        """Find which key was actually present in the entry."""
        for key in possible_keys:
            if key in entry and entry[key]:
                return f"'{key}'"
        return "none (using default)"