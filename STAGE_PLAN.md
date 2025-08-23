# Red Energy Integration - Detailed Stage Plan

## Updated Implementation Strategy: UI-First Configuration

All user configuration will be handled through Home Assistant's native UI flows. No manual file editing or environment variables required.

## Stage 2: Authentication & Configuration Flow (UPDATED)

### Core Components to Implement:

**1. Config Flow (`config_flow.py`)**
- Username/password/client_id input form
- Real-time credential validation with Red Energy API
- Account discovery after successful authentication
- Service type selection UI (electricity, gas, both)
- Multi-account support
- Error handling with user-friendly messages

**2. Options Flow**
- Post-setup configuration changes
- Account selection modifications
- Service type updates
- Polling interval adjustments

**3. Enhanced Constants (`const.py`)**
- Form field definitions
- Error message constants
- Configuration schema definitions

### Configuration Flow Steps:

1. **Initial Form**: Username, Password, Client ID input
2. **Validation**: Test credentials against Red Energy API
3. **Account Discovery**: Retrieve available accounts/properties
4. **Service Selection**: UI to choose electricity/gas per account
5. **Confirmation**: Summary of selected configuration
6. **Integration Creation**: Create config entry with all settings

### User Experience Flow:

```
Settings → Devices & Services → Add Integration
    ↓
Search "Red Energy" → Select Integration
    ↓
Enter Credentials Form (username, password, client_id)
    ↓
[API Validation] → Success/Error handling
    ↓
Account Selection (checkboxes for each discovered account)
    ↓
Service Type Selection (electricity/gas/both per account)
    ↓
Confirmation Screen → Create Integration
    ↓
Integration Active with Configured Sensors
```

### Configuration Storage:
- Credentials stored encrypted in Home Assistant config entries
- Account/service selections stored in entry options
- Support for multiple config entries (multiple Red Energy accounts)

### Validation & Error Handling:
- Real-time API credential testing
- Clear error messages for authentication failures
- Network error handling and retry logic
- Invalid client_id detection and guidance

**Deliverable**: Users can fully configure Red Energy integration through HA UI without any manual configuration files or environment variables.