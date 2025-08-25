# HACS Repository Topics Setup

To complete HACS validation, the following topics need to be added to the GitHub repository:

## Required Topics

Add these topics to the repository via GitHub web interface:

1. Go to https://github.com/craibo/ha-red-energy-au
2. Click the gear icon next to "About" on the right side
3. Add the following topics in the "Topics" field:

### Core Topics
- `home-assistant`
- `homeassistant` 
- `custom-component`
- `integration`

### Domain-Specific Topics
- `energy`
- `australia`
- `red-energy`
- `python`

## How to Add Topics

1. **Via GitHub Web Interface:**
   - Navigate to repository main page
   - Click settings gear next to "About" section
   - Add topics separated by spaces or commas
   - Save changes

2. **Via GitHub CLI (if authenticated):**
   ```bash
   gh repo edit --add-topic "home-assistant" --add-topic "homeassistant" --add-topic "custom-component" --add-topic "integration" --add-topic "energy" --add-topic "australia" --add-topic "red-energy" --add-topic "python"
   ```

## HACS Validation Requirements

- Repository must have topics defined
- hacs.json must only contain valid keys:
  - ✅ `name` (required)
  - ✅ `country` (optional)
  - ✅ `homeassistant` (optional - minimum HA version)
  - ❌ `domains` (not allowed in hacs.json)
  - ❌ `iot_class` (not allowed in hacs.json)

## After Adding Topics

1. The repository will pass HACS topic validation
2. HACS validation workflow should pass
3. Integration will be eligible for HACS inclusion

Delete this file after topics have been added manually.