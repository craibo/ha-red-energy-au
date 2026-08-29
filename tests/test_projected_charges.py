"""Tests for the Projected Net Cost / Projected Charges sensors
(issues #75, #77, and the #70 follow-up comment).

Neither value is exposed by the Red Energy API - both are linear
extrapolations built from usage/billing metadata the integration already
has, so they must never be confused with an authoritative Red Energy
figure - hence the "estimation_method" attribute on both sensors.

Three corrections from the original #75 implementation are covered here:
- GST: import_cost (sourced from consumptionDollar) is ex-GST at the API
  boundary; every cost/estimate/projection sensor must be GST-inclusive,
  so get_total_import_cost/get_latest_import_cost uplift it by
  GST_MULTIPLIER. export_credit (FIT/solar credit) has no GST component
  and is never uplifted.
- days_in_cycle off-by-one: nextBillDate is an exclusive boundary (first
  day of the *next* cycle), symmetric with lastBillDate being excluded via
  the +1 day in billing_period_start - using billing_period_start (not
  raw lastBillDate) as the days_in_cycle anchor keeps both boundaries
  treated the same way.
- The original "Projected Charges" sensor is renamed to "Projected Net
  Cost" to disclose it's energy-only (no service charge). A new
  "Projected Charges" sensor takes its old name and adds the service
  charge for a fuller bill estimate.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import (
    CONF_ENABLE_ADVANCED_SENSORS,
    DOMAIN,
    GST_MULTIPLIER,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
)
from custom_components.red_energy.sensor import (
    RedEnergyProjectedChargesSensor,
    RedEnergyProjectedNetCostSensor,
    async_setup_entry,
)

SUPPLY_CHARGE_RATE = {
    "rate_code": "80008279798F",
    "rate_desc": "Service To Property",
    "rate_incl_gst_dollars": 1.78145,
    "type": "F",
    "rate_excl_gst_cents": 161.95,
    "discounted_rate_excl_gst_in_cents": 161.95,
    "discounted_rate_incl_gst_in_cents": 178.145,
    "unit": "Day",
    "unit_step_desc": None,
}


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    return hass


@pytest.fixture
def coordinator(mock_hass):
    with patch(
        "custom_components.red_energy.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        coord = RedEnergyDataCoordinator(
            hass=mock_hass,
            username="test_user",
            password="test_pass",
            selected_accounts=["2000002"],
            services=["electricity"],
        )
    coord.api = AsyncMock()
    coord.api._access_token = "test_token"
    return coord


def _set_coordinator_data(
    coordinator,
    usage_entries=None,
    last_bill_date=None,
    next_bill_date=None,
    rates=None,
    plan_name=None,
):
    """Build coordinator.data with both the property.services (metadata)
    and top-level services (usage) shapes get_service_metadata/get_service_usage
    expect. usage_entries carry raw import_cost/export_credit (ex-GST on
    import) so get_total_import_cost's uplift is exercised end to end,
    rather than pre-computing a "total_cost" the old fixture shape used."""
    service_metadata = {
        "type": SERVICE_TYPE_ELECTRICITY,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": rates or [],
    }
    if last_bill_date is not None:
        service_metadata["lastBillDate"] = last_bill_date
    if next_bill_date is not None:
        service_metadata["nextBillDate"] = next_bill_date
    if plan_name is not None:
        service_metadata["planName"] = plan_name

    services_usage = {}
    if usage_entries is not None:
        services_usage[SERVICE_TYPE_ELECTRICITY] = {
            "consumer_number": "elec-1",
            "last_updated": "2024-01-30T10:00:00",
            "usage_data": {
                "from_date": "2024-01-01",
                "to_date": "2024-01-30",
                "usage_data": usage_entries,
            },
        }

    coordinator.data = {
        "usage_data": {
            "2000002": {
                "property": {
                    "name": "Test property",
                    "address": {},
                    "services": [service_metadata],
                },
                "services": services_usage,
            },
        }
    }


def _entry(date, import_cost, export_credit=0.0, max_demand_kw=None):
    entry = {"date": date, "import_usage": 10.0, "import_cost": import_cost, "export_credit": export_credit}
    if max_demand_kw is not None:
        entry["max_demand_kw"] = max_demand_kw
    return entry


DEMAND_CHARGE_RATE = {
    "rate_code": "80008279798FB",
    "rate_desc": "Demand Summer",
    "rate_incl_gst_dollars": 0.253,
    "type": "F",
    "rate_excl_gst_cents": 23,
    "discounted_rate_excl_gst_in_cents": 23,
    "discounted_rate_incl_gst_in_cents": 25.3,
    "unit": "KW/day",
    "unit_step_desc": None,
}

DEMAND_CHARGE_RATE_NON_SUMMER = {
    "rate_code": "80008279798FC",
    "rate_desc": "Demand Non Summer",
    "rate_incl_gst_dollars": 0.253,
    "type": "F",
    "rate_excl_gst_cents": 23,
    "discounted_rate_excl_gst_in_cents": 23,
    "discounted_rate_incl_gst_in_cents": 25.3,
    "unit": "KW/day",
    "unit_step_desc": None,
}

DEMAND_CHARGE_RATE_TEMPERATE = {
    "rate_code": "80008279798FD",
    "rate_desc": "Demand Temperate Peak",
    "rate_incl_gst_dollars": 0.154,
    "type": "F",
    "rate_excl_gst_cents": 14,
    "discounted_rate_excl_gst_in_cents": 14,
    "discounted_rate_incl_gst_in_cents": 15.4,
    "unit": "KW/day",
    "unit_step_desc": None,
}


class TestGetProjectedCharges:
    def test_seven_day_period_extrapolates_to_full_cycle(self, coordinator):
        """7 days elapsed, $35 ex-GST import cost so far (no export), 28-day
        cycle -> GST-inclusive net cost extrapolated across 28 days."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        # elapsed = 2025-07-26..2025-08-01 inclusive = 7 days
        # cycle = billing_period_start (2025-07-26) .. nextBillDate (2025-08-22) = 27 days
        net_cost_to_date = 35.0 * GST_MULTIPLIER
        assert result["net_cost_to_date"] == pytest.approx(net_cost_to_date)
        assert result["days_elapsed"] == 7
        assert result["days_in_cycle"] == 27
        assert result["projected_charges"] == pytest.approx(net_cost_to_date / 7 * 27)

    def test_days_in_cycle_excludes_next_bill_date_as_a_charge_day(self, coordinator):
        """Reproduces the #70 follow-up comment's real-world case: cycle
        26 Jul-25 Aug (31 charge days), latest usage 24 Aug (30 days
        elapsed). nextBillDate (26 Aug) must not be counted as part of this
        cycle - days_in_cycle must be 31, not 32."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2026-08-24", 300.0)],
            last_bill_date="2026-07-25",
            next_bill_date="2026-08-26",
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result["days_in_cycle"] == 31
        assert result["days_elapsed"] == 30

    def test_returns_none_when_no_usage_data(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_next_bill_date_missing(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date=None,
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_next_bill_date_invalid(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="not-a-date",
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_next_bill_date_not_after_last_bill_date(self, coordinator):
        """A stale/inconsistent nextBillDate must not produce a zero or negative cycle length."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-07-26",  # == billing_period_start, so days_in_cycle == 0
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_latest_usage_date_before_period_start(self, coordinator):
        """Stale/cached usage predating a just-rolled billing period must not produce a negative day count."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-07-20", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_single_day_period_counts_as_one_day(self, coordinator):
        """lastBillDate + 1 == latest usageDate must count as exactly 1 day, not 0."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-07-26", 5.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result["days_elapsed"] == 1
        assert result["days_in_cycle"] == 27
        net_cost_to_date = 5.0 * GST_MULTIPLIER
        assert result["projected_charges"] == pytest.approx(net_cost_to_date / 1 * 27)

    def test_falls_back_to_30_day_period_when_last_bill_date_missing(self, coordinator):
        today = datetime.now()
        latest_usage_date = today.strftime("%Y-%m-%d")
        next_bill_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry(latest_usage_date, 60.0)],
            last_bill_date=None,
            next_bill_date=next_bill_date,
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is not None

    def test_uses_net_cost_not_gross(self, coordinator):
        """Export credit reduces the GST-inclusive import cost; the
        projection must reflect that net figure, not gross import alone."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 5.0, export_credit=10.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        net_cost_to_date = 5.0 * GST_MULTIPLIER - 10.0
        assert net_cost_to_date < 0  # net exporter/credit for the period so far
        assert result["net_cost_to_date"] == pytest.approx(net_cost_to_date)
        assert result["projected_charges"] == pytest.approx(net_cost_to_date / 7 * 27)


class TestGetEstimatedCurrentPeriodCharges:
    def test_adds_service_charge_projected_across_full_cycle(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            rates=[SUPPLY_CHARGE_RATE],
        )
        result = coordinator.get_estimated_current_period_charges("2000002", SERVICE_TYPE_ELECTRICITY)

        net_cost_to_date = 35.0 * GST_MULTIPLIER
        expected_net_projection = net_cost_to_date / 7 * 27
        expected_service_charge = SUPPLY_CHARGE_RATE["rate_incl_gst_dollars"] * 27

        assert result["days_in_cycle"] == 27
        assert result["estimated_net_cost"] == pytest.approx(expected_net_projection)
        assert result["estimated_service_charge"] == pytest.approx(expected_service_charge)
        assert result["estimated_charges"] == pytest.approx(expected_net_projection + expected_service_charge)
        assert result["service_rate_incl_gst"] == pytest.approx(SUPPLY_CHARGE_RATE["rate_incl_gst_dollars"])

    def test_returns_none_when_no_service_charge_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            rates=[],
        )
        assert coordinator.get_estimated_current_period_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_projection_unavailable(self, coordinator):
        """No rate for the service charge, and separately, no usable
        projection (missing nextBillDate) - either alone must return None."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date=None,
            rates=[SUPPLY_CHARGE_RATE],
        )
        assert coordinator.get_estimated_current_period_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_includes_demand_charge_for_demand_plan(self, coordinator):
        """On a Demand plan with a resolvable seasonal rate and max demand
        data, a third term - the demand charge extrapolated across the
        full cycle - is added into estimated_charges."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2026-01-18", 35.0, max_demand_kw=4.608)],
            last_bill_date="2026-01-01",
            next_bill_date="2026-01-31",
            rates=[SUPPLY_CHARGE_RATE, DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_estimated_current_period_charges("2000002", SERVICE_TYPE_ELECTRICITY)

        assert result is not None
        # billing_period_start = 2026-01-02, days_in_cycle = Jan 2..Jan 31 (nextBillDate, exclusive) = 29 days
        assert result["days_in_cycle"] == 29
        expected_demand_charge = 4.608 * 0.253 * 29
        assert result["estimated_demand_charge"] == pytest.approx(expected_demand_charge)
        assert result["demand_rate_incl_gst"] == pytest.approx(0.253)
        assert result["estimated_charges"] == pytest.approx(
            result["estimated_net_cost"] + result["estimated_service_charge"] + result["estimated_demand_charge"]
        )

    def test_omits_demand_charge_for_non_demand_plan(self, coordinator):
        """Non-Demand-plan accounts (e.g. Time of Use) must be byte-for-byte
        unaffected - no estimated_demand_charge/demand_rate_incl_gst keys,
        and estimated_charges unchanged from the pre-Task-2 calculation."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            rates=[SUPPLY_CHARGE_RATE],
            plan_name="Residential Time of Use",
        )
        result = coordinator.get_estimated_current_period_charges("2000002", SERVICE_TYPE_ELECTRICITY)

        net_cost_to_date = 35.0 * GST_MULTIPLIER
        expected_net_projection = net_cost_to_date / 7 * 27
        expected_service_charge = SUPPLY_CHARGE_RATE["rate_incl_gst_dollars"] * 27

        assert result is not None
        assert "estimated_demand_charge" not in result
        assert "demand_rate_incl_gst" not in result
        assert result["estimated_charges"] == pytest.approx(expected_net_projection + expected_service_charge)

    def test_omits_demand_charge_when_no_resolvable_demand_rate(self, coordinator):
        """Demand plan, but the demand rates present don't unambiguously
        resolve for the current season - the demand-charge term must be
        omitted entirely, not guessed, and estimated_charges must not
        return None because of it."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2026-01-18", 35.0, max_demand_kw=4.608)],
            last_bill_date="2026-01-01",
            next_bill_date="2026-01-31",
            # Only a Non-Summer demand rate is present; on_date resolves to
            # Summer, so _get_demand_rate returns None (zero matches).
            rates=[SUPPLY_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER],
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_estimated_current_period_charges("2000002", SERVICE_TYPE_ELECTRICITY)

        assert result is not None
        assert "estimated_demand_charge" not in result
        assert "demand_rate_incl_gst" not in result

    def test_omits_demand_charge_when_no_max_demand_data(self, coordinator):
        """Demand plan with a resolvable rate but no usage entry carries
        max_demand_kw - the demand-charge term must be omitted, not raise
        or return None for the whole estimate."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2026-01-18", 35.0)],  # no max_demand_kw
            last_bill_date="2026-01-01",
            next_bill_date="2026-01-31",
            rates=[SUPPLY_CHARGE_RATE, DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_estimated_current_period_charges("2000002", SERVICE_TYPE_ELECTRICITY)

        assert result is not None
        assert "estimated_demand_charge" not in result
        assert "demand_rate_incl_gst" not in result


from homeassistant.components.sensor import SensorDeviceClass


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


class TestProjectedNetCostSensor:
    def test_native_value_and_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
        )
        sensor = RedEnergyProjectedNetCostSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        net_cost_to_date = 35.0 * GST_MULTIPLIER
        assert sensor.native_value == pytest.approx(net_cost_to_date / 7 * 27, abs=0.01)
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class is None

        attrs = sensor.extra_state_attributes
        assert attrs["net_cost_to_date"] == pytest.approx(net_cost_to_date)
        assert attrs["days_elapsed"] == 7
        assert attrs["days_in_cycle"] == 27
        assert attrs["gst_basis"] == "inclusive"

    def test_native_value_none_when_next_bill_date_missing(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyProjectedNetCostSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None


class TestProjectedChargesSensor:
    def test_native_value_and_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            rates=[SUPPLY_CHARGE_RATE],
        )
        sensor = RedEnergyProjectedChargesSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )

        net_cost_to_date = 35.0 * GST_MULTIPLIER
        expected_net_projection = net_cost_to_date / 7 * 27
        expected_service_charge = SUPPLY_CHARGE_RATE["rate_incl_gst_dollars"] * 27

        assert sensor.native_value == pytest.approx(
            expected_net_projection + expected_service_charge, abs=0.01
        )
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class is None

        attrs = sensor.extra_state_attributes
        assert attrs["days_in_cycle"] == 27
        assert attrs["gst_basis"] == "inclusive"
        assert attrs["service_rate_incl_gst"] == pytest.approx(SUPPLY_CHARGE_RATE["rate_incl_gst_dollars"])

    def test_native_value_none_when_no_service_charge_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[_entry("2025-08-01", 35.0)],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            rates=[],
        )
        sensor = RedEnergyProjectedChargesSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None


def _mock_coordinator_for_setup(service_type=SERVICE_TYPE_ELECTRICITY, property_id="2000002"):
    coordinator = MagicMock()
    service_metadata = {
        "type": service_type,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": [],
    }
    coordinator.data = {
        "usage_data": {
            property_id: {
                "property": {"name": "Test property", "address": {}, "services": [service_metadata]},
                "services": {},
            },
        }
    }
    coordinator.last_update_success = True
    coordinator.get_property_data = MagicMock(
        side_effect=lambda pid: coordinator.data["usage_data"].get(str(pid))
    )

    def get_service_metadata(prop_id, svc_type):
        property_data = coordinator.data["usage_data"].get(str(prop_id))
        if not property_data:
            return None
        services = property_data["property"].get("services", [])
        return next((s for s in services if s.get("type") == svc_type), None)

    coordinator.get_service_metadata = MagicMock(side_effect=get_service_metadata)
    coordinator.get_service_rates = MagicMock(return_value=[])
    coordinator.get_service_usage = MagicMock(return_value=None)
    return coordinator


@pytest.mark.asyncio
async def test_projected_sensors_not_created_when_advanced_disabled():
    coordinator = _mock_coordinator_for_setup()
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["2000002"],
                "services": [SERVICE_TYPE_ELECTRICITY],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))
    await async_setup_entry(hass, config_entry, async_add_entities)

    assert not [e for e in added_entities if isinstance(e, RedEnergyProjectedNetCostSensor)]
    assert not [e for e in added_entities if isinstance(e, RedEnergyProjectedChargesSensor)]


@pytest.mark.asyncio
async def test_projected_sensors_created_for_electricity_and_gas_when_advanced_enabled():
    coordinator = _mock_coordinator_for_setup(service_type=SERVICE_TYPE_ELECTRICITY)
    gas_coordinator_data = coordinator.data["usage_data"]["2000002"]["property"]["services"]
    gas_coordinator_data.append({**gas_coordinator_data[0], "type": SERVICE_TYPE_GAS})

    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    config_entry.options = {CONF_ENABLE_ADVANCED_SENSORS: True}

    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "entry1": {
                "coordinator": coordinator,
                "selected_accounts": ["2000002"],
                "services": [SERVICE_TYPE_ELECTRICITY, SERVICE_TYPE_GAS],
            }
        }
    }

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))
    await async_setup_entry(hass, config_entry, async_add_entities)

    net_cost_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyProjectedNetCostSensor)
    ]
    charges_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyProjectedChargesSensor)
    ]
    assert len(net_cost_sensors) == 2
    assert len(charges_sensors) == 2
