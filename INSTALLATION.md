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

### Current Status:
- ✅ Full UI-based configuration implemented
- ✅ Mock API for testing without real credentials
- ✅ Multi-account support
- ✅ Service selection per account
- ✅ All tests passing (10/10)
- ❌ Real Red Energy API not connected yet (Stage 3)
- ❌ No actual usage data sensors yet (Stage 3)

## Next Steps - Stage 3: Core API Integration
- Connect to real Red Energy API
- Implement data coordinators for polling
- Create actual usage and cost sensors
- Add proper error recovery and logging