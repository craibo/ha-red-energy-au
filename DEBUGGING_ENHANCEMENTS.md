# Debugging Enhancements - v1.5.4

## Issue
**Error:** "No usage data retrieved for any configured services"

This error occurs when the coordinator successfully authenticates and fetches property data, but cannot match properties to collect usage data. The root cause is likely an **ID mismatch** between `selected_accounts` (stored during config flow) and property IDs generated during updates.

## Solution Implemented

Added comprehensive INFO-level logging throughout the coordinator and data validation to diagnose the exact issue.

### Files Modified

#### 1. `custom_components/red_energy/coordinator.py`

**Added Logging Sections:**

**A. Raw API Responses**
```python
_LOGGER.info("=" * 80)
_LOGGER.info("RAW CUSTOMER API RESPONSE:")
_LOGGER.info("Type: %s", type(raw_customer_data))
_LOGGER.info("Data: %s", raw_customer_data)
_LOGGER.info("=" * 80)
```
- Shows exact data structure returned by Red Energy API
- Helps identify available field names
- Logs customer and properties responses separately

**B. Validated Data**
```python
_LOGGER.info("Validated customer data - ID: %s, Name: %s", ...)
_LOGGER.info("Validated %d properties:", len(self._properties))
for prop in self._properties:
    _LOGGER.info("  - Property ID: %s, Name: %s, Services: %s", ...)
```
- Shows IDs generated during validation
- Lists all available properties with their services

**C. Configuration Details**
```python
_LOGGER.info("COORDINATOR CONFIGURATION:")
_LOGGER.info("Selected accounts: %s", self.selected_accounts)
_LOGGER.info("Configured services: %s", self.services)
```
- Shows what accounts were selected during setup
- Shows what services are configured

**D. Property Matching**
```python
_LOGGER.info("Processing property: ID='%s', Name='%s'", property_id, property_name)

if property_id not in self.selected_accounts:
    _LOGGER.warning(
        "Property '%s' (ID: %s) not in selected_accounts %s - SKIPPING",
        ...
    )
else:
    _LOGGER.info("Property '%s' (ID: %s) MATCHED - fetching usage data", ...)
```
- Shows each property being processed
- Clearly indicates which are skipped and why
- Shows the ID comparison

**E. Service Processing**
```python
_LOGGER.info("  Processing service: type=%s, consumer_number=%s, active=%s", ...)

if not consumer_number:
    _LOGGER.warning("    Service %s has no consumer_number - SKIPPING", ...)

if service_type not in self.services:
    _LOGGER.info("    Service %s not in configured services %s - SKIPPING", ...)
```
- Shows each service being evaluated
- Explains why services are skipped

**F. Usage Data Fetching**
```python
_LOGGER.info("    Calling API get_usage_data: consumer=%s, from=%s, to=%s", ...)
_LOGGER.info("    Raw usage API response type: %s", type(raw_usage))
_LOGGER.info("    Raw usage API response: %s", raw_usage)
```
- Shows API calls being made
- Logs raw usage responses
- Helps identify usage data structure issues

**G. Summary Statistics**
```python
_LOGGER.info("DATA COLLECTION SUMMARY:")
_LOGGER.info("Total properties processed: %d", len(self._properties))
_LOGGER.info("Properties matched: %d", matched_properties)
_LOGGER.info("Properties skipped: %d", skipped_properties)
_LOGGER.info("Properties with usage data: %d", len(usage_data))
```
- Clear summary of what happened
- Makes it easy to spot the problem

**H. Enhanced Error Message**
```python
error_msg = (
    f"No usage data retrieved for any configured services. "
    f"Processed {len(self._properties)} properties, "
    f"matched {matched_properties}, skipped {skipped_properties}. "
    f"Selected accounts: {self.selected_accounts}, "
    f"Available property IDs: {[p.get('id') for p in self._properties]}"
)
```
- Shows exactly what IDs were expected vs found
- Makes the mismatch obvious

#### 2. `custom_components/red_energy/data_validation.py`

**Added Property Validation Logging:**
```python
_LOGGER.info("Validating %d properties from API", len(data))

for i, property_data in enumerate(data):
    _LOGGER.info("Validating property %d: %s", i, property_data)
    validated_property = validate_single_property(property_data)
    _LOGGER.info("  ✓ Property %d validated successfully: ID=%s, Name=%s", ...)
```
- Shows raw property data before validation
- Shows generated IDs after validation
- Helps identify if synthetic ID generation is inconsistent

## What to Look For in Logs

When you run the integration with these enhancements, look for:

### 1. **ID Mismatch**
```
Selected accounts: ['property_123_Main_Street']
...
Processing property: ID='property_124_Main_Street', Name='Main Residence'
Property 'Main Residence' (ID: property_124_Main_Street) not in selected_accounts ['property_123_Main_Street'] - SKIPPING
```
→ **Indicates synthetic ID generation is inconsistent**

### 2. **No Real IDs in API**
```
RAW PROPERTIES API RESPONSE:
Data: [{'name': 'Main Residence', 'address': {...}, 'services': [...]}]
```
→ **No 'id' field means synthetic IDs are being generated**

### 3. **Service Mismatch**
```
Processing service: type=electricity, consumer_number=None, active=True
Service electricity has no consumer_number - SKIPPING
```
→ **Properties have no consumer numbers**

### 4. **All Properties Skipped**
```
DATA COLLECTION SUMMARY:
Total properties processed: 1
Properties matched: 0
Properties skipped: 1
```
→ **Confirms ID mismatch is the issue**

## Next Steps Based on Logs

### If Synthetic IDs are Inconsistent:
1. Check if API response structure varies between calls
2. Implement deterministic ID generation using stable fields
3. Consider storing alternative matching keys

### If No Consumer Numbers:
1. API might not return service details
2. Need to call different endpoint for service data
3. May need to adjust property/service data structure

### If Services Type Mismatch:
1. Check if API returns "Electricity" vs "electricity"
2. Normalize service types in validation
3. Update configured services list

## Benefits of Enhanced Logging

1. **Precise Diagnosis**: See exactly where and why matching fails
2. **API Response Visibility**: Understand actual data structure from Red Energy
3. **Configuration Verification**: Confirm what was stored during setup
4. **Step-by-Step Tracking**: Follow data flow through entire update process
5. **Quick Fixes**: Clear indication of what needs to be adjusted

## Version
- Updated from `1.5.3` to `1.5.4`
- All logging at INFO level (visible by default)
- Uses visual separators (===) for easy reading
- Checkmarks (✓/✗) for quick status identification

