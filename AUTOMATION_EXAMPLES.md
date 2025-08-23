# Red Energy Integration - Automation Examples

## Overview
This document provides comprehensive automation examples for the Red Energy Home Assistant integration. These automations help you monitor usage, control costs, and optimize energy consumption.

## Prerequisites
- Red Energy integration configured with sensors
- Advanced sensors enabled (for efficiency and peak usage automations)

## Cost Monitoring Automations

### 1. High Daily Cost Alert
```yaml
automation:
  - alias: "Red Energy - High Daily Cost Alert"
    description: "Alert when daily energy cost exceeds threshold"
    trigger:
      - platform: numeric_state
        entity_id: sensor.main_residence_electricity_daily_usage
        above: 25  # kWh threshold
    condition:
      - condition: time
        after: "18:00:00"  # Only check in evening
        before: "23:00:00"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "⚡ High Energy Usage Alert"
          message: >
            Daily electricity usage: {{ states('sensor.main_residence_electricity_daily_usage') }} kWh
            Estimated cost: ${{ (states('sensor.main_residence_electricity_daily_usage') | float * 0.28) | round(2) }}
          data:
            tag: "energy_alert"
            group: "Red Energy Alerts"
```

### 2. Monthly Budget Tracking
```yaml
automation:
  - alias: "Red Energy - Monthly Budget Check"
    description: "Track monthly energy spending against budget"
    trigger:
      - platform: time
        at: "06:00:00"
    condition:
      - condition: template
        value_template: "{{ now().day == 1 }}"  # First day of month
    action:
      - service: input_number.set_value
        target:
          entity_id: input_number.energy_budget_remaining
        data:
          value: 200  # $200 monthly budget
      - service: notify.persistent_notification.create
        data:
          title: "🏠 Monthly Energy Budget Reset"
          message: >
            New month started! Energy budget reset to ${{ states('input_number.energy_budget_remaining') }}.
            Last month's total: ${{ states('sensor.main_residence_electricity_total_cost') | float + states('sensor.main_residence_gas_total_cost') | float }}
```

## Usage Pattern Automations

### 3. Peak Usage Detection
```yaml
automation:
  - alias: "Red Energy - Peak Usage Detection"
    description: "Alert when usage reaches daily peak"
    trigger:
      - platform: state
        entity_id: sensor.main_residence_electricity_peak_usage
    condition:
      - condition: template
        value_template: >
          {{ trigger.to_state.state | float > 
             states('sensor.main_residence_electricity_daily_average') | float * 1.5 }}
    action:
      - service: script.turn_on
        target:
          entity_id: script.energy_saving_mode
      - service: notify.mobile_app_your_phone
        data:
          title: "📈 Peak Energy Usage Detected"
          message: >
            Current usage ({{ states('sensor.main_residence_electricity_peak_usage') }} kWh) 
            is 50% above your daily average. Energy saving mode activated.
```

### 4. Efficiency Monitoring
```yaml
automation:
  - alias: "Red Energy - Low Efficiency Alert"
    description: "Alert when energy efficiency drops"
    trigger:
      - platform: numeric_state
        entity_id: sensor.main_residence_electricity_efficiency
        below: 60  # 60% efficiency threshold
        for:
          hours: 2
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🍃 Low Energy Efficiency"
          message: >
            Your energy efficiency has dropped to {{ states('sensor.main_residence_electricity_efficiency') }}%.
            Consider checking for energy-wasting appliances.
          data:
            actions:
              - action: "ENERGY_TIPS"
                title: "View Energy Tips"
```

## Cost Optimization Automations

### 5. Time-of-Use Optimization
```yaml
automation:
  - alias: "Red Energy - Off-Peak Usage Reminder"
    description: "Remind to use high-energy appliances during off-peak hours"
    trigger:
      - platform: time
        at: "22:00:00"  # Off-peak starts
    condition:
      - condition: template
        value_template: >
          {{ states('sensor.main_residence_electricity_daily_usage') | float < 
             states('sensor.main_residence_electricity_daily_average') | float }}
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "⏰ Off-Peak Hours Started"
          message: >
            Off-peak electricity rates now active. Good time to run:
            • Dishwasher • Washing machine • Pool pump • EV charging
          data:
            tag: "off_peak_reminder"
```

### 6. Appliance Scheduling
```yaml
automation:
  - alias: "Red Energy - Smart Appliance Control"
    description: "Control high-energy appliances based on usage patterns"
    trigger:
      - platform: numeric_state
        entity_id: sensor.main_residence_electricity_daily_usage
        above: 30  # High usage day threshold
    condition:
      - condition: time
        after: "14:00:00"
        before: "18:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: 
            - switch.pool_pump
            - switch.electric_hot_water
      - service: notify.mobile_app_your_phone
        data:
          title: "🎛️ Energy Management Active"
          message: "High usage detected. Pool pump and hot water temporarily paused until off-peak hours."
```

## Data Management Automations

### 7. Weekly Energy Report
```yaml
automation:
  - alias: "Red Energy - Weekly Report"
    description: "Generate weekly energy usage report"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: template
        value_template: "{{ now().weekday() == 6 }}"  # Sunday
    action:
      - service: red_energy.export_data
        data:
          format: "json"
          days: 7
      - service: notify.mobile_app_your_phone
        data:
          title: "📊 Weekly Energy Report"
          message: >
            This week's energy summary:
            • Electricity: {{ states('sensor.main_residence_electricity_total_usage') }} kWh
            • Gas: {{ states('sensor.main_residence_gas_total_usage') }} MJ
            • Total Cost: ${{ (states('sensor.main_residence_electricity_total_cost') | float + states('sensor.main_residence_gas_total_cost') | float) | round(2) }}
            • Efficiency: {{ states('sensor.main_residence_electricity_efficiency') }}%
```

### 8. Data Refresh on Connection Issues
```yaml
automation:
  - alias: "Red Energy - Auto Refresh on Error"
    description: "Automatically refresh data when sensors become unavailable"
    trigger:
      - platform: state
        entity_id: 
          - sensor.main_residence_electricity_daily_usage
          - sensor.main_residence_gas_daily_usage
        to: "unavailable"
        for:
          minutes: 10
    action:
      - service: red_energy.refresh_data
      - delay:
          seconds: 30
      - service: notify.mobile_app_your_phone
        data:
          title: "🔄 Red Energy Data Refresh"
          message: "Sensor data was unavailable. Automatic refresh triggered."
        condition:
          - condition: template
            value_template: >
              {{ states('sensor.main_residence_electricity_daily_usage') == 'unavailable' }}
```

## Smart Home Integration

### 9. Energy Dashboard Integration
```yaml
# Template sensors for energy dashboard
template:
  - sensor:
      - name: "Total Electricity Usage"
        state: >
          {{ states('sensor.main_residence_electricity_total_usage') | float + 
             states('sensor.investment_property_electricity_total_usage') | float }}
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total
      
      - name: "Total Energy Cost"
        state: >
          {{ (states('sensor.main_residence_electricity_total_cost') | float +
              states('sensor.main_residence_gas_total_cost') | float +
              states('sensor.investment_property_electricity_total_cost') | float) | round(2) }}
        unit_of_measurement: "AUD"
        device_class: monetary
```

### 10. Voice Assistant Integration
```yaml
# Alexa/Google Assistant intents
intent_script:
  EnergyUsageIntent:
    speech:
      text: >
        Your current daily electricity usage is {{ states('sensor.main_residence_electricity_daily_usage') }} kilowatt hours,
        costing approximately {{ (states('sensor.main_residence_electricity_daily_usage') | float * 0.28) | round(2) }} dollars.
        Your energy efficiency is {{ states('sensor.main_residence_electricity_efficiency') }} percent.

  EnergyBudgetIntent:
    speech:
      text: >
        Your monthly energy budget is {{ states('input_number.energy_budget_remaining') }} dollars remaining.
        Current month spending is {{ states('sensor.main_residence_electricity_total_cost') | float + states('sensor.main_residence_gas_total_cost') | float }} dollars.
```

## Utility Scripts

### Energy Saving Mode Script
```yaml
script:
  energy_saving_mode:
    alias: "Energy Saving Mode"
    sequence:
      - service: climate.set_temperature
        target:
          entity_id: climate.main_ac
        data:
          temperature: 24  # Increase cooling temp
      - service: light.turn_off
        target:
          entity_id: all
      - service: switch.turn_off
        target:
          entity_id:
            - switch.pool_pump
            - switch.outdoor_lights
      - service: notify.mobile_app_your_phone
        data:
          title: "💡 Energy Saving Mode Activated"
          message: "AC temperature raised, non-essential lights/appliances turned off."
```

## Input Helpers
```yaml
input_number:
  energy_budget_remaining:
    name: "Energy Budget Remaining"
    min: 0
    max: 500
    step: 0.01
    unit_of_measurement: "AUD"
    icon: mdi:cash

  high_usage_threshold:
    name: "High Usage Alert Threshold"
    min: 10
    max: 50
    step: 1
    unit_of_measurement: "kWh"
    icon: mdi:flash
```

## Troubleshooting Automations

### 11. Sensor Health Check
```yaml
automation:
  - alias: "Red Energy - Sensor Health Check"
    description: "Monitor sensor health and data freshness"
    trigger:
      - platform: time_pattern
        hours: "/6"  # Every 6 hours
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🔍 Red Energy Health Check"
          message: >
            Sensor Status:
            {% for entity in ['sensor.main_residence_electricity_daily_usage', 'sensor.main_residence_gas_daily_usage'] %}
            • {{ state_attr(entity, 'friendly_name') }}: {{ 'OK' if states(entity) != 'unavailable' else 'ERROR' }}
            {% endfor %}
        condition:
          - condition: template
            value_template: >
              {{ states('sensor.main_residence_electricity_daily_usage') == 'unavailable' or
                 states('sensor.main_residence_gas_daily_usage') == 'unavailable' }}
```

These automation examples provide a comprehensive foundation for managing your Red Energy data in Home Assistant. Customize the thresholds, schedules, and actions to match your specific needs and energy goals.