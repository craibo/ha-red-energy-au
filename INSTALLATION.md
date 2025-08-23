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

## Next Steps - Stage 2: UI Configuration Flow

Stage 2 will implement a comprehensive Home Assistant UI configuration flow:

### Configuration Flow Features:
- **Initial Setup UI**: Username, password, and client_id input fields
- **Credential Validation**: Real-time validation against Red Energy API
- **Account Discovery**: Automatic detection of available Red Energy accounts
- **Service Selection**: Choose electricity, gas, or both services per account
- **Multi-Account Support**: Configure multiple Red Energy accounts
- **Error Handling**: Clear error messages for invalid credentials or API issues

### Options Flow Features (post-setup):
- Modify account selections
- Change service types (electricity/gas)
- Update polling intervals
- Change credentials

### User Experience:
1. Go to Settings → Devices & Services → Add Integration
2. Search for "Red Energy" 
3. Enter Red Energy login credentials
4. Select which accounts and services to monitor
5. Integration automatically creates sensors for usage and cost data

**All configuration will be handled through the Home Assistant UI - no manual file editing required.**