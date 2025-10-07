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


def create_mock_usage_data(property_id="prop-001", service_type="electricity", days=30):
    """Create mock usage data for testing."""
    from datetime import datetime, timedelta
    
    usage_data = []
    start_date = datetime.now() - timedelta(days=days)
    
    for i in range(days):
        current_date = start_date + timedelta(days=i)
        base_usage = 25 if service_type == "electricity" else 45
        daily_usage = base_usage + (i % 10)
        
        usage_data.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "usage": daily_usage,
            "cost": daily_usage * 0.28,
            "import_usage": daily_usage * 0.7,
            "export_usage": daily_usage * 0.3,
            "import_cost": daily_usage * 0.7 * 0.28,
            "export_credit": daily_usage * 0.3 * 0.10,
            "peak_import": daily_usage * 0.3,
            "offpeak_import": daily_usage * 0.5,
            "shoulder_import": daily_usage * 0.2,
        })
    
    return {
        "consumer_number": f"{service_type}-123",
        "from_date": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
        "to_date": datetime.now().strftime("%Y-%m-%d"),
        "usage_data": usage_data,
        "total_usage": sum(d["usage"] for d in usage_data),
        "total_cost": sum(d["cost"] for d in usage_data),
        "metadata": {
            "nmi": "1234567890",
            "meterType": "Smart Meter",
            "solar": True,
            "productName": "Basic Energy Plan",
            "linesCompany": "AusNet Services",
            "balanceDollar": -150.50,
            "arrearsDollar": 0.0,
            "lastBillDate": "2024-01-01",
            "nextBillDate": "2024-02-01",
            "billingFrequency": "monthly",
            "jurisdiction": "VIC",
            "chargeClass": "RES",
            "status": "ON",
            "active": True
        }
    }


def create_mock_coordinator_data(property_ids=None, service_types=None):
    """Create comprehensive mock coordinator data."""
    property_ids = property_ids or ["prop-001"]
    service_types = service_types or ["electricity"]
    
    data = {"usage_data": {}}
    
    for prop_id in property_ids:
        data["usage_data"][prop_id] = {
            "property": {
                "id": prop_id,
                "name": f"Property {prop_id}",
                "address": {
                    "street": "123 Test Street",
                    "city": "Melbourne",
                    "state": "VIC",
                    "postcode": "3000"
                }
            }
        }
        
        for service_type in service_types:
            usage_data = create_mock_usage_data(prop_id, service_type)
            data["usage_data"][prop_id][service_type] = {
                "consumer_number": usage_data["consumer_number"],
                "usage_data": {
                    "from_date": usage_data["from_date"],
                    "to_date": usage_data["to_date"],
                    "usage_data": usage_data["usage_data"]
                },
                "metadata": usage_data["metadata"],
                "period_days": 30,
                "last_updated": datetime.now().isoformat()
            }
    
    return data


def create_advanced_mock_coordinator():
    """Create an advanced mock coordinator with comprehensive data."""
    coordinator = MagicMock()
    coordinator.data = create_mock_coordinator_data()
    coordinator.last_update_success = True
    
    # Add all accessor methods
    coordinator.get_property_data = MagicMock(side_effect=lambda prop_id: 
        coordinator.data["usage_data"].get(prop_id, {}).get("property"))
    
    coordinator.get_service_usage = MagicMock(side_effect=lambda prop_id, service_type:
        coordinator.data["usage_data"].get(prop_id, {}).get(service_type))
    
    coordinator.get_service_metadata = MagicMock(side_effect=lambda prop_id, service_type:
        coordinator.data["usage_data"].get(prop_id, {}).get(service_type, {}).get("metadata"))
    
    # Add calculation methods
    coordinator.get_total_cost = MagicMock(return_value=23.24)
    coordinator.get_total_usage = MagicMock(return_value=83.0)
    coordinator.get_total_import_usage = MagicMock(return_value=83.0)
    coordinator.get_total_export_usage = MagicMock(return_value=15.0)
    coordinator.get_total_import_cost = MagicMock(return_value=23.24)
    coordinator.get_total_export_credit = MagicMock(return_value=2.10)
    coordinator.get_net_total_cost = MagicMock(return_value=21.14)
    coordinator.get_latest_import_usage = MagicMock(return_value=28.0)
    coordinator.get_latest_export_usage = MagicMock(return_value=5.0)
    coordinator.get_latest_import_cost = MagicMock(return_value=7.84)
    coordinator.get_latest_export_credit = MagicMock(return_value=0.70)
    coordinator.get_period_import_usage = MagicMock(return_value=50.0)
    coordinator.get_period_export_usage = MagicMock(return_value=10.0)
    coordinator.get_max_demand_data = MagicMock(return_value={
        "max_demand_kw": 5.2,
        "max_demand_time": "2024-01-15T18:30:00",
        "max_demand_date": "2024-01-15"
    })
    coordinator.get_total_carbon_emission = MagicMock(return_value=0.073)
    coordinator.get_performance_metrics = MagicMock(return_value={"operations": 100})
    coordinator.get_error_statistics = MagicMock(return_value={"total_errors": 0})
    
    return coordinator