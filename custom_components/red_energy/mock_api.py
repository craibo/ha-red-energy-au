"""Mock Red Energy API for testing and development."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from .api import RedEnergyAPI, RedEnergyAuthError

_LOGGER = logging.getLogger(__name__)


class MockRedEnergyAPI(RedEnergyAPI):
    """Mock Red Energy API for testing."""
    
    # Mock credentials for testing
    VALID_CREDENTIALS = {
        "test@example.com": {
            "password": "testpass",
            "client_id": "test-client-id-123"
        },
        "demo@redenergy.com.au": {
            "password": "demo123",
            "client_id": "demo-client-abc"
        }
    }
    
    MOCK_CUSTOMER_DATA = {
        "id": "12345",
        "name": "John Smith",
        "email": "test@example.com",
        "phone": "+61400123456"
    }
    
    MOCK_PROPERTIES = [
        {
            "id": "prop-001",
            "name": "Main Residence",
            "address": {
                "street": "123 Main Street",
                "city": "Melbourne",
                "state": "VIC",
                "postcode": "3000"
            },
            "services": [
                {
                    "type": "electricity",
                    "consumer_number": "elec-123456",
                    "active": True
                },
                {
                    "type": "gas", 
                    "consumer_number": "gas-789012",
                    "active": True
                }
            ]
        },
        {
            "id": "prop-002", 
            "name": "Investment Property",
            "address": {
                "street": "456 Oak Avenue",
                "city": "Sydney",
                "state": "NSW", 
                "postcode": "2000"
            },
            "services": [
                {
                    "type": "electricity",
                    "consumer_number": "elec-654321",
                    "active": True
                }
            ]
        }
    ]
    
    async def authenticate(self, username: str, password: str, client_id: str) -> bool:
        """Mock authentication."""
        _LOGGER.debug("Mock authentication for %s", username)
        
        valid_creds = self.VALID_CREDENTIALS.get(username)
        if not valid_creds:
            raise RedEnergyAuthError("Invalid username")
        
        if valid_creds["password"] != password:
            raise RedEnergyAuthError("Invalid password")
            
        if valid_creds["client_id"] != client_id:
            raise RedEnergyAuthError("Invalid client ID")
        
        # Set mock tokens
        self._access_token = f"mock-token-{username}"
        self._refresh_token = "mock-refresh-token"
        self._token_expires = datetime.now() + timedelta(hours=1)
        
        return True
    
    async def test_credentials(self, username: str, password: str, client_id: str) -> bool:
        """Test if credentials are valid."""
        try:
            return await self.authenticate(username, password, client_id)
        except RedEnergyAuthError:
            return False
    
    async def get_customer_data(self) -> Dict[str, Any]:
        """Get mock customer data."""
        await self._ensure_valid_token()
        return self.MOCK_CUSTOMER_DATA.copy()
    
    async def get_properties(self) -> List[Dict[str, Any]]:
        """Get mock properties."""
        await self._ensure_valid_token()
        return self.MOCK_PROPERTIES.copy()
    
    async def get_usage_data(
        self, 
        consumer_number: str, 
        from_date: datetime, 
        to_date: datetime
    ) -> Dict[str, Any]:
        """Get mock usage data."""
        await self._ensure_valid_token()
        
        # Generate mock daily usage data
        current_date = from_date
        usage_data = []
        
        while current_date <= to_date:
            # Mock usage values (kWh for electricity, MJ for gas)
            base_usage = 25 if "elec" in consumer_number else 45
            daily_usage = base_usage + (hash(current_date.strftime("%Y%m%d")) % 20)
            
            usage_data.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "usage": daily_usage,
                "cost": daily_usage * 0.28,  # Mock rate
                "unit": "kWh" if "elec" in consumer_number else "MJ"
            })
            
            current_date += timedelta(days=1)
        
        return {
            "consumer_number": consumer_number,
            "from_date": from_date.strftime("%Y-%m-%d"),
            "to_date": to_date.strftime("%Y-%m-%d"),
            "usage_data": usage_data,
            "total_usage": sum(d["usage"] for d in usage_data),
            "total_cost": sum(d["cost"] for d in usage_data)
        }
    
    async def _ensure_valid_token(self) -> None:
        """Mock token validation."""
        if not self._access_token:
            raise RedEnergyAuthError("No access token available")
        # In mock mode, tokens are always valid
        
    async def _refresh_access_token(self) -> None:
        """Mock token refresh."""
        self._token_expires = datetime.now() + timedelta(hours=1)