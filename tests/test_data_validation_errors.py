"""Tests for data validation error handling."""
import pytest
from custom_components.red_energy.data_validation import (
    validate_usage_data,
    DataValidationError
)


def test_validate_usage_data_with_error_response():
    """Test that error responses are passed through without validation."""
    error_response = {
        "error": True,
        "error_type": "bad_request",
        "error_message": "Invalid consumer number",
        "error_details": "Consumer number 123 is not valid",
        "consumer_number": "123",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": []
    }
    
    result = validate_usage_data(error_response)
    
    # Verify error response is returned unchanged
    assert result == error_response
    assert result["error"] is True
    assert result["error_type"] == "bad_request"
    assert result["error_message"] == "Invalid consumer number"
    assert result["error_details"] == "Consumer number 123 is not valid"


def test_validate_usage_data_with_error_response_missing_fields():
    """Test error response handling with missing error fields."""
    error_response = {
        "error": True,
        "consumer_number": "123",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": []
    }
    
    result = validate_usage_data(error_response)
    
    # Verify error response is returned unchanged even with missing fields
    assert result == error_response
    assert result["error"] is True
    assert "error_type" not in result
    assert "error_message" not in result
    assert "error_details" not in result


def test_validate_usage_data_with_normal_data():
    """Test that normal usage data is validated as usual."""
    normal_data = {
        "consumer_number": "1234567890",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": [
            {
                "date": "2024-01-01",
                "usage": 15.5,
                "cost": 25.50,
                "unit": "kWh"
            }
        ]
    }
    
    result = validate_usage_data(normal_data)
    
    # Verify normal validation occurs
    assert "error" not in result
    assert result["consumer_number"] == "1234567890"
    assert result["from_date"] == "2024-01-01"
    assert result["to_date"] == "2024-01-02"
    assert len(result["usage_data"]) == 1
    assert result["usage_data"][0]["date"] == "2024-01-01"
    assert result["usage_data"][0]["usage"] == 15.5
    assert result["usage_data"][0]["cost"] == 25.50
    assert result["total_usage"] == 15.5
    assert result["total_cost"] == 25.50


def test_validate_usage_data_with_empty_usage_data():
    """Test error response with empty usage data."""
    error_response = {
        "error": True,
        "error_type": "bad_request",
        "error_message": "No data available",
        "error_details": "No usage data found for the specified period",
        "consumer_number": "123",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": []
    }
    
    result = validate_usage_data(error_response)
    
    # Verify error response is returned unchanged
    assert result == error_response
    assert result["error"] is True
    assert result["usage_data"] == []


def test_validate_usage_data_with_complex_error_response():
    """Test error response with complex error details."""
    error_response = {
        "error": True,
        "error_type": "bad_request",
        "error_message": "Validation failed",
        "error_details": {
            "field_errors": {
                "consumer_number": "Invalid format",
                "date_range": "Date range too large"
            },
            "suggestions": [
                "Use a valid consumer number",
                "Reduce the date range to 90 days or less"
            ]
        },
        "consumer_number": "invalid",
        "from_date": "2024-01-01",
        "to_date": "2024-12-31",
        "usage_data": []
    }
    
    result = validate_usage_data(error_response)
    
    # Verify complex error response is returned unchanged
    assert result == error_response
    assert result["error"] is True
    assert result["error_type"] == "bad_request"
    assert result["error_message"] == "Validation failed"
    assert isinstance(result["error_details"], dict)
    assert "field_errors" in result["error_details"]
    assert "suggestions" in result["error_details"]


def test_validate_usage_data_error_response_preserves_all_fields():
    """Test that all fields in error response are preserved."""
    error_response = {
        "error": True,
        "error_type": "bad_request",
        "error_message": "Test error",
        "error_details": "Test details",
        "consumer_number": "123",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": [],
        "additional_field": "should_be_preserved",
        "nested_field": {
            "key": "value"
        }
    }
    
    result = validate_usage_data(error_response)
    
    # Verify all fields are preserved
    assert result == error_response
    assert result["additional_field"] == "should_be_preserved"
    assert result["nested_field"]["key"] == "value"


def test_validate_usage_data_mixed_error_and_normal_data():
    """Test validation with mixed error and normal data structures."""
    # This test ensures that if somehow both error and normal data are present,
    # the error flag takes precedence
    mixed_data = {
        "error": True,
        "error_type": "bad_request",
        "error_message": "Error occurred",
        "error_details": "Some error details",
        "consumer_number": "123",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": [
            {
                "date": "2024-01-01",
                "usage": 10.0,
                "cost": 15.00
            }
        ]
    }
    
    result = validate_usage_data(mixed_data)
    
    # Verify error response is returned unchanged (error flag takes precedence)
    assert result == mixed_data
    assert result["error"] is True
    assert result["error_type"] == "bad_request"
    # Normal validation should not have occurred
    assert "total_usage" not in result
    assert "total_cost" not in result


def test_validate_usage_data_error_response_logging(caplog):
    """Test that error responses generate appropriate log messages."""
    error_response = {
        "error": True,
        "error_type": "bad_request",
        "error_message": "Test error message",
        "error_details": "Test error details",
        "consumer_number": "123",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": []
    }
    
    validate_usage_data(error_response)
    
    # Verify warning log was generated
    assert "Skipping validation for error response" in caplog.text
    assert "Test error message" in caplog.text
    assert "Test error details" in caplog.text


def test_validate_usage_data_error_response_with_missing_error_fields_logging(caplog):
    """Test error response logging with missing error fields."""
    error_response = {
        "error": True,
        "consumer_number": "123",
        "from_date": "2024-01-01",
        "to_date": "2024-01-02",
        "usage_data": []
    }
    
    validate_usage_data(error_response)
    
    # Verify warning log was generated with default values
    assert "Skipping validation for error response" in caplog.text
    assert "Unknown error" in caplog.text
    assert "No details" in caplog.text
