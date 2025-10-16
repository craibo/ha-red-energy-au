"""Tests for API 400 error handling."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from aiohttp import ClientResponseError
from custom_components.red_energy.api import RedEnergyAPI, RedEnergyAPIError


@pytest.fixture
def api_client():
    """Create API client for testing."""
    session = AsyncMock()
    return RedEnergyAPI(session)


@pytest.mark.asyncio
async def test_get_usage_data_400_error_with_json_response(api_client):
    """Test 400 error handling with JSON error response."""
    # Mock the session and response
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.url = "https://api.example.com/usage/interval?consumerNumber=123&fromDate=2024-01-01&toDate=2024-01-02"
    
    # Mock JSON error response
    error_data = {
        "message": "Invalid consumer number",
        "details": "Consumer number 123 is not valid for this account"
    }
    mock_response.json = AsyncMock(return_value=error_data)
    
    # Mock the session context manager
    async def mock_context_manager(*args, **kwargs):
        return mock_response
    
    api_client._session.get.return_value.__aenter__ = mock_context_manager
    api_client._session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    api_client._access_token = "test_token"
    
    # Call the method
    result = await api_client.get_usage_data("123", datetime(2024, 1, 1), datetime(2024, 1, 2))
    
    # Verify error response structure
    assert result["error"] is True
    assert result["error_type"] == "bad_request"
    assert result["error_message"] == "Invalid consumer number"
    assert result["error_details"] == "Consumer number 123 is not valid for this account"
    assert result["consumer_number"] == "123"
    assert result["from_date"] == "2024-01-01"
    assert result["to_date"] == "2024-01-02"
    assert result["usage_data"] == []


@pytest.mark.asyncio
async def test_get_usage_data_400_error_without_json_response(api_client):
    """Test 400 error handling when JSON parsing fails."""
    # Mock the session and response
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.url = "https://api.example.com/usage/interval?consumerNumber=123&fromDate=2024-01-01&toDate=2024-01-02"
    
    # Mock JSON parsing failure
    mock_response.json = AsyncMock(side_effect=Exception("Invalid JSON"))
    
    # Mock the session context manager
    async def mock_context_manager(*args, **kwargs):
        return mock_response
    
    api_client._session.get.return_value.__aenter__ = mock_context_manager
    api_client._session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    api_client._access_token = "test_token"
    
    # Call the method
    result = await api_client.get_usage_data("123", datetime(2024, 1, 1), datetime(2024, 1, 2))
    
    # Verify error response structure with fallback values
    assert result["error"] is True
    assert result["error_type"] == "bad_request"
    assert result["error_message"] == "Bad Request"
    assert result["error_details"] == "Unable to parse error response"
    assert result["consumer_number"] == "123"
    assert result["from_date"] == "2024-01-01"
    assert result["to_date"] == "2024-01-02"
    assert result["usage_data"] == []


@pytest.mark.asyncio
async def test_get_usage_data_400_error_with_missing_fields(api_client):
    """Test 400 error handling with missing error fields."""
    # Mock the session and response
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.url = "https://api.example.com/usage/interval?consumerNumber=123&fromDate=2024-01-01&toDate=2024-01-02"
    
    # Mock JSON response with missing fields
    error_data = {}
    mock_response.json = AsyncMock(return_value=error_data)
    
    # Mock the session context manager
    async def mock_context_manager(*args, **kwargs):
        return mock_response
    
    api_client._session.get.return_value.__aenter__ = mock_context_manager
    api_client._session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    api_client._access_token = "test_token"
    
    # Call the method
    result = await api_client.get_usage_data("123", datetime(2024, 1, 1), datetime(2024, 1, 2))
    
    # Verify error response structure with default values
    assert result["error"] is True
    assert result["error_type"] == "bad_request"
    assert result["error_message"] == "Bad Request"
    assert result["error_details"] == "No additional details"
    assert result["consumer_number"] == "123"
    assert result["from_date"] == "2024-01-01"
    assert result["to_date"] == "2024-01-02"
    assert result["usage_data"] == []


@pytest.mark.asyncio
async def test_get_usage_data_other_http_errors_still_raise(api_client):
    """Test that non-400 HTTP errors still raise exceptions."""
    # Mock the session and response
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.url = "https://api.example.com/usage/interval?consumerNumber=123&fromDate=2024-01-01&toDate=2024-01-02"
    
    # Mock the session context manager
    async def mock_context_manager(*args, **kwargs):
        return mock_response
    
    api_client._session.get.return_value.__aenter__ = mock_context_manager
    api_client._session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    api_client._access_token = "test_token"
    
    # Call the method and expect it to raise
    with pytest.raises(ClientResponseError):
        await api_client.get_usage_data("123", "2024-01-01", "2024-01-02")


@pytest.mark.asyncio
async def test_get_usage_data_success_response(api_client):
    """Test successful API response is processed normally."""
    # Mock the session and response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=[{"date": "2024-01-01", "usage": 10.5}])
    
    # Mock the session context manager
    async def mock_context_manager(*args, **kwargs):
        return mock_response
    
    api_client._session.get.return_value.__aenter__ = mock_context_manager
    api_client._session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    api_client._access_token = "test_token"
    
    # Call the method
    result = await api_client.get_usage_data("123", datetime(2024, 1, 1), datetime(2024, 1, 2))
    
    # Verify normal processing
    assert "error" not in result
    assert result["consumer_number"] == "123"
    assert result["from_date"] == "2024-01-01"
    assert result["to_date"] == "2024-01-02"
    assert len(result["usage_data"]) == 1
    assert result["usage_data"][0]["date"] == "2024-01-01"
    assert result["usage_data"][0]["usage"] == 10.5


@pytest.mark.asyncio
async def test_get_usage_data_logging_on_400_error(api_client, caplog):
    """Test that 400 errors are logged with detailed information."""
    # Mock the session and response
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.url = "https://api.example.com/usage/interval?consumerNumber=123&fromDate=2024-01-01&toDate=2024-01-02"
    
    error_data = {
        "message": "Invalid consumer number",
        "details": "Consumer number 123 is not valid for this account"
    }
    mock_response.json = AsyncMock(return_value=error_data)
    
    # Mock the session context manager
    async def mock_context_manager(*args, **kwargs):
        return mock_response
    
    api_client._session.get.return_value.__aenter__ = mock_context_manager
    api_client._session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    api_client._access_token = "test_token"
    
    # Call the method
    await api_client.get_usage_data("123", "2024-01-01", "2024-01-02")
    
    # Verify error logging
    assert "400 Bad Request for usage data" in caplog.text
    assert "Consumer: 123" in caplog.text
    assert "Date Range: 2024-01-01 to 2024-01-02" in caplog.text
    assert "Error: Invalid consumer number" in caplog.text
    assert "Details: Consumer number 123 is not valid for this account" in caplog.text
    assert "URL: https://api.example.com/usage/interval" in caplog.text
