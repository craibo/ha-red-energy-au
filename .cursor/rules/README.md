# Red Energy Integration Rules & Documentation

This directory contains project-specific rules, patterns, and documentation for the Red Energy Home Assistant integration.

## Contents

### 📋 API Documentation

- **[red-energy-api-structure.md](./red-energy-api-structure.md)** - Complete API response structure reference
  - Property/Account response format
  - Consumer/Service data structure
  - Address field mappings
  - Data transformation examples
  - Validation rules
  - Common issues and solutions

### 🔐 Authentication

- **[red-energy-authentication.md](./red-energy-authentication.md)** - OAuth2 PKCE authentication reference
  - Authentication flow architecture
  - Token lifecycle management
  - Implementation details with code references
  - Security considerations
  - Error handling patterns
  - Troubleshooting guide

### 🏪 HACS Configuration

- **[hacs-topics.md](./hacs-topics.md)** - HACS repository topics and validation reference
  - Required and recommended topics
  - HACS validation requirements
  - hacs.json valid keys
  - Topic verification and management
  - Troubleshooting guide

## Quick Reference

### API Response Key Differences

The Red Energy API uses non-standard field names:

| Standard | Red Energy API | Notes |
|----------|----------------|-------|
| `services` | `consumers` | Array of utility services |
| `type: "electricity"` | `utility: "E"` | Utility code mapping |
| `consumer_number` | `consumerNumber` | camelCase format |
| `active: true` | `status: "ON"` | String status |
| `city` | `suburb` | Australian terminology |

### Critical Implementation Details

1. **Property IDs must be strings** for comparison
2. **All accounts are auto-selected** during setup
3. **Config v4 migration** auto-fixes old configs with wrong IDs
4. **Service validation** handles both `consumers` and `services` arrays

## Development Guidelines

When working with this integration:

1. **API Structure**: Always refer to `red-energy-api-structure.md` before modifying API response handling
2. **Authentication**: Review `red-energy-authentication.md` when working with auth flows or token management
3. **Testing**: Test with actual API responses, not mock data
4. **Documentation**: Update version history when making structural changes
5. **Validation**: Add new mappings/patterns to documentation when discovered
6. **Code References**: Keep implementation references accurate when refactoring

## File Organization

```
.cursor/rules/
├── README.md                       # This file
├── hacs-topics.md                  # HACS configuration reference
├── red-energy-api-structure.md     # API structure reference
└── red-energy-authentication.md    # OAuth2 authentication reference
```

## Related Files

- `custom_components/red_energy/api.py` - API client and authentication implementation
- `custom_components/red_energy/config_flow.py` - Setup flow and credential validation
- `custom_components/red_energy/data_validation.py` - Data validation and transformation
- `custom_components/red_energy/config_migration.py` - Config version migrations
- `tests/test_config_flow_basic.py` - Authentication and config flow tests

## Last Updated

2025-10-06 - Added OAuth2 authentication reference documentation

