# Stage 4 Testing Guide: Advanced Features & Enhancements

## Overview
Stage 4 adds advanced features including configurable polling, calculated sensors, service calls, energy dashboard integration, and comprehensive automation examples.

## What's New in Stage 4

### Core Enhancements:
- **Configurable Polling Intervals**: 1min, 5min, 15min, 30min, 1hour options
- **Advanced Calculated Sensors**: Daily average, monthly average, peak usage, efficiency rating
- **Service Calls**: Manual refresh, credential updates, data export
- **Energy Dashboard Integration**: Native HA Energy dashboard support
- **Comprehensive Automations**: 11 ready-to-use automation examples

### New Sensor Types:
When advanced sensors are enabled, you get 4 additional sensors per service:
1. **Daily Average Sensor**: Average daily usage over the data period
2. **Monthly Average Sensor**: Projected monthly usage based on 30-day data
3. **Peak Usage Sensor**: Highest single-day usage with date attribution
4. **Efficiency Rating Sensor**: 0-100% efficiency based on usage consistency

## Testing Stage 4

### Step 1: Enable Advanced Features
1. Go to **Settings** → **Devices & Services** → **Red Energy**
2. Click **Configure** on your Red Energy integration
3. Enable "Advanced Sensors"
4. Select preferred polling interval (test with 1min for faster testing)
5. Save changes

### Step 2: Verify Advanced Sensors
After enabling advanced sensors and restarting HA, check for new entities:

**For Main Residence Electricity (if enabled):**
- `Main Residence Electricity Daily_Average` (~25-30 kWh average)
- `Main Residence Electricity Monthly_Average` (~760-900 kWh projected)
- `Main Residence Electricity Peak_Usage` (~45 kWh max day)
- `Main Residence Electricity Efficiency` (~75-85% rating)

**Sensor Attributes to Verify:**
- **Daily Average**: `calculation_period` showing days used
- **Peak Usage**: `peak_date` and `peak_cost` attributes
- **Efficiency**: `usage_variation` (Low/Medium/High) and `mean_daily_usage`

### Step 3: Test Service Calls
Test the three service calls in **Developer Tools** → **Services**:

#### Manual Data Refresh
```yaml
service: red_energy.refresh_data
data: {}
```
**Expected**: All coordinators refresh, logs show "Manual data refresh requested"

#### Export Data  
```yaml
service: red_energy.export_data
data:
  format: json
  days: 7
```
**Expected**: Persistent notification appears with export summary

#### Update Credentials (Test with same credentials)
```yaml
service: red_energy.update_credentials
data:
  username: "test@example.com"
  password: "testpass"
  client_id: "test-client-id-123"
```
**Expected**: Logs show "Successfully updated credentials"

### Step 4: Test Polling Interval Changes
1. **Configure** → Change polling interval to "1 minute"
2. Check entity update times - should update every ~1 minute
3. Change back to "5 minutes (default)" for normal operation
4. Verify coordinator logs show interval updates

### Step 5: Energy Dashboard Integration
1. Go to **Settings** → **Dashboards** → **Energy**
2. Click **Add Consumption**
3. Look for Red Energy sensors in the entity picker
4. Should see options like "Main Residence Electricity Total Usage"
5. Add to energy dashboard and verify data appears

### Step 6: Test Automation Examples
Copy automation examples from `AUTOMATION_EXAMPLES.md`:

#### High Daily Cost Alert (Example 1)
- Modify trigger threshold to 20 kWh (lower for testing)
- Should trigger when daily usage exceeds threshold
- Test between 6-11 PM for time condition

#### Peak Usage Detection (Example 3)  
- Should activate when current usage > 1.5x daily average
- Check that efficiency calculations are working

## Expected Mock Data Values

### Core Sensors:
- **Daily Usage**: 25-45 kWh (electricity), 45-65 MJ (gas)
- **Total Cost**: $210-378 AUD (30 days)
- **Total Usage**: 750-1350 kWh/MJ (30 days)

### Advanced Sensors:
- **Daily Average**: ~30 kWh (electricity), ~55 MJ (gas)
- **Monthly Average**: ~900 kWh (electricity), ~1650 MJ (gas)
- **Peak Usage**: ~45 kWh (electricity), ~65 MJ (gas)
- **Efficiency**: 75-85% (good consistency), with variation rating

## Service Call Testing

### Refresh Data Service
**Test Steps:**
1. Note current sensor values
2. Call `red_energy.refresh_data` 
3. Values should update (may be similar due to mock data)
4. Check logs for "Manual data refresh requested" message

### Export Data Service
**Test Steps:**
1. Call with different parameters (json/csv, 7/30 days)
2. Check for persistent notification
3. Verify notification shows correct counts
4. Check logs for export completion message

### Credential Update Service  
**Test Steps:**
1. Use same mock credentials to avoid authentication errors
2. Should succeed and show success message
3. Try with wrong credentials - should fail gracefully

## Energy Dashboard Verification

**Integration Test:**
1. Add Red Energy sensors to Energy Dashboard
2. Verify proper units (kWh for electricity, MJ for gas)
3. Check that cost sensors appear in cost tracking
4. Confirm data flows into dashboard graphs

## Automation Integration

**Test Key Automations:**
1. **High Usage Alert**: Lower thresholds to trigger easily
2. **Efficiency Monitoring**: Should show realistic efficiency ratings
3. **Data Export**: Weekly/monthly automation should work
4. **Voice Integration**: Test with voice assistant if available

## Performance Testing

**Polling Performance:**
1. Set to 1-minute intervals
2. Monitor system performance and log sizes
3. Verify no memory leaks or excessive API calls
4. Test with multiple integrations if possible

## Advanced Features Validation

### Efficiency Algorithm:
- Efficiency based on coefficient of variation
- Lower variation = higher efficiency rating
- Should show 75-85% for typical mock data patterns

### Peak Detection:
- Identifies highest single-day usage
- Provides date and cost attribution
- Should align with highest values in daily data

### Monthly Projections:
- Projects 30-day data to full month (30.44 days)
- Should be slightly higher than 30-day total
- Useful for budgeting and planning

## Expected Test Results

✅ **Stage 4 Complete** when:
- [ ] Advanced sensors appear when enabled (4 additional per service)
- [ ] Polling intervals configurable (1min to 1hour)
- [ ] All 3 service calls work correctly
- [ ] Energy dashboard integration functional
- [ ] Efficiency ratings show 75-85% for mock data
- [ ] Peak usage sensors show realistic peaks with dates
- [ ] All 33 tests pass (`pytest tests/ -v`)
- [ ] Automation examples work when implemented
- [ ] No performance issues with 1-minute polling

## Troubleshooting

**Advanced sensors don't appear**: Check that "Enable Advanced Sensors" is checked in options
**Efficiency shows 0%**: Need at least 7 days of data for calculation
**Service calls fail**: Check entity_ids match your actual sensor names
**Energy dashboard not showing sensors**: Verify sensor state_class and device_class
**Automations not triggering**: Check entity names and threshold values

## Real-World Usage Notes

When using with real Red Energy API:
- Use 5-15 minute polling to avoid rate limits
- Peak usage helps identify high-consumption days
- Efficiency ratings help optimize usage patterns
- Export data for external analysis and budgeting
- Energy dashboard provides comprehensive energy monitoring