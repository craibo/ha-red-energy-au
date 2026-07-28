"""Tests for data validation error handling."""
import pytest
from custom_components.red_energy.data_validation import (
    validate_usage_data,
    validate_usage_entry,
    validate_address,
    validate_properties_data,
    validate_single_service,
    validate_rates,
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


def test_validate_address_handles_none_values():
    """Test that address with null/None fields does not raise AttributeError."""
    address_with_nulls = {
        "house": None,
        "street": None,
        "suburb": None,
        "city": None,
        "state": None,
        "postcode": None,
    }
    result = validate_address(address_with_nulls)
    assert result["street"] == ""
    assert result["city"] == ""
    assert result["state"] == ""
    assert result["postcode"] == ""


def test_validate_address_handles_partial_none_values():
    """Test address with some None and some string values."""
    address = {
        "house": None,
        "street": "SUNNYSIDE CRES",
        "suburb": "CASTLECRAG",
        "state": "NSW",
        "postcode": "2068",
    }
    result = validate_address(address)
    assert result["street"] == "SUNNYSIDE CRES"
    assert result["city"] == "CASTLECRAG"
    assert result["state"] == "NSW"
    assert result["postcode"] == "2068"


def test_validate_usage_entry_allday_tariff_no_warning(caplog):
    """ALLDAY (Anytime) tariff has no ToU breakdown — no WARNING should be logged."""
    entry = {
        "date": "2026-03-24",
        "usage": 13.538,
        "cost": 3.79,
        "import_usage": 13.538,
        "export_usage": 0.0,
        "import_cost": 3.79,
        "export_credit": 0.0,
        "net_cost": 3.79,
        "peak_import_usage": 0.0,
        "offpeak_import_usage": 0.0,
        "shoulder_import_usage": 0.0,
        "peak_export_usage": 0.0,
        "offpeak_export_usage": 0.0,
        "shoulder_export_usage": 0.0,
        "_breakdown_available": False,
    }
    import logging
    with caplog.at_level(logging.WARNING, logger="custom_components.red_energy.data_validation"):
        validate_usage_entry(entry)

    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warning_records, f"Unexpected WARNING(s) for ALLDAY tariff: {[r.message for r in warning_records]}"


def test_validate_usage_entry_tou_mismatch_still_warns(caplog):
    """A genuine ToU breakdown mismatch (breakdown_available=True) must still log a WARNING."""
    entry = {
        "date": "2026-03-24",
        "usage": 13.538,
        "cost": 3.79,
        "import_usage": 13.538,
        "export_usage": 0.0,
        "import_cost": 3.79,
        "export_credit": 0.0,
        "net_cost": 3.79,
        # Deliberately wrong sum (5.0 != 13.538)
        "peak_import_usage": 2.0,
        "offpeak_import_usage": 2.0,
        "shoulder_import_usage": 1.0,
        "peak_export_usage": 0.0,
        "offpeak_export_usage": 0.0,
        "shoulder_export_usage": 0.0,
        "_breakdown_available": True,
    }
    import logging
    with caplog.at_level(logging.WARNING, logger="custom_components.red_energy.data_validation"):
        validate_usage_entry(entry)

    assert any("breakdown mismatch" in r.message for r in caplog.records if r.levelno >= logging.WARNING)


def test_validate_properties_data_handles_address_with_none_house():
    """Test property validation when API returns house: null (e.g. unit-only address)."""
    raw_properties = [
        {
            "accountNumber": 1000001,
            "address": {
                "house": None,
                "street": "SUNNYSIDE CRES",
                "suburb": "CASTLECRAG",
                "state": "NSW",
                "postcode": "2068",
            },
            "consumers": [
                {
                    "consumerNumber": 3000003,
                    "utility": "E",
                    "status": "ON",
                }
            ],
        }
    ]
    result = validate_properties_data(raw_properties)
    assert len(result) == 1
    assert result[0]["id"] == "1000001"
    assert result[0]["address"]["street"] == "SUNNYSIDE CRES"
    assert result[0]["address"]["city"] == "CASTLECRAG"
    assert result[0]["address"]["state"] == "NSW"
    assert result[0]["address"]["postcode"] == "2068"


def test_validate_properties_data_shared_account_number_stays_distinct():
    """Two properties on one billing account share accountNumber but must
    still validate to distinct IDs (see GitHub issue #51)."""
    raw_properties = [
        {
            "accountNumber": 1001100,
            "propertyPhysicalNumber": 1111111,
            "address": {
                "street": "1 FIRST STREET",
                "suburb": "SUBURBIA",
                "state": "NSW",
                "postcode": "2000",
            },
            "consumers": [
                {
                    "consumerNumber": 2000001,
                    "utility": "E",
                    "status": "ON",
                }
            ],
        },
        {
            "accountNumber": 1001100,
            "propertyPhysicalNumber": 2222222,
            "address": {
                "street": "2 SECOND STREET",
                "suburb": "SUBURBIA",
                "state": "NSW",
                "postcode": "2000",
            },
            "consumers": [
                {
                    "consumerNumber": 2000002,
                    "utility": "E",
                    "status": "ON",
                }
            ],
        },
    ]
    result = validate_properties_data(raw_properties)
    assert len(result) == 2
    ids = {prop["id"] for prop in result}
    assert len(ids) == 2
    assert ids == {"1111111.1001100", "2222222.1001100"}


def test_validate_single_service_extracts_payment_type_description():
    """paymentTypeDetail.paymentTypeDescription must surface as a flat field."""
    raw_service = {
        "utility": "G",
        "consumerNumber": "4000004",
        "status": "ON",
        "paymentTypeDetail": {
            "paymentType": "DDB",
            "paymentTypeDescription": "DirectDebit Bank",
        },
    }
    result = validate_single_service(raw_service)
    assert result["paymentTypeDescription"] == "DirectDebit Bank"


def test_validate_single_service_extracts_promotion_desc():
    """currentPlan.promotionDesc must surface as a flat field."""
    raw_service = {
        "utility": "E",
        "consumerNumber": "3000003",
        "status": "ON",
        "currentPlan": {
            "promotionCode": "NEQ005",
            "promotionDesc": "Qantas Red Saver, 2 QFF Points per $1",
        },
    }
    result = validate_single_service(raw_service)
    assert result["promotionDesc"] == "Qantas Red Saver, 2 QFF Points per $1"


def test_validate_single_service_missing_nested_fields_omitted():
    """Missing paymentTypeDetail/currentPlan must not add empty keys."""
    raw_service = {
        "utility": "G",
        "consumerNumber": "4000004",
        "status": "ON",
    }
    result = validate_single_service(raw_service)
    assert "paymentTypeDescription" not in result
    assert "promotionDesc" not in result


def test_validate_single_service_extracts_rates():
    """currentPlan.rates must surface as a validated list on the service."""
    raw_service = {
        "utility": "E",
        "consumerNumber": "3000003",
        "status": "ON",
        "currentPlan": {
            "rates": [
                {
                    "rateCode": "80008279798P",
                    "rateDesc": "Peak",
                    "type": "PR",
                    "rateExclGstCents": 24.55,
                    "rateInclGstCents": 27.005,
                    "discountedRateExclGstInCents": 24.55,
                    "discountedRateInclGstInCents": 27.005,
                    "unit": "kWh",
                    "unitStepDesc": None,
                },
            ],
        },
    }
    result = validate_single_service(raw_service)
    assert len(result["rates"]) == 1
    rate = result["rates"][0]
    assert rate["rate_code"] == "80008279798P"
    assert rate["rate_desc"] == "Peak"
    assert rate["rate_incl_gst_dollars"] == pytest.approx(0.27005)
    assert rate["type"] == "PR"
    assert rate["unit"] == "kWh"
    assert rate["unit_step_desc"] is None


def test_validate_single_service_no_rates_defaults_to_empty_list():
    """Missing currentPlan/rates must default to an empty list, not KeyError."""
    raw_service = {
        "utility": "G",
        "consumerNumber": "4000004",
        "status": "ON",
    }
    result = validate_single_service(raw_service)
    assert result["rates"] == []


def test_validate_rates_handles_negative_solar_rate():
    """Solar feed-in rates are negative (a credit) - must not be rejected."""
    raw_rates = [
        {
            "rateCode": "80008279798GP",
            "rateDesc": "Solar",
            "type": "PR",
            "rateExclGstCents": -3.6364,
            "rateInclGstCents": -4,
            "discountedRateExclGstInCents": -3.6364,
            "discountedRateInclGstInCents": -4,
            "unit": "kWh",
            "unitStepDesc": None,
        },
    ]
    result = validate_rates(raw_rates)
    assert len(result) == 1
    assert result[0]["rate_incl_gst_dollars"] == pytest.approx(-0.04)


def test_validate_rates_handles_duplicate_rate_code_tiered_steps():
    """Tiered gas rates repeat rateCode across steps - all must be preserved."""
    raw_rates = [
        {
            "rateCode": "10009300825P",
            "rateDesc": "Anytime Step1",
            "type": "PSR1",
            "rateExclGstCents": 4.5,
            "rateInclGstCents": 4.95,
            "discountedRateExclGstInCents": 4.5,
            "discountedRateInclGstInCents": 4.95,
            "unit": "MJ",
            "unitStepDesc": "First 20.712 / day",
        },
        {
            "rateCode": "10009300825P",
            "rateDesc": "Anytime Step2",
            "type": "PSR1",
            "rateExclGstCents": 3.3,
            "rateInclGstCents": 3.63,
            "discountedRateExclGstInCents": 3.3,
            "discountedRateInclGstInCents": 3.63,
            "unit": "MJ",
            "unitStepDesc": "Next 20.384 / day",
        },
    ]
    result = validate_rates(raw_rates)
    assert len(result) == 2
    assert result[0]["rate_code"] == result[1]["rate_code"] == "10009300825P"
    assert result[0]["rate_desc"] == "Anytime Step1"
    assert result[1]["rate_desc"] == "Anytime Step2"


def test_validate_rates_skips_entries_missing_required_fields():
    """Entries missing rateCode or rateDesc must be skipped, not raise."""
    raw_rates = [
        {"rateDesc": "Missing code", "rateInclGstCents": 1.0},
        {"rateCode": "X1", "rateInclGstCents": 1.0},
        {"rateCode": "X2", "rateDesc": "Valid", "rateInclGstCents": 10.0},
    ]
    result = validate_rates(raw_rates)
    assert len(result) == 1
    assert result[0]["rate_code"] == "X2"


def test_validate_rates_handles_non_list_input():
    """Malformed rates field (not a list) must return an empty list, not raise."""
    assert validate_rates(None) == []
    assert validate_rates("not-a-list") == []
    assert validate_rates({}) == []
