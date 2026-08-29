# Red Energy Home Assistant Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
[![Integration Usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&style=for-the-badge&logo=home-assistant&label=usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.red_energy.total)](https://analytics.home-assistant.io/)

A comprehensive Home Assistant custom integration for Red Energy (Australian energy provider) that provides real-time energy monitoring and advanced analytics.

---

## Support this project

[![Sponsor me on GitHub](https://img.shields.io/badge/Sponsor-craibo%20on%20GitHub-blue.svg?logo=github)](https://github.com/sponsors/craibo)
[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?logo=paypal)](https://paypal.me/craibo?country.x=AU&locale.x=en_AU)

---

## Features

### 🏠 **Core Energy Monitoring**
- **Real-time Usage Tracking**: Daily electricity and gas consumption
- **Cost Analysis**: Total costs and daily spending tracking
- **Multi-Account Support**: Monitor every account on your Red Energy login, each as its own device - including split accounts where electricity and gas are billed separately
- **Dual Service Support**: Electricity and gas monitored automatically, with electricity-only sensors (solar, export, time-of-use, demand, emissions) correctly omitted from gas accounts
- **Tariff Rate Visibility**: A diagnostic sensor per contracted rate on your actual plan (peak/off-peak/shoulder/supply/demand/tiered steps)

### 📊 **Advanced Analytics** (Optional)
- **Daily & Monthly Averages**: Statistical analysis of usage patterns
- **Peak Usage Detection**: Identify highest consumption periods with date attribution
- **Efficiency Ratings**: 0-100% efficiency scoring based on usage consistency
- **Usage Pattern Analysis**: Coefficient of variation calculations for optimization

### 🔧 **Configuration & Management**
- **UI-First Setup**: Complete configuration through Home Assistant UI
- **Flexible Polling**: Configurable update intervals (15min, 30min (default), 1hour, 2hours, 4hours)
- **Service Calls**: Manual refresh, credential updates, and data export
- **Energy Dashboard Integration**: Native Home Assistant Energy dashboard support

## Quick Start

### Installation via HACS (Recommended)

1. Install [HACS](#hacs) following the instructions [here](https://hacs.xyz/docs/setup/download)
2. [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=craibo&repository=ha-red-energy-au&category=integration)
3. Press the Download button
4. Restart Home Assistant
5. [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=red_energy)

### Manual Installation

1. Download the `red_energy` folder from the `custom_components` directory
2. Copy to your Home Assistant `custom_components` directory
3. Restart Home Assistant

### Configuration

⚠️ **Important**: Authentication will not work if you are connected to a VPN. Ensure your VPN is disabled during the initial setup and authentication process.

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration** and search for "Red Energy"
3. Enter your Red Energy credentials:
   - **Username**: Your Red Energy account email address
   - **Password**: Your Red Energy account password
4. All accounts on your Red Energy login are added automatically - electricity and gas are always both monitored (each account is billed as one service, so there's nothing to select)
5. Use the integration's **Configure** options afterwards to choose which accounts to monitor, adjust polling interval, or enable advanced sensors

⚠️ **Important**: This integration uses the real Red Energy API. You must have valid Red Energy account credentials to use this integration.

## Important: Data Update Limitations

⚠️ **Red Energy Data Update Schedule**: Red Energy only updates usage data on their platform once per day, typically around 3am AEST (Australian Eastern Standard Time). This means:

- **Usage data is not updated every polling interval** - The integration can check for updates at your configured interval (15 minutes, 30 minutes, etc.), but the actual usage data from Red Energy will only change once per day after their daily update.
- **Polling intervals affect API checks, not data freshness** - Setting a shorter polling interval (e.g., 15 minutes) means the integration will check Red Energy's API more frequently, but it will continue to see the same usage data until the next daily update.
- **Recommended polling intervals** - Since data updates daily, longer polling intervals (30 minutes to 4 hours) are recommended to reduce unnecessary API calls while still ensuring you receive updates shortly after Red Energy's daily data refresh.

This limitation is inherent to Red Energy's platform and cannot be changed by this integration. The integration will automatically detect and display new data once Red Energy updates it.

## Devices & Sensors Created

Red Energy bills electricity and gas as **separate accounts**, even at the same address (e.g. one account for electricity, another for gas). This integration creates **one Home Assistant device per account**, named `{account_id} - {Electricity|Gas}`, so split accounts at the same address are never ambiguous. Every sensor entity belongs to its account's device; entity names don't repeat the account ID or service (the device already shows both).

Since electricity-only concepts (solar, export, time-of-use tariffs, demand, carbon emissions) don't apply to gas, those sensors are only created on electricity accounts - a gas-only account won't get a permanently meaningless "Solar" entity, for example.

### Core Sensors (Always Available)
**24 sensors for electricity accounts, 19 for gas accounts** (gas accounts skip the 5 electricity-only ones marked below):

**Usage & Cost Tracking:**
- Daily Import Usage - Daily imported energy (kWh/MJ)
- Daily Export Usage *(electricity only)* - Daily exported energy (kWh)
- Current Period Import Usage - Imported energy since last bill
- Current Period Export Usage *(electricity only)* - Exported energy since last bill
- Daily Import Cost - Daily import cost, GST-exclusive (AUD)
- Daily Export Credit *(electricity only)* - Daily export credit (AUD)
- Current Period Import Cost - Import cost since last bill, GST-exclusive (AUD)
- Current Period Export Credit *(electricity only)* - Export credit since last bill (AUD)
- Current Period Net Cost - Net cost (GST-exclusive import minus export credit) since last bill (AUD)

**Account & Service Information:**
- NMI - National Meter Identifier
- Meter Type - Meter type (e.g. INTERVAL, BASIC)
- Solar *(electricity only)* - Solar system indicator
- Energy Plan - Current energy plan name (exposes the plan's `promotion_description` as an attribute)
- Distributor - Energy distributor / lines company
- Payment Type - Payment method description (e.g. Direct Debit Bank)
- Address - Formatted property address (exposes `latitude`/`longitude` attributes for mapping)
- Jurisdiction - Jurisdiction (state)
- Energy Plan Type - Charge classification (Residential/Small Business)
- Status - Service status

**Billing Information:**
- Balance - Current account balance (AUD)
- Arrears - Outstanding arrears (AUD)
- Last Bill Date - Last billing date
- Next Bill Date - Next billing date
- Billing Frequency - Billing cycle frequency

### Tariff Rate Sensors (Always Available, Variable Count)
One diagnostic sensor per rate on the account's actual plan (e.g. Peak, Off-Peak, Shoulder, Supply, Demand, or tiered gas usage steps), named `Rate {rate description}`. The state is the rate in dollars including GST; unit, excl-GST rate, and step description are exposed as attributes. The number of these sensors depends entirely on the plan's tariff structure.

### Advanced Sensors (Optional)
Enabled via the "Advanced Sensors" integration option. **12 sensors for electricity accounts, 3 for gas accounts** (gas accounts only get Daily/Monthly Average and Peak Usage, which apply to total usage regardless of service):

**Statistical Analysis:**
- Daily Average - Average daily usage
- Monthly Average - Projected monthly usage (billing period-adjusted)
- Peak Usage - Highest single-day usage with date
- Efficiency *(electricity only)* - Usage consistency efficiency rating (0-100%)
- Projected Net Cost - Estimated net energy cost (import minus export credit) for the full billing cycle, extrapolated from usage to date. GST-inclusive; not Red Energy's own figure
- Projected Charges - Projected Net Cost plus the daily service/supply charge projected across the full cycle, for a fuller bill estimate. GST-inclusive; not Red Energy's own figure

**Time-of-Use Breakdown** *(electricity only - gas has no ToU tariff)*:
- Peak/Offpeak/Shoulder Import Usage
- Peak/Offpeak/Shoulder Export Usage

**Demand & Environmental** *(electricity only)*:
- Max Demand - Maximum demand (kW)
- Carbon Emission Tonne - Carbon emissions (tonnes CO₂e)

### Diagnostics Button
Each device has its own **Refresh metadata** button. Pressing it on any device triggers a full metadata + usage refresh for every account on the config entry (not just that one device) - it's duplicated per device purely so the action is reachable no matter which device you're viewing.

## Usage Calculation & Billing Period

### How Usage is Calculated

The integration automatically aligns with your Red Energy billing cycle by using the `lastBillDate` from your account:

- **Usage Period**: `lastBillDate` to current date
- **Updates**: Automatically adjusts each billing cycle
- **Alignment**: Matches your actual Red Energy bill for easy comparison

### Benefits of Billing Period Tracking

- **Accurate Cost Projections**: Monthly averages reflect your actual billing cycle
- **Bill Comparison**: Sensor totals directly match your Red Energy bill amounts
- **Flexible Billing**: Works with all billing frequencies (monthly, quarterly, etc.)
- **Real-time Progress**: Track current bill period costs as they accumulate

### Fallback Behavior

If `lastBillDate` is unavailable (new accounts or API issues):
- Automatically falls back to 30-day rolling period
- Continues to provide accurate usage data
- Returns to billing period tracking once data is available

### Viewing Your Current Period

Each sensor includes the current calculation period in its attributes:
```yaml
period: "28 days (since last bill)"
period_days: 28
start_date: "2025-09-09T00:00:00"
end_date: "2025-10-07T12:34:56"
```

## Service Calls

### Manual Data Refresh
```yaml
service: red_energy.refresh_data
data: {}
```

### Export Usage Data
```yaml
service: red_energy.export_data
data:
  format: json  # or csv
  days: 30      # 1-365 days
```

### Update Credentials
```yaml
service: red_energy.update_credentials
data:
  username: "your@email.com"
  password: "newpassword"
```

## Energy Dashboard Integration

The integration automatically provides sensors compatible with Home Assistant's Energy Dashboard:

1. Go to **Settings** → **Dashboards** → **Energy**
2. Click **Add Consumption**
3. Select your Red Energy sensors from the list
4. Configure cost tracking using the cost sensors

## Troubleshooting

**Authentication failures**
- Verify username/password are correct
- Check for account lockouts on Red Energy website
- Ensure VPN is disabled during authentication

**Usage sensors disabled and showing "Unknown" on a device**
- If the account has a BASIC (manual-read) meter, Red Energy's API has no interval usage data for it - usage-dependent sensors are created disabled by default rather than sitting enabled with no value. Metadata sensors (NMI, balance, bill dates, etc.) still work normally

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

### Development Setup

```bash
# Clone repository
git clone https://github.com/craibo/ha-red-energy-au.git
cd ha-red-energy-au

# Install test dependencies
pip install -r requirements-test.txt

# Run tests
pytest tests/ -v
```

## Support

- **Issues**: Report bugs or feature requests via [GitHub Issues](https://github.com/craibo/ha-red-energy-au/issues)
- **Developer Reference**: See [CLAUDE.md](CLAUDE.md) for API structure and authentication documentation

## Real-World Usage

### For Homeowners
- Monitor daily energy costs and usage patterns
- Set up automated alerts for high usage periods
- Optimize energy consumption with time-of-use data
- Track efficiency improvements over time

### For Property Managers
- Monitor multiple properties from a single interface
- Generate automated usage reports
- Set up cost monitoring and budget alerts
- Track property-specific usage patterns

### For Energy Enthusiasts
- Deep analytics with coefficient of variation calculations
- Energy dashboard integration for comprehensive monitoring

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for the Home Assistant community
- Inspired by the need for comprehensive Australian energy provider integration
- Thanks to all contributors and testers

---

**Note**: This integration is not officially affiliated with Red Energy. It's a community-developed integration for Home Assistant users.

[commits-shield]: https://img.shields.io/github/commit-activity/y/craibo/ha-red-energy-au.svg?style=for-the-badge
[commits]: https://github.com/craibo/ha-red-energy-au/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/craibo/ha-red-energy-au.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/craibo/ha-red-energy-au.svg?style=for-the-badge
[releases]: https://github.com/craibo/ha-red-energy-au/releases
