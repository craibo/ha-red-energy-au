"""Red Energy API client for Home Assistant integration."""
from __future__ import annotations

import asyncio
import logging
import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, parse_qs, urlparse
import hashlib
import base64

import aiohttp
import async_timeout

from .const import API_TIMEOUT

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
    
    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._session = session
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        
    async def authenticate(self, username: str, password: str, client_id: str) -> bool:
        """Authenticate with Red Energy using OAuth2 PKCE flow."""
        try:
            _LOGGER.debug("Starting Red Energy authentication")
            
            # Get OAuth2 endpoints from discovery URL
            discovery_data = await self._get_discovery_data()
            auth_endpoint = discovery_data["authorization_endpoint"]
            token_endpoint = discovery_data["token_endpoint"]
            
            # Generate PKCE parameters
            code_verifier = self._generate_code_verifier()
            code_challenge = self._generate_code_challenge(code_verifier)
            
            # Step 1: Get authorization code
            auth_code = await self._get_authorization_code(
                auth_endpoint, username, password, client_id, code_challenge
            )
            
            # Step 2: Exchange authorization code for tokens
            await self._exchange_code_for_tokens(
                token_endpoint, auth_code, client_id, code_verifier
            )
            
            _LOGGER.debug("Red Energy authentication successful")
            return True
            
        except Exception as err:
            _LOGGER.error("Authentication failed: %s", err)
            raise RedEnergyAuthError(f"Authentication failed: {err}") from err
    
    async def _get_discovery_data(self) -> Dict[str, Any]:
        """Get OAuth2 discovery data."""
        async with async_timeout.timeout(API_TIMEOUT):
            async with self._session.get(self.DISCOVERY_URL) as response:
                response.raise_for_status()
                return await response.json()
    
    def _generate_code_verifier(self) -> str:
        """Generate PKCE code verifier."""
        return base64.urlsafe_b64encode(
            ''.join(secrets.choice(string.ascii_letters + string.digits) 
                   for _ in range(128)).encode()
        ).decode().rstrip('=')
    
    def _generate_code_challenge(self, verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')
    
    async def _get_authorization_code(
        self, 
        auth_endpoint: str, 
        username: str, 
        password: str, 
        client_id: str,
        code_challenge: str
    ) -> str:
        """Get authorization code through login flow."""
        # Simplified implementation - in production this would handle the full OAuth flow
        # including form submissions, redirects, and parsing the authorization code from the callback
        
        auth_params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': self.REDIRECT_URI,
            'scope': 'openid profile email',
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'state': secrets.token_urlsafe(32),
        }
        
        auth_url = f"{auth_endpoint}?{urlencode(auth_params)}"
        
        # For now, return a placeholder that will be replaced with real implementation
        # In a real implementation, this would:
        # 1. Submit the login form with username/password
        # 2. Handle any MFA challenges
        # 3. Follow redirects to capture the authorization code
        # 4. Parse the code from the callback URL
        
        _LOGGER.warning(
            "Red Energy API authentication requires manual implementation of OAuth flow. "
            "Using mock mode for now. To use real API, implement the full OAuth2 PKCE flow."
        )
        
        raise RedEnergyAuthError(
            "Real Red Energy API authentication not yet implemented. "
            "The integration currently uses mock data for testing. "
            "To connect to the real API, the OAuth2 PKCE flow needs to be completed."
        )
    
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
                response.raise_for_status()
                tokens = await response.json()
                
                self._access_token = tokens['access_token']
                self._refresh_token = tokens.get('refresh_token')
                expires_in = tokens.get('expires_in', 3600)
                self._token_expires = datetime.now() + timedelta(seconds=expires_in)
    
    async def test_credentials(self, username: str, password: str, client_id: str) -> bool:
        """Test if credentials are valid by attempting authentication."""
        try:
            return await self.authenticate(username, password, client_id)
        except RedEnergyAuthError:
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
                return await response.json()
    
    async def _ensure_valid_token(self) -> None:
        """Ensure we have a valid access token."""
        if not self._access_token:
            raise RedEnergyAuthError("No access token available")
        
        if self._token_expires and datetime.now() >= self._token_expires:
            if self._refresh_token:
                await self._refresh_access_token()
            else:
                raise RedEnergyAuthError("Token expired and no refresh token available")
    
    async def _refresh_access_token(self) -> None:
        """Refresh the access token using refresh token."""
        # Implementation would depend on the specific OAuth2 flow
        raise NotImplementedError("Token refresh needs implementation")