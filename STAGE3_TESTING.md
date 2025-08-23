# Stage 3 Testing Guide: Core API Integration & Data Polling

## Overview
Stage 3 implements the complete data polling system with coordinators, real usage sensors, and comprehensive error handling.

## What's New in Stage 3

### Core Features:
- **DataUpdateCoordinator**: Manages polling and data updates every 5 minutes
- **Real Sensor Entities**: Usage, cost, and total usage sensors for each service
- **Data Validation**: Robust validation and error recovery for all API data
- **Diagnostics**: Comprehensive diagnostics for troubleshooting
- **Mock API Enhanced**: Realistic test data for electricity and gas services

### New Sensors Created:
For each account and service (electricity/gas), you'll get:
1. **Daily Usage Sensor**: Most recent day's usage (kWh/MJ)
2. **Total Cost Sensor**: 30-day total cost (AUD)
3. **Total Usage Sensor**: 30-day total usage (kWh/MJ)

## Testing Stage 3

### Step 1: Install Updated Integration
1. Copy the updated `custom_components/red_energy/` to your Home Assistant
2. Restart Home Assistant
3. Use existing Stage 2 credentials or configure new integration

### Step 2: Configuration Testing
Use the same mock credentials from Stage 2:
- **Username**: `test@example.com`
- **Password**: `testpass` 
- **Client ID**: `test-client-id-123`

### Step 3: Expected Behavior

**After Configuration:**
1. Integration should load successfully
2. Coordinator will start polling every 5 minutes
3. You should see multiple sensors appear:

**For Main Residence (Electricity):**
- `Main Residence Electricity Daily_Usage` (kWh)
- `Main Residence Electricity Total_Cost` (AUD)  
- `Main Residence Electricity Total_Usage` (kWh)

**For Main Residence (Gas):**
- `Main Residence Gas Daily_Usage` (MJ)
- `Main Residence Gas Total_Cost` (AUD)
- `Main Residence Gas Total_Usage` (MJ)

**For Investment Property (Electricity only):**
- `Investment Property Electricity Daily_Usage` (kWh)
- `Investment Property Electricity Total_Cost` (AUD)
- `Investment Property Electricity Total_Usage` (kWh)

### Step 4: Sensor Values Verification

**Expected Mock Data Values:**
- **Daily Usage**: ~25-45 kWh (electricity) or ~45-65 MJ (gas)
- **Total Usage**: ~750-1350 kWh/MJ (30 days)
- **Total Cost**: ~210-378 AUD (30 days at $0.28 rate)

**Sensor Attributes:**
Each sensor includes extra attributes:
- `consumer_number`: Service identifier
- `last_updated`: When data was last fetched
- `service_type`: electricity or gas
- `period`: "30 days" for totals
- `from_date` / `to_date`: Data range

### Step 5: Device Organization

**Device Grouping:**
- Sensors are organized by property (device)
- Each property shows manufacturer: "Red Energy"
- Model shows service type: "Electricity Service" / "Gas Service"

## Testing Error Scenarios

### 1. Invalid Credentials
- Try configuring with wrong password
- Should fail at setup with clear error message

### 2. Data Polling Issues
- Check Home Assistant logs for coordinator errors
- Should see retry attempts if mock API fails

### 3. Partial Data Loss
- Mock API handles missing data gracefully
- Individual sensor failures don't break entire integration

## Advanced Testing

### 1. Diagnostics
1. Go to **Settings** → **Devices & Services** → **Red Energy**
2. Click on integration → **Download Diagnostics**
3. Verify diagnostic data includes:
   - Customer info (sanitized)
   - Property details
   - Usage data summaries
   - API status

### 2. Device Diagnostics
1. Click on a property device → **Download Diagnostics**
2. Should show property-specific usage statistics

### 3. Options Flow
1. Integration → **Configure**  
2. Change service selection (electricity/gas)
3. Should update available sensors

## Expected Test Results

✅ **Stage 3 Complete** when:
- [ ] Integration loads with coordinator
- [ ] Multiple sensors appear (3 per service)
- [ ] Sensors show realistic mock usage data
- [ ] Sensors update every 5 minutes
- [ ] Device grouping by property works
- [ ] Diagnostics provide useful information
- [ ] Options flow updates sensor selection
- [ ] All 21 tests pass (`pytest tests/test_*.py -v`)

## Troubleshooting

**No sensors appear**: Check logs for coordinator setup errors
**Sensors show "unavailable"**: Check data validation errors in logs
**Wrong sensor values**: Verify mock API data structure
**Authentication fails**: Using wrong mock credentials

## Real API Notice

The integration currently uses mock data. To connect to the real Red Energy API:
1. Implement complete OAuth2 PKCE flow in `api.py`
2. Replace `MockRedEnergyAPI` with `RedEnergyAPI` in `coordinator.py`
3. Handle real authentication tokens and session management

## Next Stage Preview

Stage 4 will focus on:
- Real-time usage monitoring improvements
- Historical data visualization
- Energy cost optimization features
- Enhanced device management