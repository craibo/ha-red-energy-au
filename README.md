# Red Energy Home Assistant Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
[![Integration Usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&style=for-the-badge&logo=home-assistant&label=usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.red_energy.total)](https://analytics.home-assistant.io/)

A comprehensive Home Assistant custom integration for Red Energy (Australian energy provider) that tracks daily energy usage and provides advanced analytics.

---

## Support this project

[![Sponsor me on GitHub](https://img.shields.io/badge/Sponsor-craibo%20on%20GitHub-blue.svg?logo=github)](https://github.com/sponsors/craibo)
[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?logo=paypal)](https://paypal.me/craibo?country.x=AU&locale.x=en_AU)

---

## Features

### 🏠 **Core Energy Monitoring**
- **Energy Usage Tracking**: Daily electricity and gas consumption data from Red Energy
- **Cost Analysis**: Total costs and daily spending tracking
- **Multi-Account Support**: Monitor every account on your Red Energy login, each as its own device - including split accounts where electricity and gas are billed separately
- **Dual Service Support**: Electricity and gas monitored automatically, with electricity-only sensors (solar, export, time-of-use, demand, emissions) correctly omitted from gas accounts
- **Tariff Rate Visibility**: A diagnostic sensor per contracted rate on your actual plan (peak/off-peak/shoulder/supply/demand/tiered steps)

### 📊 **Advanced Analytics** (Optional)
- **Daily & Monthly Averages**: Statistical analysis of current billing-period usage
- **Highest Net Usage Day Detection**: Identify the highest single-day net usage with date attribution
- **Usage Consistency Score**: 0-100 score based on day-to-day usage variation (not energy efficiency)
- **Usage Pattern Analysis**: Coefficient of variation calculations for spotting irregular usage
- **CL2/TOU Reconstruction** *(where supported)*: Separates inferred Controlled Load usage from combined Peak/Shoulder/Off-Peak interval data

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
**25 sensors for electricity accounts, 20 for gas accounts** (gas accounts skip the 5 electricity-only ones marked below):

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
- Product Name - Promotional product name (exposes the plan's `promotion_description` as an attribute)
- Distributor - Energy distributor / lines company
- Payment Type - Payment method description (e.g. Direct Debit Bank)
- Address - Formatted property address (exposes `latitude`/`longitude` attributes for mapping)
- Jurisdiction - Jurisdiction (state)
- Charge Class - Charge classification (Residential/Small Business)
- Plan Name - Named tariff plan (e.g. Residential Demand Solar)
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
Enabled via the "Advanced Sensors" integration option. **16 sensors for electricity accounts, 6 for gas accounts** (gas accounts get Daily/Monthly Average, Highest Net Usage Day, Current Period Service Charge, Projected Net Cost, and Projected Charges - the rest are electricity-only, marked below). This count does **not** include the CL2/TOU Reconstruction sensors described further below, which are conditional and not present on every electricity account.

**Statistical Analysis:**
- Daily Average - Arithmetic mean of the available daily usage records in the *current billing period*. Early in a new billing period this may be based on only a small number of days
- Monthly Average - Current billing-period usage normalised to a nominal 30.44-day month (`current period total usage / current period days × 30.44`). This is derived from the current billing period, not an average of historical months
- Highest Net Usage Day - Highest single-day net usage recorded in the analysed period, with the date it occurred. This is distinct from TOU Peak-period consumption and from maximum electrical demand
- Efficiency *(electricity only)* - Daily usage consistency score (0-100) based on the coefficient of variation of daily consumption. A higher value means more consistent day-to-day usage, not lower consumption or greater energy efficiency
- Current Period Service Charge - Accumulated daily service/supply charge from the start of the current billing period to the latest completed usage day (AUD)
- Projected Net Cost - Estimated net energy cost (import minus export credit) for the full billing cycle, extrapolated from usage to date. GST-inclusive; an estimate, not Red Energy's own figure
- Projected Charges - Projected Net Cost plus the daily service/supply charge projected across the full cycle, for a fuller bill estimate; for Demand-tariff plans this also includes the projected demand charge. GST-inclusive; an estimate, not Red Energy's own figure

**Time-of-Use Breakdown** *(electricity only - gas has no ToU tariff)*:
- Peak/Offpeak/Shoulder Import Usage - combined TOU-labelled usage as supplied by Red Energy (see [CL2/TOU Reconstruction](#cl2--tou-reconstruction-optional-conditional) below if your plan has a resolvable Controlled Load rate)
- Peak/Offpeak/Shoulder Export Usage

**Demand & Environmental** *(electricity only)*:
- Max Demand - Maximum demand (kW)
- Current Period Demand Charge - Accumulated demand charge from the start of the current billing period to the latest completed usage day, for Demand-tariff plans. GST-inclusive; an estimate, not Red Energy's own figure
- Carbon Emission Tonne - Carbon emissions (tonnes CO₂e)

### CL2 / TOU Reconstruction (Optional, Conditional)

Red Energy's own usage presentation does not expose Controlled Load (CL2) as a separate energy component. At the API level, each half-hourly interval provides a single combined consumption value that mixes general-supply TOU energy with any CL2 usage occurring during that interval, labelled with whichever TOU period (Peak/Shoulder/Off-Peak) applies.

Where the integration can unambiguously resolve the account's Peak, Shoulder, Off-Peak, and CL2 rates from its plan, it uses each interval's energy, cost, and those rates to separate out the inferred CL2 component. This produces six additional sensors, created **only** when all four rate roles resolve unambiguously - most accounts have no Controlled Load and will never see these entities:

- CL2 Inferred Energy - Estimated CL2 energy separated from the combined interval consumption
- Corrected Peak Import - Peak-period general-supply import with inferred CL2 energy removed
- Corrected Shoulder Import - Shoulder-period general-supply import with inferred CL2 energy removed
- Corrected Off-Peak Import - Off-Peak-period general-supply import with inferred CL2 energy removed
- CL2 Inferred Cost - Calculated cost of the inferred CL2 component
- Reconstructed Import Cost - Reconstructed total import cost, used to reconcile the separated TOU + CL2 components against Red Energy's own interval cost

CL2 is **not** assumed to occur only during Off-Peak periods - it is inferred from whichever Peak, Shoulder, or Off-Peak interval it actually falls in.

**Choosing which TOU sensor set to use:** the original Peak/Shoulder/Off-Peak sensors above represent the *combined* TOU-labelled usage as supplied by Red Energy, and remain useful for direct comparison with the Red Energy app and for backwards compatibility. Because that combined usage can already include CL2 energy, do **not** add CL2 Inferred Energy to the original Peak/Shoulder/Off-Peak totals when building a separated tariff breakdown - this double-counts the CL2 component. For a separated breakdown, use:

> **Corrected Peak + Corrected Shoulder + Corrected Off-Peak + CL2 Inferred Energy**

These reconstructed values are calculations derived by the integration from Red Energy's interval data - they are not additional meter readings.

**Limitations:**
- The calculation uses the account's *current* plan rates for every interval in the queried period, because historical tariff-rate data isn't available from the API. A tariff-rate change partway through the analysed period will therefore skew reconstruction for the days before the change
- Individual intervals are excluded from inference when their pricing can't be reliably resolved (e.g. an unknown tariff, or rates that can't be distinguished from one another); the integration tracks accepted/rejected interval counts and rejection reasons internally for diagnostic purposes

### Diagnostics Button
Each device has its own **Refresh metadata** button. Pressing it on any device triggers a full metadata + usage refresh for every account on the config entry (not just that one device) - it's duplicated per device purely so the action is reachable no matter which device you're viewing.

## Usage Calculation & Billing Period

### How Usage is Calculated

The integration automatically aligns with your Red Energy billing cycle by using the `lastBillDate` from your account:

- **Billing Period Start**: `lastBillDate` represents the *final day of the previous* billing period, so the current billing period begins on the calendar day following it (`lastBillDate + 1 day`)
- **Usage Data Availability**: The billing-period calculation window may extend beyond the latest daily usage Red Energy has actually published, since usage data is normally published retrospectively (see [Data Update Limitations](#important-data-update-limitations) above)
- **Updates**: Automatically adjusts each billing cycle

### Benefits of Billing Period Tracking

- **Bill Comparison**: Current-period sensors are aligned to the Red Energy billing period to facilitate close comparison with Red Energy billing data. Integration-calculated projections are estimates and may differ from the final Red Energy invoice
- **Flexible Billing**: Works with all billing frequencies (monthly, quarterly, etc.)
- **Current Period Tracking**: Track available usage and calculated charges for the current billing period as they accumulate

### Fallback Behavior

If `lastBillDate` is unavailable (new accounts or API issues), the integration uses a **30-day fallback calculation window** instead of the true billing period:
- Automatically falls back to a rolling 30-day window
- This fallback window is not necessarily your actual Red Energy billing period
- Returns to billing period tracking once `lastBillDate` is available

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
- Track usage consistency over time

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
