"""Tests for coordinator 400 error handling."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.api import RedEnergyAPIError


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    return hass


@pytest.fixture
def coordinator(mock_hass):
    """Create coordinator for testing."""
    coordinator = RedEnergyDataCoordinator(
        hass=mock_hass,
        username="test_user",
        password="test_pass",
        selected_accounts=["prop1", "prop2"],
        services=["electricity"]
    )
    
    # Mock the API
    coordinator.api = AsyncMock()
    coordinator.api._access_token = "test_token"
    
    # Mock properties data
    coordinator._properties = [
        {
            "id": "prop1",
            "name": "Property 1",
            "services": [
                {
                    "type": "electricity",
                    "consumer_number": "1234567890",
                    "active": True,
                    "lastBillDate": "2024-01-01"
                }
            ]
        },
        {
            "id": "prop2", 
            "name": "Property 2",
            "services": [
                {
                    "type": "electricity",
                    "consumer_number": "0987654321",
                    "active": True,
                    "lastBillDate": "2024-01-01"
                }
            ]
        }
    ]
    
    # Mock customer data
    coordinator._customer_data = {"id": "customer1", "name": "Test Customer"}
    
    return coordinator


@pytest.mark.asyncio
async def test_coordinator_handles_400_error_gracefully(coordinator, caplog):
    """Test that coordinator handles 400 errors and continues processing."""
    # Mock API to return 400 error for first property, success for second
    def mock_get_usage_data(consumer_number, start_date, end_date):
        if consumer_number == "1234567890":
            # Return 400 error for first property
            return {
                "error": True,
                "error_type": "bad_request",
                "error_message": "Invalid consumer number",
                "error_details": "Consumer number 1234567890 is not valid",
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": []
            }
        else:
            # Return success for second property
            return {
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": [
                    {"date": "2024-01-01", "usage": 15.5, "cost": 25.50}
                ]
            }
    
    coordinator.api.get_usage_data = AsyncMock(side_effect=mock_get_usage_data)
    
    # Call the update method
    result = await coordinator._async_update_data()
    
    # Verify the result contains data for the successful property only
    assert "usage_data" in result
    assert "prop2" in result["usage_data"]  # Second property succeeded
    assert "prop1" not in result["usage_data"]  # First property failed
    
    # Verify warning was logged for the failed service
    assert "API returned error for electricity service (consumer 1234567890)" in caplog.text
    assert "Invalid consumer number" in caplog.text
    assert "Skipping this service but continuing with others" in caplog.text
    
    # Verify success was logged for the working service
    assert "Successfully fetched electricity usage for property prop2" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_handles_all_services_failing(coordinator, caplog):
    """Test coordinator behavior when all services return 400 errors."""
    # Mock API to return 400 error for all properties
    coordinator.api.get_usage_data = AsyncMock(return_value={
        "error": True,
        "error_type": "bad_request",
        "error_message": "Invalid consumer number",
        "error_details": "All consumer numbers are invalid",
        "consumer_number": "1234567890",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": []
    })
    
    # Call the update method
    with pytest.raises(Exception):  # Should raise UpdateFailed
        await coordinator._async_update_data()
    
    # Verify warnings were logged for all failed services
    assert "API returned error for electricity service" in caplog.text
    assert "Invalid consumer number" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_mixed_success_and_failure(coordinator, caplog):
    """Test coordinator with some services succeeding and others failing."""
    # Mock API responses
    def mock_get_usage_data(consumer_number, start_date, end_date):
        if consumer_number == "1234567890":
            # First property fails
            return {
                "error": True,
                "error_type": "bad_request",
                "error_message": "Invalid consumer number",
                "error_details": "Consumer number 1234567890 is not valid",
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": []
            }
        else:
            # Second property succeeds
            return {
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": [
                    {"date": "2024-01-01", "usage": 20.0, "cost": 35.00}
                ]
            }
    
    coordinator.api.get_usage_data = AsyncMock(side_effect=mock_get_usage_data)
    
    # Call the update method
    result = await coordinator._async_update_data()
    
    # Verify we got data for the successful property
    assert "usage_data" in result
    assert "prop2" in result["usage_data"]
    assert "prop1" not in result["usage_data"]
    
    # Verify the successful property has correct data
    prop2_data = result["usage_data"]["prop2"]
    assert "services" in prop2_data
    assert "electricity" in prop2_data["services"]
    
    electricity_data = prop2_data["services"]["electricity"]
    assert electricity_data["consumer_number"] == "0987654321"
    assert len(electricity_data["usage_data"]["usage_data"]) == 1
    assert electricity_data["usage_data"]["usage_data"][0]["usage"] == 20.0


@pytest.mark.asyncio
async def test_coordinator_skips_inactive_services(coordinator):
    """Test that coordinator skips inactive services."""
    # Set one service as inactive
    coordinator._properties[0]["services"][0]["active"] = False
    
    # Mock API (should not be called for inactive service)
    coordinator.api.get_usage_data = AsyncMock(return_value={
        "consumer_number": "0987654321",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": [{"date": "2024-01-01", "usage": 15.0, "cost": 25.00}]
    })
    
    # Call the update method
    result = await coordinator._async_update_data()
    
    # Verify only the active service was processed
    assert coordinator.api.get_usage_data.call_count == 1
    assert coordinator.api.get_usage_data.call_args[0][0] == "0987654321"  # Second property's consumer number
    
    # Verify result contains only the active service
    assert "usage_data" in result
    assert "prop2" in result["usage_data"]
    assert "prop1" not in result["usage_data"]


@pytest.mark.asyncio
async def test_coordinator_skips_unconfigured_services(coordinator):
    """Test that coordinator skips services not in configured services list."""
    # Add a gas service that's not in the configured services
    coordinator._properties[0]["services"].append({
        "type": "gas",
        "consumer_number": "1111111111",
        "active": True,
        "lastBillDate": "2024-01-01"
    })
    
    # Mock API (should only be called for electricity service)
    coordinator.api.get_usage_data = AsyncMock(return_value={
        "consumer_number": "1234567890",
        "from_date": "2024-01-01", 
        "to_date": "2024-01-02",
        "usage_data": [{"date": "2024-01-01", "usage": 10.0, "cost": 15.00}]
    })
    
    # Call the update method
    result = await coordinator._async_update_data()
    
    # Verify only electricity service was processed (2 calls for 2 properties)
    assert coordinator.api.get_usage_data.call_count == 2
    
    # Verify result contains only electricity services
    for prop_data in result["usage_data"].values():
        assert "electricity" in prop_data["services"]
        assert "gas" not in prop_data["services"]


@pytest.mark.asyncio
async def test_coordinator_logs_debug_information(coordinator, caplog):
    """Test that coordinator logs debug information during processing."""
    # Enable debug logging
    import logging
    caplog.set_level(logging.DEBUG)
    
    # Mock API to return success
    coordinator.api.get_usage_data = AsyncMock(return_value={
        "consumer_number": "1234567890",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02", 
        "usage_data": [{"date": "2024-01-01", "usage": 10.0, "cost": 15.00}]
    })
    
    # Call the update method
    await coordinator._async_update_data()
    
    # Verify debug logs were generated
    assert "COORDINATOR CONFIGURATION:" in caplog.text
    assert "Processing property:" in caplog.text
    assert "Property has" in caplog.text
    assert "Processing service:" in caplog.text
    assert "Service electricity MATCHED" in caplog.text
    assert "Calling API get_usage_data:" in caplog.text
    assert "DATA COLLECTION SUMMARY:" in caplog.text
