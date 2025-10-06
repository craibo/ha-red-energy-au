# Red Energy API Response Structure

> Last Updated: 2025-10-06
> 
> This document defines the actual API response structures returned by the Red Energy API and how they map to our internal data model.

## Overview

The Red Energy API returns data in a specific structure that differs from typical REST API conventions. This document serves as the authoritative reference for understanding and validating API responses.

---

## 1. Properties/Accounts Response

### Endpoint
`GET /api/properties` or similar endpoint

### Actual API Response Structure

```json
[
  {
    "propertyPhysicalNumber": 82227160,
    "propertyNumber": "82227160.8490263",
    "accountNumber": 8490263,
    "address": {
      "unit": null,
      "unitType": null,
      "house": "27",
      "floor": null,
      "building": null,
      "street": "SUNNYSIDE CRES",
      "streetType": null,
      "suburb": "CASTLECRAG",
      "pobox": null,
      "townCity": null,
      "postcode": "2068",
      "state": "NSW",
      "country": null,
      "gentrackDisplayAddress": "27 SUNNYSIDE CRES, CASTLECRAG, NSW 2068",
      "displayAddresses": {
        "shortForm": "27 Sunnyside Crescent, Castlecrag",
        "shortFormAlt": "27 Sunnyside Crescent, Castlecrag",
        "extraShortForm": "27 Sunnyside Crescent",
        "longForm": "27 Sunnyside Crescent\nCastlecrag NSW 2068",
        "longFormAlt": "27 Sunnyside Crescent, Castlecrag, New South Wales 2 0 6 8"
      },
      "displayAddress": "27 SUNNYSIDE CRES\nCASTLECRAG  NSW  2068"
    },
    "consumers": [
      {
        "consumerNumber": 4235478511,
        "propertyNumber": "82227160.8490263",
        "accountNumber": 8490263,
        "entryDate": "2024-09-13",
        "finalDate": null,
        "status": "ON",
        "nmi": "4103296839",
        "nmiWithChecksum": "41032968395",
        "utility": "E",
        "meterType": "INTERVAL",
        "chargeClass": "RES",
        "solar": true,
        "lastBillDate": "2025-09-10",
        "nextBillDate": "2025-10-11",
        "latitude": -33.799045,
        "longitude": 151.212185,
        "balanceDollar": -75.0,
        "arrearsDollar": 0.0,
        "productName": "Qantas Red Saver",
        "linesCompany": "Ausgrid",
        "jurisdiction": "NSW",
        "billingFrequency": "MONTHLY"
      }
    ]
  }
]
```

### Key Field Mappings

| API Field | Our Internal Field | Notes |
|-----------|-------------------|-------|
| `accountNumber` | `id` | Primary identifier for the property |
| `consumers` | `services` | Array of services (electricity/gas) |
| No direct field | `name` | Built from `address.displayAddresses.shortForm` or address parts |
| `address` | `address` | Transformed to our address structure |

### Property ID Resolution

The integration looks for property ID in this order:
1. `data.get("id")`
2. `data.get("propertyId")`
3. `data.get("property_id")`
4. `data.get("accountNumber")` ✅ **Used by Red Energy API**
5. Generated from address if none found

---

## 2. Consumer/Service Structure

### Actual API Structure

```json
{
  "consumerNumber": 4235478511,
  "accountNumber": 8490263,
  "utility": "E",
  "status": "ON",
  "nmi": "4103296839",
  "meterType": "INTERVAL",
  "solar": true,
  "productName": "Qantas Red Saver",
  "linesCompany": "Ausgrid",
  "balanceDollar": -75.0
}
```

### Field Mappings

| API Field | Our Internal Field | Transformation |
|-----------|-------------------|----------------|
| `consumerNumber` | `consumer_number` | Convert to string |
| `utility` | `type` | `"E"` → `"electricity"`, `"G"` → `"gas"` |
| `status` | `active` | `"ON"` → `true`, `"OFF"` → `false` |

### Utility Code Mapping

```python
# API → Internal
"E" → "electricity"
"G" → "gas"
```

### Status Mapping

```python
# API → Internal
"ON" → True
"OFF" → False
```

---

## 3. Address Structure

### Actual API Structure

```json
{
  "unit": null,
  "unitType": null,
  "house": "27",
  "floor": null,
  "building": null,
  "street": "SUNNYSIDE CRES",
  "streetType": null,
  "suburb": "CASTLECRAG",
  "pobox": null,
  "townCity": null,
  "postcode": "2068",
  "state": "NSW",
  "country": null,
  "gentrackDisplayAddress": "27 SUNNYSIDE CRES, CASTLECRAG, NSW 2068",
  "displayAddresses": {
    "shortForm": "27 Sunnyside Crescent, Castlecrag",
    "shortFormAlt": "27 Sunnyside Crescent, Castlecrag",
    "extraShortForm": "27 Sunnyside Crescent",
    "longForm": "27 Sunnyside Crescent\nCastlecrag NSW 2068",
    "longFormAlt": "27 Sunnyside Crescent, Castlecrag, New South Wales 2 0 6 8"
  },
  "displayAddress": "27 SUNNYSIDE CRES\nCASTLECRAG  NSW  2068"
}
```

### Field Mappings

| API Field | Our Internal Field | Transformation |
|-----------|-------------------|----------------|
| `house` + `street` | `street` | Combined: `"27 SUNNYSIDE CRES"` |
| `suburb` | `city` | Direct mapping |
| `state` | `state` | Direct mapping |
| `postcode` | `postcode` | Direct mapping |

### Display Address Priority

For property names, we use in order:
1. `displayAddresses.shortForm` ✅ **Preferred** - "27 Sunnyside Crescent, Castlecrag"
2. `displayAddresses.extraShortForm` - "27 Sunnyside Crescent"
3. Built from `house` + `street` + `suburb`
4. Fallback: `"Property {id}"`

---

## 4. Customer Data Response

### Actual API Structure

```json
{
  "id": "CUST123456",
  "name": "John Smith",
  "email": "john.smith@example.com",
  "phone": "0412345678",
  "accounts": [...]
}
```

### Field Mappings

| API Field | Our Internal Field | Notes |
|-----------|-------------------|-------|
| `id` | `id` | Customer ID |
| `name` | `name` | Customer name |
| `email` | `email` | Contact email |
| `phone` / `phoneNumber` / `mobile` | `phone` | First non-null value |

---

## 5. Usage Data Response

### Actual API Response Structure

**Status:** Confirmed (2025-10-06)

The Red Energy API `/usage/interval` endpoint returns **daily summaries** with half-hourly interval data:

**API Response Format:**
```json
[
  {
    "usageDate": "2025-09-06",
    "halfHours": [
      {
        "intervalStart": "2025-09-06T00:00:00+10:00",
        "primaryConsumptionTariffComponent": "OFFPEAK",
        "consumptionKwh": 0.128,
        "consumptionDollar": 0.03,
        "consumptionDollarIncGst": 0.0346,
        "generationKwh": 0.0,
        "generationDollar": 0.0,
        "demandDetail": { ... },
        "isPricingReliable": true,
        "isPricingAvailable": true
      },
      // ... 47 more half-hour intervals (48 total per day)
    ],
    "maxDemandDetail": { ... },
    "carbonEmissionTonne": 0.0057,
    "minTemperatureC": 0.0,
    "maxTemperatureC": 0.0,
    "isPricingReliable": true,
    "unreliablePricingExplanation": null,
    "numUnreliablyPricedIntervals": 0,
    "quality": "Actual",
    "isConsumptionDollarGstInclusive": false,
    "consumptionDollar": 1.65,     // Daily total (excl GST)
    "generationDollar": -0.3279,   // Daily solar credit
    "hasUnpricedUsage": false,
    "numUnpricedIntervals": 0
  },
  // ... more days
]
```

**Key Structure Elements:**
- **Array of daily summaries** (30 items for 30-day request)
- Each day contains:
  - `usageDate`: Date in YYYY-MM-DD format
  - `halfHours`: Array of 48 half-hourly intervals
  - `consumptionDollar`: Daily total consumption cost (excl GST)
  - `generationDollar`: Daily solar generation credit (negative value)
  - `carbonEmissionTonne`: Daily carbon emissions
  - Various quality/reliability indicators

**Half-Hour Interval Fields:**
- `intervalStart`: ISO 8601 timestamp
- `consumptionKwh`: Consumption in kWh for this interval
- `consumptionDollar`: Cost for this interval (excl GST)
- `consumptionDollarIncGst`: Cost including GST
- `generationKwh`: Solar generation in kWh (if applicable)
- `generationDollar`: Solar generation credit
- `primaryConsumptionTariffComponent`: Tariff rate (OFFPEAK, SHOULDER, PEAK)
- `demandDetail`: Demand charge information

### Internal Expected Structure

Our validation layer expects this normalized format:

```json
{
  "consumer_number": "4235478511",
  "from_date": "2025-09-06",
  "to_date": "2025-10-06",
  "usage_data": [
    {
      "date": "2025-09-06",
      "usage": 12.5,
      "cost": 3.37
    },
    {
      "date": "2025-09-07",
      "usage": 14.2,
      "cost": 3.83
    }
  ],
  "total_usage": 26.7,
  "total_cost": 7.20
}
```

### API Transformation

The `api.py` module includes two transformation methods that convert Red Energy's format into our internal structure:

**1. `_transform_usage_data()`** - Converts overall API structure:
- **List format**: Wraps list in object with consumer_number and date range
- Calls `_normalize_usage_entry()` for each daily summary
- Returns structure with metadata (consumer_number, from_date, to_date, usage_data)

**2. `_normalize_usage_entry()`** - Aggregates daily data:
- **Date**: Extracts from `usageDate` field
- **Usage (kWh)**: Sums `consumptionKwh` from all 48 half-hour intervals in `halfHours` array
- **Cost**: Combines `consumptionDollar` + `generationDollar` for net daily cost
  - `consumptionDollar`: Daily consumption cost (excl GST)
  - `generationDollar`: Solar generation credit (negative value)
  - Net cost accounts for solar offsets automatically
- **Unit**: Always "kWh"

**Transformation Process:**
1. API returns 30 daily summaries, each with 48 half-hourly intervals
2. For each day:
   - Extract `usageDate` as the date
   - Sum all `consumptionKwh` values from `halfHours` array (48 intervals)
   - Calculate net cost: `consumptionDollar` + `generationDollar`
3. Result: 30 normalized daily entries with date, total usage, net cost

### Field Requirements

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `consumer_number` | string | Yes | Must match consumer from property |
| `usage_data` | array | Yes | Array of daily usage entries |
| `usage_data[].date` | string | Yes | ISO 8601 date format |
| `usage_data[].usage` | number | Yes | kWh or MJ |
| `usage_data[].cost` | number | Yes | Dollar amount |

---

## 6. Validation Rules

### Property Validation

```python
# Required fields
- accountNumber (becomes id)
- address (object)
- consumers (array)

# Optional fields
- propertyNumber
- propertyPhysicalNumber
```

### Consumer/Service Validation

```python
# Required fields
- consumerNumber
- utility ("E" or "G")

# Optional fields (with defaults)
- status (default: "ON")
- accountNumber
```

### Address Validation

```python
# Required fields
- At least one of: house, street, suburb
- state
- postcode

# Optional fields
- unit, unitType, floor, building
- displayAddresses
```

---

## 7. Common Issues and Solutions

### Issue 1: "No accounts found" or "Skipping account with invalid ID"

**Cause:** Config flow receives raw API data without validation, looking for `id` field that doesn't exist (API has `accountNumber`)

**Solution:** 
- Always validate API responses in `validate_input()` before using
- Call `validate_properties_data()` to transform `accountNumber` → `id`
- Ensure validation handles both `consumers` (Red Energy) and `services` (generic)

### Issue 2: Property ID mismatch

**Cause:** Config has `"0"` but API returns actual account numbers

**Solution:** 
- Always use `accountNumber` from API
- Convert to string for consistent comparison
- Config migration v4 auto-fixes old configs

### Issue 3: Service not detected

**Cause:** Looking for `type: "electricity"` but API has `utility: "E"`

**Solution:** Map utility codes:
```python
if utility == "E":
    service_type = "electricity"
elif utility == "G":
    service_type = "gas"
```

### Issue 4: "Usage data must be a dictionary" validation error

**Cause:** The Red Energy API `/usage/interval` endpoint returns data in various formats (often a list, not a dict), which doesn't match the validator's expected structure.

**Solution:** 
- The `api.py` module now includes `_transform_usage_data()` to handle multiple API formats
- Automatically wraps list responses with required metadata
- Extracts nested data from various field name variations
- Returns empty structure for None/empty responses
- See Section 5 "API Transformation" for details

**Fixed in:** 2025-10-06

### Issue 5: "Usage entry missing date" validation error

**Cause:** Red Energy API returns **daily summaries** with half-hourly intervals in a nested structure:
- Each day has `usageDate` (not `date`)
- Usage data is in `halfHours` array (48 half-hourly intervals)
- Costs are aggregated at day level (`consumptionDollar`, `generationDollar`)

**Solution:**
- Updated `_normalize_usage_entry()` to handle Red Energy's actual structure:
  - Extracts `usageDate` as the date
  - Sums all `consumptionKwh` values from `halfHours` array
  - Combines consumption and generation costs for net daily cost
  - Properly handles solar generation credits (negative values)
- See Section 5 "API Transformation" for complete details

**Fixed in:** 2025-10-06

---

## 8. Data Transformation Examples

### Example 1: Property Transformation

**Input (API):**
```json
{
  "accountNumber": 8490263,
  "address": {
    "house": "27",
    "street": "SUNNYSIDE CRES",
    "suburb": "CASTLECRAG",
    "state": "NSW",
    "postcode": "2068",
    "displayAddresses": {
      "shortForm": "27 Sunnyside Crescent, Castlecrag"
    }
  },
  "consumers": [...]
}
```

**Output (Internal):**
```json
{
  "id": "8490263",
  "name": "27 Sunnyside Crescent, Castlecrag",
  "address": {
    "street": "27 SUNNYSIDE CRES",
    "city": "CASTLECRAG",
    "state": "NSW",
    "postcode": "2068"
  },
  "services": [...]
}
```

### Example 2: Consumer Transformation

**Input (API):**
```json
{
  "consumerNumber": 4235478511,
  "utility": "E",
  "status": "ON"
}
```

**Output (Internal):**
```json
{
  "type": "electricity",
  "consumer_number": "4235478511",
  "active": true
}
```

---

## 9. Version History

### v4 (2025-10-06)
- ✅ Added support for `consumers` array (vs `services`)
- ✅ Added `utility` → `type` mapping
- ✅ Added `status` → `active` mapping
- ✅ Added `consumerNumber` support
- ✅ Added `suburb` → `city` mapping
- ✅ Added `displayAddresses.shortForm` for property names
- ✅ Auto-select all accounts by default

### v3 (Previous)
- Added performance optimizations
- Added device management

### v2 (Previous)
- Added advanced sensors
- Added polling options

### v1 (Initial)
- Basic property and service support
- Expected different API structure

---

## 10. Testing Checklist

When updating API response handling:

- [ ] Test with single property
- [ ] Test with multiple properties
- [ ] Test with electricity only
- [ ] Test with gas only
- [ ] Test with both utilities
- [ ] Test with inactive service (status: "OFF")
- [ ] Test with missing optional fields
- [ ] Test property name generation
- [ ] Test address parsing with unit number
- [ ] Test address parsing without house number
- [ ] Verify entity IDs are friendly
- [ ] Verify all IDs are strings for comparison

---

## 11. References

- Integration: `custom_components/red_energy/`
- Validation: `custom_components/red_energy/data_validation.py`
- API Client: `custom_components/red_energy/api.py`
- Config Flow: `custom_components/red_energy/config_flow.py`
- Migration: `custom_components/red_energy/config_migration.py`

---

## 12. Future Considerations

### Potential API Changes to Watch For

1. **New Utility Types**: Currently only `"E"` and `"G"` - watch for new codes
2. **Additional Status Values**: Currently only `"ON"` and `"OFF"` - watch for `"PENDING"`, `"SUSPENDED"`, etc.
3. **New Address Fields**: API may add fields like `streetNumber`, `streetName` separately
4. **Multiple Meters**: Some properties may have multiple meters per utility type
5. **Solar Feed-in Data**: Consider separate handling for solar generation vs consumption

### Recommended Improvements

1. Cache API responses to reduce API calls
2. Add retry logic for failed API calls
3. Implement exponential backoff
4. Add API rate limiting
5. Monitor for API deprecation notices
6. Add support for real-time usage data if API provides websockets

