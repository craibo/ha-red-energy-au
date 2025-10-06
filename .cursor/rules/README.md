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

1. Always refer to `red-energy-api-structure.md` before modifying API response handling
2. Test with actual API responses, not mock data
3. Update version history when making structural changes
4. Add new mappings to the documentation when discovered
5. Keep transformation examples up to date

## File Organization

```
.cursor/rules/
├── README.md                      # This file
└── red-energy-api-structure.md   # API structure reference
```

## Related Files

- `custom_components/red_energy/data_validation.py` - Implements validation and transformation
- `custom_components/red_energy/api.py` - API client implementation
- `custom_components/red_energy/config_flow.py` - Setup flow
- `custom_components/red_energy/config_migration.py` - Config version migrations

## Last Updated

2025-10-06 - Initial documentation created

