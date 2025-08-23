# Stage 2 Testing Guide: UI Configuration Flow

## Overview
Stage 2 implements comprehensive Home Assistant UI-based configuration with mock data for testing.

## Mock Test Credentials

The integration includes a mock API for testing. Use these credentials in the Home Assistant UI:

### Account 1:
- **Username**: `test@example.com`
- **Password**: `testpass`
- **Client ID**: `test-client-id-123`

### Account 2:
- **Username**: `demo@redenergy.com.au`  
- **Password**: `demo123`
- **Client ID**: `demo-client-abc`

## Testing the Configuration Flow

### Step 1: Install Integration
1. Copy `custom_components/red_energy/` to your Home Assistant `custom_components` directory
2. Restart Home Assistant

### Step 2: Add Integration via UI
1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Red Energy"
4. Click on the Red Energy integration

### Step 3: Configuration Flow Testing

**Form 1: Credentials**
- Enter one of the mock credentials above
- Click **Submit**
- Should validate successfully and proceed to next step

**Form 2: Account Selection** (if multiple accounts)
- Select which accounts to monitor
- Shows account names and addresses
- Click **Submit**

**Form 3: Service Selection**
- Choose services: Electricity, Gas, or both
- Click **Submit**
- Integration should be created successfully

### Step 4: Verify Integration
- Integration should appear in Devices & Services
- Title should show customer name (e.g., "John Smith")
- Multiple accounts will show count (e.g., "John Smith (2 accounts)")

## Expected Mock Data

**Customer**: John Smith (test@example.com)

**Properties**:
1. **Main Residence** - 123 Main Street, Melbourne VIC 3000
   - Electricity service (consumer: elec-123456)
   - Gas service (consumer: gas-789012)

2. **Investment Property** - 456 Oak Avenue, Sydney NSW 2000  
   - Electricity service only (consumer: elec-654321)

## Error Testing

Test these error scenarios:

1. **Invalid Credentials**: Use wrong password → should show "Invalid username or password"
2. **Invalid Client ID**: Use wrong client_id → should show "Invalid client ID" 
3. **Network Issues**: (simulated) → should show "Failed to connect to Red Energy"

## Options Flow Testing

After setup:
1. Go to integration → **Configure**
2. Should allow changing service selections
3. Changes should be saved and applied

## Success Criteria

✅ **Stage 2 Complete** when:
- [ ] Integration loads in Home Assistant UI
- [ ] Configuration flow accepts mock credentials
- [ ] Account selection works with multiple properties
- [ ] Service selection (electricity/gas) works
- [ ] Error handling displays appropriate messages
- [ ] Options flow allows post-setup changes
- [ ] All 10 tests pass (`pytest tests/ -v`)

## Next Stage
Stage 3 will connect to the real Red Energy API and implement data coordinators for polling usage data.

## Troubleshooting

**Integration doesn't appear**: Check Home Assistant logs for loading errors
**Forms don't work**: Verify voluptuous dependency is available
**Mock data issues**: Check config_flow.py is using MockRedEnergyAPI