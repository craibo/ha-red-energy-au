"""Integration tests for 400 error handling scenarios."""
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
def coordinator_with_multiple_properties(mock_hass):
    """Create coordinator with multiple properties and services."""
    coordinator = RedEnergyDataCoordinator(
        hass=mock_hass,
        username="test_user",
        password="test_pass",
        selected_accounts=["prop1", "prop2", "prop3"],
        services=["electricity", "gas"]
    )
    
    # Mock the API
    coordinator.api = AsyncMock()
    coordinator.api._access_token = "test_token"
    
    # Mock properties with multiple services
    coordinator._properties = [
        {
            "id": "prop1",
            "name": "Property 1",
            "services": [
                {
                    "type": "electricity",
                    "consumer_number": "elec1",
                    "active": True,
                    "lastBillDate": "2024-01-01"
                },
                {
                    "type": "gas",
                    "consumer_number": "gas1",
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
                    "consumer_number": "elec2",
                    "active": True,
                    "lastBillDate": "2024-01-01"
                },
                {
                    "type": "gas",
                    "consumer_number": "gas2",
                    "active": True,
                    "lastBillDate": "2024-01-01"
                }
            ]
        },
        {
            "id": "prop3",
            "name": "Property 3",
            "services": [
                {
                    "type": "electricity",
                    "consumer_number": "elec3",
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
async def test_integration_mixed_success_failure_scenario(coordinator_with_multiple_properties, caplog):
    """Test integration with mixed success and failure across properties and services."""
    # Define which services should fail
    failing_services = {"elec1", "gas2"}  # Property 1 electricity and Property 2 gas
    
    def mock_get_usage_data(consumer_number, start_date, end_date):
        if consumer_number in failing_services:
            # Return 400 error for failing services
            return {
                "error": True,
                "error_type": "bad_request",
                "error_message": f"Invalid consumer number: {consumer_number}",
                "error_details": f"Consumer number {consumer_number} is not valid for this account",
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": []
            }
        else:
            # Return success for working services
            return {
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": [
                    {
                        "date": "2024-01-01",
                        "usage": 20.0,
                        "cost": 30.00,
                        "unit": "kWh"
                    }
                ]
            }
    
    coordinator_with_multiple_properties.api.get_usage_data = AsyncMock(side_effect=mock_get_usage_data)
    
    # Call the update method
    result = await coordinator_with_multiple_properties._async_update_data()
    
    # Verify we got data for successful services only
    assert "usage_data" in result
    
    # Property 1: electricity should fail, gas should succeed
    assert "prop1" in result["usage_data"]
    prop1_data = result["usage_data"]["prop1"]
    assert "gas" in prop1_data["services"]
    assert "electricity" not in prop1_data["services"]
    
    # Property 2: electricity should succeed, gas should fail
    assert "prop2" in result["usage_data"]
    prop2_data = result["usage_data"]["prop2"]
    assert "electricity" in prop2_data["services"]
    assert "gas" not in prop2_data["services"]
    
    # Property 3: electricity should succeed
    assert "prop3" in result["usage_data"]
    prop3_data = result["usage_data"]["prop3"]
    assert "electricity" in prop3_data["services"]
    
    # Verify error warnings were logged
    assert "API returned error for electricity service (consumer elec1)" in caplog.text
    assert "API returned error for gas service (consumer gas2)" in caplog.text
    
    # Verify success messages were logged
    assert "Successfully fetched gas usage for property prop1" in caplog.text
    assert "Successfully fetched electricity usage for property prop2" in caplog.text
    assert "Successfully fetched electricity usage for property prop3" in caplog.text


@pytest.mark.asyncio
async def test_integration_all_services_fail_for_one_property(coordinator_with_multiple_properties, caplog):
    """Test integration when all services fail for one property but others succeed."""
    # Make all services for property 1 fail
    def mock_get_usage_data(consumer_number, start_date, end_date):
        if consumer_number in {"elec1", "gas1"}:
            return {
                "error": True,
                "error_type": "bad_request",
                "error_message": "Property 1 services unavailable",
                "error_details": "All services for property 1 are currently unavailable",
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": []
            }
        else:
            return {
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": [
                    {
                        "date": "2024-01-01",
                        "usage": 25.0,
                        "cost": 40.00,
                        "unit": "kWh"
                    }
                ]
            }
    
    coordinator_with_multiple_properties.api.get_usage_data = AsyncMock(side_effect=mock_get_usage_data)
    
    # Call the update method
    result = await coordinator_with_multiple_properties._async_update_data()
    
    # Verify property 1 has no usage data (all services failed)
    assert "prop1" not in result["usage_data"]
    
    # Verify other properties have data
    assert "prop2" in result["usage_data"]
    assert "prop3" in result["usage_data"]
    
    # Verify property 2 has both services
    prop2_data = result["usage_data"]["prop2"]
    assert "electricity" in prop2_data["services"]
    assert "gas" in prop2_data["services"]
    
    # Verify property 3 has electricity service
    prop3_data = result["usage_data"]["prop3"]
    assert "electricity" in prop3_data["services"]
    
    # Verify error warnings were logged for property 1
    assert "API returned error for electricity service (consumer elec1)" in caplog.text
    assert "API returned error for gas service (consumer gas1)" in caplog.text
    assert "Property 1 services unavailable" in caplog.text


@pytest.mark.asyncio
async def test_integration_partial_failure_with_retry_logic(coordinator_with_multiple_properties, caplog):
    """Test integration with partial failures and verify retry behavior."""
    call_count = {}
    
    def mock_get_usage_data(consumer_number, start_date, end_date):
        # Track calls for each consumer
        call_count[consumer_number] = call_count.get(consumer_number, 0) + 1
        
        # Fail on first call for elec1, succeed on subsequent calls
        if consumer_number == "elec1" and call_count[consumer_number] == 1:
            return {
                "error": True,
                "error_type": "bad_request",
                "error_message": "Temporary service unavailable",
                "error_details": "Service temporarily unavailable, please try again",
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": []
            }
        else:
            return {
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": [
                    {
                        "date": "2024-01-01",
                        "usage": 15.0,
                        "cost": 25.00,
                        "unit": "kWh"
                    }
                ]
            }
    
    coordinator_with_multiple_properties.api.get_usage_data = AsyncMock(side_effect=mock_get_usage_data)
    
    # Call the update method
    result = await coordinator_with_multiple_properties._async_update_data()
    
    # Verify all services were called exactly once (no automatic retry)
    assert call_count["elec1"] == 1
    assert call_count["elec2"] == 1
    assert call_count["gas1"] == 1
    assert call_count["gas2"] == 1
    assert call_count["elec3"] == 1
    
    # Verify property 1 has only gas data (electricity failed)
    assert "prop1" in result["usage_data"]
    prop1_data = result["usage_data"]["prop1"]
    assert "gas" in prop1_data["services"]
    assert "electricity" not in prop1_data["services"]
    
    # Verify error was logged for elec1
    assert "API returned error for electricity service (consumer elec1)" in caplog.text
    assert "Temporary service unavailable" in caplog.text


@pytest.mark.asyncio
async def test_integration_graceful_degradation_with_minimal_data(coordinator_with_multiple_properties, caplog):
    """Test integration graceful degradation when most services fail."""
    # Make most services fail, only allow one to succeed
    def mock_get_usage_data(consumer_number, start_date, end_date):
        if consumer_number == "elec3":  # Only property 3 electricity succeeds
            return {
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": [
                    {
                        "date": "2024-01-01",
                        "usage": 30.0,
                        "cost": 50.00,
                        "unit": "kWh"
                    }
                ]
            }
        else:
            return {
                "error": True,
                "error_type": "bad_request",
                "error_message": "Service unavailable",
                "error_details": "Service is currently unavailable",
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": []
            }
    
    coordinator_with_multiple_properties.api.get_usage_data = AsyncMock(side_effect=mock_get_usage_data)
    
    # Call the update method
    result = await coordinator_with_multiple_properties._async_update_data()
    
    # Verify we still get some data (graceful degradation)
    assert "usage_data" in result
    assert "prop3" in result["usage_data"]
    assert "prop1" not in result["usage_data"]
    assert "prop2" not in result["usage_data"]
    
    # Verify property 3 has electricity data
    prop3_data = result["usage_data"]["prop3"]
    assert "electricity" in prop3_data["services"]
    electricity_data = prop3_data["services"]["electricity"]
    assert electricity_data["usage_data"]["usage_data"][0]["usage"] == 30.0
    
    # Verify multiple error warnings were logged
    error_warnings = [record for record in caplog.records if "API returned error" in record.message]
    assert len(error_warnings) == 5  # 5 services failed


@pytest.mark.asyncio
async def test_integration_logging_levels_and_debug_info(coordinator_with_multiple_properties, caplog):
    """Test that appropriate logging levels are used for different scenarios."""
    import logging
    caplog.set_level(logging.DEBUG)
    
    # Mix of success and failure
    def mock_get_usage_data(consumer_number, start_date, end_date):
        if consumer_number in {"elec1", "gas2"}:
            return {
                "error": True,
                "error_type": "bad_request",
                "error_message": "Service unavailable",
                "error_details": "Service is currently unavailable",
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": []
            }
        else:
            return {
                "consumer_number": consumer_number,
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": end_date.strftime('%Y-%m-%d'),
                "usage_data": [
                    {
                        "date": "2024-01-01",
                        "usage": 20.0,
                        "cost": 35.00,
                        "unit": "kWh"
                    }
                ]
            }
    
    coordinator_with_multiple_properties.api.get_usage_data = AsyncMock(side_effect=mock_get_usage_data)
    
    # Call the update method
    await coordinator_with_multiple_properties._async_update_data()
    
    # Verify debug logs for processing details
    debug_logs = [record for record in caplog.records if record.levelno == logging.DEBUG]
    assert any("COORDINATOR CONFIGURATION:" in record.message for record in debug_logs)
    assert any("Processing property:" in record.message for record in debug_logs)
    assert any("Processing service:" in record.message for record in debug_logs)
    assert any("Calling API get_usage_data:" in record.message for record in debug_logs)
    
    # Verify warning logs for errors
    warning_logs = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert any("API returned error for electricity service (consumer elec1)" in record.message for record in warning_logs)
    assert any("API returned error for gas service (consumer gas2)" in record.message for record in warning_logs)
    
    # Verify info logs for successful operations
    info_logs = [record for record in caplog.records if record.levelno == logging.INFO]
    assert any("Successfully fetched" in record.message for record in info_logs)
