"""Test mocking utilities for Red Energy integration."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock


class MockRedEnergyAPI:
    """Mock Red Energy API for testing."""
    
    def __init__(self, session=None):
        """Initialize mock API."""
        self._session = session
        self._access_token = None
        self._refresh_token = None
        self._token_expires = None
        
        # Mock data
        self.mock_customer_data = {
            "id": "12345",
            "name": "John Smith", 
            "email": "test@example.com",
            "phone": "+61400123456"
        }
        
        self.mock_properties = [
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
            }
        ]
    
    async def authenticate(self, username: str, password: str, client_id: str) -> bool:
        """Mock authentication."""
        # Mock successful authentication for test credentials
        if username == "test@example.com" and password == "testpass" and client_id == "test-client-123":
            self._access_token = "mock-access-token"
            self._refresh_token = "mock-refresh-token"
            self._token_expires = datetime.now() + timedelta(hours=1)
            return True
        return False
    
    async def test_credentials(self, username: str, password: str, client_id: str) -> bool:
        """Test mock credentials."""
        return await self.authenticate(username, password, client_id)
    
    async def get_customer_data(self) -> Dict[str, Any]:
        """Get mock customer data."""
        return self.mock_customer_data.copy()
    
    async def get_properties(self) -> List[Dict[str, Any]]:
        """Get mock properties."""
        return self.mock_properties.copy()
    
    async def get_usage_data(
        self,
        consumer_number: str,
        from_date: datetime,
        to_date: datetime
    ) -> Dict[str, Any]:
        """Get mock usage data."""
        # Generate mock daily usage data
        current_date = from_date
        usage_data = []
        
        while current_date <= to_date:
            # Mock usage values
            base_usage = 25 if "elec" in consumer_number else 45
            daily_usage = base_usage + (hash(current_date.strftime("%Y%m%d")) % 20)
            
            usage_data.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "usage": daily_usage,
                "cost": daily_usage * 0.28,
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


def create_mock_api() -> MockRedEnergyAPI:
    """Create a mock API instance for testing."""
    return MockRedEnergyAPI()


def create_mock_hass():
    """Create a mock Home Assistant instance for testing."""
    mock_hass = MagicMock()
    mock_hass.data = {}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
    mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return mock_hass


def create_mock_config_entry(data=None, options=None):
    """Create a mock config entry for testing."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry_id"
    mock_entry.data = data or {
        "username": "test@example.com",
        "password": "testpass",
        "client_id": "test-client-123",
        "selected_accounts": ["prop-001"],
        "services": ["electricity"]
    }
    mock_entry.options = options or {}
    return mock_entry


# Test constants
MOCK_VALID_CREDENTIALS = {
    "username": "test@example.com",
    "password": "testpass", 
    "client_id": "test-client-123"
}

MOCK_INVALID_CREDENTIALS = {
    "username": "invalid@example.com",
    "password": "wrongpass",
    "client_id": "invalid-client"
}