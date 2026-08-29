# Red Energy Home Assistant Integration

[![GitHub Release](https://img.shields.io/github/v/release/craibo/ha-red-energy-au?color=41BDF5&style=for-the-badge)](https://github.com/craibo/ha-red-energy-au/releases/latest)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Integration Usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&style=for-the-badge&logo=home-assistant&label=usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.red_energy.total)](https://analytics.home-assistant.io/)

A comprehensive Home Assistant custom integration for Red Energy (Australian energy provider) that provides real-time energy monitoring and advanced analytics.

---

## Support this project

[![Sponsor me on GitHub](https://img.shields.io/badge/Sponsor-craibo%20on%20GitHub-blue.svg?logo=github)](https://github.com/sponsors/craibo)
[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?logo=paypal)](https://paypal.me/craibo?country.x=AU&locale.x=en_AU)

---

## Key Features

- **Real-time Energy Monitoring**: Track daily electricity and gas usage with cost analysis
- **Multi-Account Support**: Every account on your Red Energy login gets its own device - including split accounts where electricity and gas are billed separately at the same address
- **Advanced Analytics**: Daily/monthly averages, peak usage detection, and efficiency ratings
- **Tariff Rate Visibility**: A diagnostic sensor per rate on your actual plan (peak/off-peak/shoulder/supply/demand)
- **Energy Dashboard Integration**: Native Home Assistant Energy dashboard support

## What You Get

### Core Sensors (Per Account/Device)
- Daily and total usage/cost tracking (kWh for electricity, MJ for gas) since last bill
- Account metadata: NMI, meter type, product name, plan name, distributor, payment type, address (with lat/long for mapping), balance, arrears, bill dates
- Electricity-only concepts (solar, export usage/credit) are only created on electricity accounts, never on gas

### Advanced Analytics (Optional)
- Daily and monthly usage averages (billing period-adjusted)
- Peak usage detection with date attribution  
- Efficiency ratings (0-100%) based on usage consistency - electricity only
- Time-of-use breakdown, max demand, and carbon emissions - electricity only
- Projected net cost and projected charges (including demand charge for Demand-tariff plans) for the current billing cycle
- Accrued service charge and demand charge (Demand-tariff plans) since the start of the current billing period

### Billing Period Alignment
- Automatic alignment with Red Energy billing cycles
- Usage tracking from last bill date to current date
- Direct comparison with actual Red Energy bills
- Automatic fallback to 30-day period if needed

### Service Calls
- Manual data refresh
- Credential updates
- Data export (JSON/CSV formats)

## Setup

⚠️ **Important**: Authentication and token renewal will **not** work if you are connected to a VPN. Ensure your VPN is disabled for the domains `redenergy.okta.com` and `login.redenergy.com.au`

⚠️ **Data Update Limitation**: Red Energy only updates usage data on their platform once per day, typically around 3am AEST. This means usage data is not updated every polling interval - the integration checks Red Energy's API at your configured interval, but usage data will only change once per day after Red Energy's daily update. Longer polling intervals (30 minutes to 4 hours) are recommended to reduce unnecessary API calls.

### Configuration Steps

1. Enter your Red Energy credentials:
   - **Username**: Your Red Energy account email
   - **Password**: Your Red Energy account password
2. All accounts on your login are added automatically, each as its own device - electricity and gas are always both monitored (there's nothing to select per-service)
3. Afterwards, use the integration's **Configure** option to choose which accounts to monitor, set the polling interval, or enable advanced sensors

## Configuration Options

- **Accounts to Monitor**: Choose which accounts/devices are active, labeled `{account_id} - {Electricity|Gas}`
- **Polling Intervals**: 15min, 30min (default), 1hour, 2hours, 4hours
- **Advanced Sensors**: Enable detailed usage analytics

**Note**: Red Energy updates usage data once daily around 3am AEST. Polling intervals control how often the integration checks for updates, but usage data will only change once per day after Red Energy's daily refresh.

## Real-World Benefits

### For Homeowners
- Monitor daily energy costs and identify high-usage periods
- Set up automated alerts for budget management
- Optimize energy consumption with time-of-use insights
- Track efficiency improvements over time

### For Property Managers  
- Monitor multiple properties from a single interface
- Generate automated usage reports
- Set up cost monitoring and budget alerts
- Track property-specific usage patterns

### For Energy Enthusiasts
- Deep analytics with statistical calculations
- Comprehensive energy dashboard integration

## Documentation

Complete documentation includes:
- Troubleshooting and debug information in README
- Developer references for API structure and OAuth2 authentication

## Support

- Detailed installation documentation
- GitHub Issues for bug reports and feature requests
- Active development with regular updates
- Community-driven with responsive support

---

**Note**: This is a community-developed integration and is not officially affiliated with Red Energy. Requires valid Red Energy account credentials.
