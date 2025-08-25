"""Data validation utilities for Red Energy integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

_LOGGER = logging.getLogger(__name__)


class DataValidationError(Exception):
    """Exception raised when data validation fails."""


def validate_customer_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate customer data from Red Energy API."""
    if not isinstance(data, dict):
        raise DataValidationError("Customer data must be a dictionary")
    
    required_fields = ["id", "name", "email"]
    for field in required_fields:
        if field not in data:
            _LOGGER.warning("Missing required customer field: %s", field)
            # Provide default values for missing fields
            if field == "id":
                data[field] = "unknown"
            elif field == "name":
                data[field] = "Red Energy Customer"
            elif field == "email":
                data[field] = "unknown@redenergy.com.au"
    
    # Sanitize data
    validated_data = {
        "id": str(data["id"]),
        "name": str(data["name"]).strip(),
        "email": str(data["email"]).strip().lower(),
    }
    
    # Add optional fields if present
    if "phone" in data:
        validated_data["phone"] = str(data["phone"]).strip()
    
    _LOGGER.debug("Validated customer data: %s", validated_data["name"])
    return validated_data


def validate_properties_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate properties data from Red Energy API."""
    if not isinstance(data, list):
        raise DataValidationError("Properties data must be a list")
    
    if not data:
        raise DataValidationError("No properties found in response")
    
    validated_properties = []
    
    for i, property_data in enumerate(data):
        try:
            validated_property = validate_single_property(property_data)
            validated_properties.append(validated_property)
        except DataValidationError as err:
            _LOGGER.error("Property %d validation failed: %s", i, err)
            # Skip invalid properties rather than failing completely
            continue
    
    if not validated_properties:
        raise DataValidationError("No valid properties after validation")
    
    _LOGGER.debug("Validated %d properties", len(validated_properties))
    return validated_properties


def validate_single_property(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a single property."""
    if not isinstance(data, dict):
        raise DataValidationError("Property data must be a dictionary")
    
    # Required fields
    if "id" not in data:
        raise DataValidationError("Property missing required 'id' field")
    
    validated_property = {
        "id": str(data["id"]),
        "name": data.get("name", f"Property {data['id']}"),
        "address": validate_address(data.get("address", {})),
        "services": validate_services(data.get("services", [])),
    }
    
    return validated_property


def validate_address(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate address data."""
    if not isinstance(data, dict):
        data = {}
    
    return {
        "street": data.get("street", "").strip(),
        "city": data.get("city", "").strip(),
        "state": data.get("state", "").strip(),
        "postcode": data.get("postcode", "").strip(),
    }


def validate_services(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate services data."""
    if not isinstance(data, list):
        return []
    
    validated_services = []
    
    for service in data:
        try:
            validated_service = validate_single_service(service)
            validated_services.append(validated_service)
        except DataValidationError as err:
            _LOGGER.warning("Service validation failed: %s", err)
            continue
    
    return validated_services


def validate_single_service(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a single service."""
    if not isinstance(data, dict):
        raise DataValidationError("Service data must be a dictionary")
    
    service_type = data.get("type", "").lower()
    if service_type not in ["electricity", "gas"]:
        raise DataValidationError(f"Invalid service type: {service_type}")
    
    consumer_number = data.get("consumer_number")
    if not consumer_number:
        raise DataValidationError("Service missing consumer_number")
    
    return {
        "type": service_type,
        "consumer_number": str(consumer_number),
        "active": bool(data.get("active", True)),
    }


def validate_usage_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate usage data from Red Energy API."""
    if not isinstance(data, dict):
        raise DataValidationError("Usage data must be a dictionary")
    
    # Required fields
    required_fields = ["consumer_number", "usage_data"]
    for field in required_fields:
        if field not in data:
            raise DataValidationError(f"Usage data missing required field: {field}")
    
    usage_entries = data["usage_data"]
    if not isinstance(usage_entries, list):
        raise DataValidationError("usage_data must be a list")
    
    validated_entries = []
    total_usage = 0.0
    total_cost = 0.0
    
    for entry in usage_entries:
        try:
            validated_entry = validate_usage_entry(entry)
            validated_entries.append(validated_entry)
            total_usage += validated_entry["usage"]
            total_cost += validated_entry["cost"]
        except DataValidationError as err:
            _LOGGER.warning("Usage entry validation failed: %s", err)
            continue
    
    return {
        "consumer_number": str(data["consumer_number"]),
        "from_date": data.get("from_date", ""),
        "to_date": data.get("to_date", ""),
        "usage_data": validated_entries,
        "total_usage": round(total_usage, 2),
        "total_cost": round(total_cost, 2),
    }


def validate_usage_entry(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a single usage data entry."""
    if not isinstance(data, dict):
        raise DataValidationError("Usage entry must be a dictionary")
    
    # Validate date
    date_str = data.get("date")
    if not date_str:
        raise DataValidationError("Usage entry missing date")
    
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as err:
        raise DataValidationError(f"Invalid date format: {date_str}") from err
    
    # Validate usage (must be numeric)
    usage = data.get("usage", 0)
    try:
        usage = float(usage)
        if usage < 0:
            _LOGGER.warning("Negative usage value: %s, setting to 0", usage)
            usage = 0.0
    except (ValueError, TypeError) as err:
        raise DataValidationError(f"Invalid usage value: {usage}") from err
    
    # Validate cost (must be numeric)
    cost = data.get("cost", 0)
    try:
        cost = float(cost)
        if cost < 0:
            _LOGGER.warning("Negative cost value: %s, setting to 0", cost)
            cost = 0.0
    except (ValueError, TypeError) as err:
        raise DataValidationError(f"Invalid cost value: {cost}") from err
    
    return {
        "date": date_str,
        "usage": round(usage, 3),
        "cost": round(cost, 2),
        "unit": data.get("unit", "kWh"),
    }


def sanitize_sensor_name(name: str) -> str:
    """Sanitize a name for use as a sensor name."""
    if not name:
        return "Unknown"
    
    # Remove/replace problematic characters
    sanitized = name.replace("/", "_").replace("\\", "_")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in " -_.")
    
    # Limit length
    if len(sanitized) > 50:
        sanitized = sanitized[:47] + "..."
    
    return sanitized.strip()


def validate_config_data(config: Dict[str, Any]) -> None:
    """Validate configuration data."""
    required_fields = ["username", "password", "client_id"]
    
    for field in required_fields:
        if field not in config:
            raise DataValidationError(f"Configuration missing required field: {field}")
        
        value = config[field]
        if not value or not isinstance(value, str) or not value.strip():
            raise DataValidationError(f"Configuration field '{field}' must be a non-empty string")
    
    # Validate email format for username
    username = config["username"]
    if "@" not in username or "." not in username.split("@")[-1]:
        raise DataValidationError("Username must be a valid email address")
    
    # Validate client_id format (should be non-empty string)
    client_id = config["client_id"]
    if len(client_id) < 5:
        raise DataValidationError("Client ID appears too short - verify it was captured correctly")
    
    _LOGGER.debug("Configuration validation passed")