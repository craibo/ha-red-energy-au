# Red Energy Integration - Installation Instructions

## Stage 1: Basic Integration Structure

### Manual Installation (Development)

1. Copy the `custom_components/red_energy` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. The integration should appear in the logs as loading successfully

### Expected Structure

```
custom_components/
└── red_energy/
    ├── __init__.py
    ├── const.py
    ├── manifest.json
    └── sensor.py
```

### Testing the Installation

1. Check Home Assistant logs for "Setting up Red Energy integration"
2. A test sensor named "Red Energy Test Sensor" should appear with the value "Integration loaded successfully"

### Current Limitations

This is Stage 1 - the integration currently:
- ✅ Loads successfully in Home Assistant
- ✅ Creates a basic test sensor
- ❌ Does not have configuration flow (cannot be configured through UI)
- ❌ Does not connect to Red Energy API yet
- ❌ Does not retrieve real usage data

## Stage 2 Complete: UI Configuration Flow ✅

### What's New:
- **Complete UI-based configuration** - no manual file editing required
- **Multi-step configuration flow** with credential validation
- **Account discovery and selection** 
- **Service type selection** (electricity, gas, or both)
- **Comprehensive error handling** with user-friendly messages
- **Mock API for testing** with sample credentials
- **Options flow** for post-setup changes

### Testing Stage 2:
See `STAGE2_TESTING.md` for detailed testing instructions with mock credentials:
- Username: `test@example.com` / Password: `testpass` / Client ID: `test-client-id-123`

### Configuration Flow:
1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Red Energy"
3. Enter credentials (use mock credentials for testing)
4. Select accounts to monitor
5. Choose services (electricity/gas/both)
6. Integration created with configured sensors

## Stage 3 Complete: Core API Integration & Data Polling ✅

### What's New:
- **DataUpdateCoordinator**: Automatic 5-minute polling for usage data
- **Real Sensor Entities**: 3 sensors per service (daily usage, total cost, total usage)
- **Device Organization**: Sensors grouped by property with proper device info
- **Data Validation**: Robust validation and error handling for all API responses
- **Diagnostics Support**: Integration and device-level diagnostics for troubleshooting
- **Enhanced Error Recovery**: Graceful handling of partial data failures

### Sensor Types Created:
For each account/service combination:
1. **Daily Usage**: Most recent day's consumption (kWh for electricity, MJ for gas)
2. **Total Cost**: 30-day cost total in AUD
3. **Total Usage**: 30-day usage total with proper units

### Testing Stage 3:
See `STAGE3_TESTING.md` for detailed testing with expected sensor values and troubleshooting.

### Current Status:
- ✅ Complete UI-based configuration
- ✅ DataUpdateCoordinator with 5-minute polling
- ✅ Multiple sensor entities per service
- ✅ Device grouping and organization  
- ✅ Comprehensive data validation
- ✅ Diagnostics and error recovery
- ✅ All tests passing (21/21)
- ❌ Real Red Energy API OAuth flow (requires manual implementation)
- ❌ Historical data visualization (future stage)

## Next Steps - Stage 4: Advanced Features
- Real-time usage monitoring enhancements
- Historical data and trends
- Energy optimization recommendations  
- Enhanced device management