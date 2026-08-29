"""Tests for the Billing Period Service Charge sensor (issue #71)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import SERVICE_TYPE_ELECTRICITY
from custom_components.red_energy.sensor import (
    RedEnergyBillingPeriodServiceChargeSensor,
    RedEnergyCurrentPeriodDemandChargeSensor,
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

ENERGY_RATE = {
    "rate_code": "80008279798P",
    "rate_desc": "Peak",
    "rate_incl_gst_dollars": 0.27005,
    "type": "PR",
    "rate_excl_gst_cents": 24.55,
    "discounted_rate_excl_gst_in_cents": 24.55,
    "discounted_rate_incl_gst_in_cents": 27.005,
    "unit": "kWh",
    "unit_step_desc": None,
}

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

SECOND_SUPPLY_CHARGE_RATE = {
    "rate_code": "80008279798F2",
    "rate_desc": "Second Service To Property",
    "rate_incl_gst_dollars": 0.5,
    "type": "F",
    "rate_excl_gst_cents": 45.45,
    "discounted_rate_excl_gst_in_cents": 45.45,
    "discounted_rate_incl_gst_in_cents": 50.0,
    "unit": "day",
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


def _set_coordinator_data(coordinator, rates, usage_entries=None, last_bill_date=None, plan_name=None):
    """Build coordinator.data with both the property.services (metadata/rates)
    and top-level services (usage) shapes get_service_metadata/get_service_usage expect."""
    service_metadata = {
        "type": SERVICE_TYPE_ELECTRICITY,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": rates,
    }
    if last_bill_date is not None:
        service_metadata["lastBillDate"] = last_bill_date
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


class TestFindServiceChargeRate:
    def test_returns_none_when_no_rates(self, coordinator):
        _set_coordinator_data(coordinator, [])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_no_day_rate(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_finds_the_day_rate_among_others(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE, DEMAND_CHARGE_RATE, SUPPLY_CHARGE_RATE])
        result = coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == SUPPLY_CHARGE_RATE

    def test_uses_first_match_when_multiple_day_rates(self, coordinator):
        _set_coordinator_data(coordinator, [SUPPLY_CHARGE_RATE, SECOND_SUPPLY_CHARGE_RATE])
        result = coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == SUPPLY_CHARGE_RATE

    def test_non_day_unit_does_not_match(self, coordinator):
        rate = {**SUPPLY_CHARGE_RATE, "unit": "kWh"}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_type_is_irrelevant_to_matching(self, coordinator):
        """type alone can't distinguish the service charge - real payloads use
        the same type ("F") for both this charge and demand charges - so a
        rate with a different type still matches as long as unit == "day"."""
        rate = {**SUPPLY_CHARGE_RATE, "type": "PR"}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) == rate

    def test_demand_charge_kw_per_day_unit_does_not_match(self, coordinator):
        """Demand charges share type "F" with the service charge but use
        unit "KW/day", not a bare "day" - must not be mistaken for it."""
        _set_coordinator_data(coordinator, [DEMAND_CHARGE_RATE])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_unit_matching_is_case_insensitive(self, coordinator):
        """Real payloads have been observed sending both "day" and "Day" for
        this same charge across different accounts/services."""
        rate = {**SUPPLY_CHARGE_RATE, "unit": "day"}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) == rate

    def test_non_string_unit_does_not_match(self, coordinator):
        rate = {**SUPPLY_CHARGE_RATE, "unit": None}
        _set_coordinator_data(coordinator, [rate])
        assert coordinator._find_service_charge_rate("2000002", SERVICE_TYPE_ELECTRICITY) is None


class TestIsDemandPlan:
    def test_true_when_plan_name_contains_demand(self, coordinator):
        _set_coordinator_data(coordinator, [], plan_name="Residential Demand Solar")
        assert coordinator._is_demand_plan("2000002", SERVICE_TYPE_ELECTRICITY) is True

    def test_false_when_plan_name_has_no_demand(self, coordinator):
        _set_coordinator_data(coordinator, [], plan_name="Residential Time of Use")
        assert coordinator._is_demand_plan("2000002", SERVICE_TYPE_ELECTRICITY) is False

    def test_false_when_plan_name_missing(self, coordinator):
        """A missing/None planName must return False, never True - unknown
        must never be treated as "yes, add a demand charge.\""""
        _set_coordinator_data(coordinator, [])
        assert coordinator._is_demand_plan("2000002", SERVICE_TYPE_ELECTRICITY) is False

    def test_case_insensitive(self, coordinator):
        _set_coordinator_data(coordinator, [], plan_name="RESIDENTIAL DEMAND SOLAR")
        assert coordinator._is_demand_plan("2000002", SERVICE_TYPE_ELECTRICITY) is True


class TestGetDemandRate:
    def test_selects_summer_in_january(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 1, 15))
        assert rate["rate_desc"] == "Demand Summer"

    def test_selects_summer_in_december(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 12, 1))
        assert rate["rate_desc"] == "Demand Summer"

    def test_boundary_nov_1_is_summer(self, coordinator):
        """Summer runs 1 Nov - 31 Mar, wrapping the year boundary - Nov 1
        is the first day of Summer, not still Temperate."""
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 11, 1))
        assert rate["rate_desc"] == "Demand Summer"

    def test_boundary_oct_31_is_temperate(self, coordinator):
        """The day immediately before the Nov 1 Summer boundary must still
        resolve to Temperate, not Summer."""
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 10, 31))
        assert rate["rate_desc"] == "Demand Temperate Peak"

    def test_selects_non_summer_in_july(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 7, 15))
        assert rate["rate_desc"] == "Demand Non Summer"

    def test_selects_temperate_in_april(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 4, 15))
        assert rate["rate_desc"] == "Demand Temperate Peak"

    def test_selects_temperate_in_september(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 9, 30))
        assert rate["rate_desc"] == "Demand Temperate Peak"

    def test_returns_none_when_no_demand_rates(self, coordinator):
        _set_coordinator_data(coordinator, [ENERGY_RATE, SUPPLY_CHARGE_RATE])
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 1, 15))
        assert rate is None

    def test_returns_none_when_season_label_has_zero_matches(self, coordinator):
        """Plan only has a Summer demand rate; resolving for a Non-Summer
        date must not fall back to guessing the Summer rate."""
        _set_coordinator_data(coordinator, [DEMAND_CHARGE_RATE])
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 7, 15))
        assert rate is None

    def test_returns_none_when_season_label_ambiguous(self, coordinator):
        """Two rates share the same normalized rate_desc for the resolved
        season - must never guess which one applies."""
        duplicate_summer_rate = {**DEMAND_CHARGE_RATE, "rate_code": "80008279798FE", "rate_incl_gst_dollars": 0.30}
        _set_coordinator_data(coordinator, [DEMAND_CHARGE_RATE, duplicate_summer_rate])
        rate = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY, on_date=date(2026, 1, 15))
        assert rate is None

    def test_defaults_to_today_when_on_date_omitted(self, coordinator):
        """on_date defaults to datetime.now().date() - verify by using
        today's actual season rather than hardcoding an assumption about
        the current date."""
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        )
        expected = coordinator._get_demand_rate(
            "2000002", SERVICE_TYPE_ELECTRICITY, on_date=datetime.now().date()
        )
        actual = coordinator._get_demand_rate("2000002", SERVICE_TYPE_ELECTRICITY)
        assert actual == expected


class TestGetBillingPeriodServiceCharge:
    def test_seven_day_period_matches_issue_example(self, coordinator):
        last_bill_date = "2025-07-25"
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date=last_bill_date,
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == pytest.approx(7 * 1.78145)

    def test_returns_none_when_no_matching_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [ENERGY_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_no_usage_data(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_latest_usage_date_before_period_start(self, coordinator):
        """Stale/cached usage predating a just-rolled billing period must not produce a negative day count."""
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-07-20", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        assert coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_falls_back_to_30_day_period_when_last_bill_date_missing(self, coordinator):
        today = datetime.now()
        latest_usage_date = today.strftime("%Y-%m-%d")
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": latest_usage_date, "import_usage": 10.0}],
            last_bill_date=None,
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        expected_days = (today.date() - (today - timedelta(days=30)).date()).days + 1
        assert result == pytest.approx(expected_days * 1.78145)

    def test_single_day_period_counts_as_one_day(self, coordinator):
        """lastBillDate + 1 == latest usageDate must count as exactly 1 day, not 0."""
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-07-26", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        result = coordinator.get_billing_period_service_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result == pytest.approx(1 * 1.78145)


class TestGetBillingPeriodDemandCharge:
    def test_computes_accrued_demand_charge(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_billing_period_demand_charge("2000002", SERVICE_TYPE_ELECTRICITY)

        assert result is not None
        # represented_day_count = 2026-01-02 (lastBillDate + 1) .. 2026-01-18 inclusive = 17 days
        assert result["represented_day_count"] == 17
        assert result["max_demand_kw"] == 4.608
        assert result["demand_rate_incl_gst"] == pytest.approx(0.253)
        assert result["demand_rate_desc"] == "Demand Summer"
        assert result["demand_charge"] == pytest.approx(4.608 * 0.253 * 17)

    def test_none_when_not_demand_plan(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Time of Use",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_billing_period_demand_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is None

    def test_none_when_no_resolvable_demand_rate(self, coordinator):
        """Only a Non-Summer demand rate is present; resolving for a
        Summer date must not fall back to guessing it."""
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE_NON_SUMMER],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_billing_period_demand_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is None

    def test_none_when_no_max_demand_data(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0}],  # no max_demand_kw
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_billing_period_demand_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is None

    def test_none_when_no_usage_data(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        result = coordinator.get_billing_period_demand_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is None

    def test_none_when_latest_usage_date_before_period_start(self, coordinator):
        """Stale/cached usage predating a just-rolled billing period must not produce a negative day count."""
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2025-12-20", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        result = coordinator.get_billing_period_demand_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is None

    def test_single_day_period_counts_as_one_day(self, coordinator):
        """lastBillDate + 1 == latest usageDate must count as exactly 1 day, not 0."""
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-02", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 2)
            mock_dt.strptime = datetime.strptime
            result = coordinator.get_billing_period_demand_charge("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is not None
        assert result["represented_day_count"] == 1
        assert result["demand_charge"] == pytest.approx(4.608 * 0.253 * 1)


from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


class TestBillingPeriodServiceChargeSensor:
    def test_native_value_and_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value == pytest.approx(7 * 1.78145)
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class == SensorStateClass.TOTAL
        assert sensor._attr_name == "Current Period Service Charge"
        assert sensor._attr_unique_id.endswith("_billing_period_service_charge")

        attrs = sensor.extra_state_attributes
        assert attrs["billing_period_start"] == "2025-07-26"
        assert attrs["billing_period_end"] == "2025-08-01"
        assert attrs["latest_usage_date"] == "2025-08-01"
        assert attrs["represented_day_count"] == 7
        assert attrs["service_rate_incl_gst"] == pytest.approx(1.78145)
        assert attrs["service_rate_excl_gst"] == pytest.approx(1.6195)
        assert "calculation" in attrs

    def test_native_value_none_when_no_rate(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [ENERGY_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value is None
        assert sensor.extra_state_attributes is None

    def test_last_reset_matches_billing_period_start(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        # last_reset must match billing_period_start (lastBillDate + 1 day),
        # since lastBillDate is the last day of the *previous* period, not
        # the first day of the current one.
        assert sensor.last_reset.date().isoformat() == "2025-07-26"

    def test_last_reset_is_none_when_last_bill_date_missing(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [SUPPLY_CHARGE_RATE],
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
        )
        sensor = RedEnergyBillingPeriodServiceChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        # Without lastBillDate, last_reset must be None (stable), not a
        # datetime.now()-based fallback that drifts on every poll and would
        # reset HA's statistics accumulation each update.
        assert sensor.last_reset is None


class TestCurrentPeriodDemandChargeSensor:
    def test_native_value_and_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            sensor = RedEnergyCurrentPeriodDemandChargeSensor(
                coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
            )
            assert sensor.native_value == pytest.approx(round(4.608 * 0.253 * 17, 2))
            assert sensor.device_class == SensorDeviceClass.MONETARY
            assert sensor.native_unit_of_measurement == "AUD"
            assert sensor.state_class == SensorStateClass.TOTAL
            assert sensor._attr_name == "Current Period Demand Charge"
            assert sensor._attr_unique_id.endswith("_current_period_demand_charge")

            attrs = sensor.extra_state_attributes
        assert attrs == {
            "max_demand_kw": 4.608,
            "demand_rate_incl_gst": pytest.approx(0.253),
            "demand_rate_desc": "Demand Summer",
            "represented_day_count": 17,
        }

    def test_native_value_none_when_not_demand_plan(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Time of Use",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            sensor = RedEnergyCurrentPeriodDemandChargeSensor(
                coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
            )
            assert sensor.native_value is None
            assert sensor.extra_state_attributes is None

    def test_native_value_none_when_no_resolvable_demand_rate(self, coordinator):
        """Only a Non-Summer demand rate is present; resolving for a
        Summer date must not fall back to guessing it."""
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE_NON_SUMMER],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            sensor = RedEnergyCurrentPeriodDemandChargeSensor(
                coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
            )
            assert sensor.native_value is None
            assert sensor.extra_state_attributes is None

    def test_native_value_none_when_no_max_demand_data(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0}],  # no max_demand_kw
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        with patch("custom_components.red_energy.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 18)
            mock_dt.strptime = datetime.strptime
            sensor = RedEnergyCurrentPeriodDemandChargeSensor(
                coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
            )
            assert sensor.native_value is None
            assert sensor.extra_state_attributes is None

    def test_electricity_only_flag(self):
        assert RedEnergyCurrentPeriodDemandChargeSensor._electricity_only is True

    def test_last_reset_matches_billing_period_start(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            last_bill_date="2026-01-01",
            plan_name="Residential Demand Solar",
        )
        sensor = RedEnergyCurrentPeriodDemandChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        # last_reset must match billing_period_start (lastBillDate + 1 day),
        # since lastBillDate is the last day of the *previous* period, not
        # the first day of the current one.
        assert sensor.last_reset.date().isoformat() == "2026-01-02"

    def test_last_reset_is_none_when_last_bill_date_missing(self, coordinator):
        _set_coordinator_data(
            coordinator,
            [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
            usage_entries=[{"date": "2026-01-18", "import_usage": 10.0, "max_demand_kw": 4.608}],
            plan_name="Residential Demand Solar",
        )
        sensor = RedEnergyCurrentPeriodDemandChargeSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        # Without lastBillDate, last_reset must be None (stable), not a
        # datetime.now()-based fallback that drifts on every poll and would
        # reset HA's statistics accumulation each update.
        assert sensor.last_reset is None


from custom_components.red_energy.const import DOMAIN, CONF_ENABLE_ADVANCED_SENSORS, SERVICE_TYPE_GAS
from custom_components.red_energy.sensor import async_setup_entry


def _mock_coordinator_for_setup(rates, service_type=SERVICE_TYPE_ELECTRICITY, property_id="2000002"):
    coordinator = MagicMock()
    service_metadata = {
        "type": service_type,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": rates,
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

    def get_service_rates(prop_id, svc_type):
        metadata = get_service_metadata(prop_id, svc_type)
        return metadata.get("rates", []) if metadata else []

    coordinator.get_service_rates = MagicMock(side_effect=get_service_rates)
    coordinator.get_service_usage = MagicMock(return_value=None)
    return coordinator


@pytest.mark.asyncio
async def test_service_charge_sensors_not_created_when_advanced_disabled():
    coordinator = _mock_coordinator_for_setup([SUPPLY_CHARGE_RATE])
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

    charge_sensors = [
        e for e in added_entities
        if isinstance(e, RedEnergyBillingPeriodServiceChargeSensor)
    ]
    assert charge_sensors == []


@pytest.mark.asyncio
async def test_service_charge_sensors_created_for_electricity_and_gas_when_advanced_enabled():
    coordinator = _mock_coordinator_for_setup([SUPPLY_CHARGE_RATE], service_type=SERVICE_TYPE_ELECTRICITY)
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

    billing_charge_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyBillingPeriodServiceChargeSensor)
    ]
    assert len(billing_charge_sensors) == 2


@pytest.mark.asyncio
async def test_demand_charge_sensor_not_created_when_advanced_disabled():
    coordinator = _mock_coordinator_for_setup(
        [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE]
    )
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

    demand_charge_sensors = [
        e for e in added_entities
        if isinstance(e, RedEnergyCurrentPeriodDemandChargeSensor)
    ]
    assert demand_charge_sensors == []


@pytest.mark.asyncio
async def test_demand_charge_sensor_created_only_for_electricity_when_advanced_enabled():
    """Gas services must never get a demand charge sensor - only electricity
    gets one, even when both electricity and gas are configured."""
    coordinator = _mock_coordinator_for_setup(
        [DEMAND_CHARGE_RATE, DEMAND_CHARGE_RATE_NON_SUMMER, DEMAND_CHARGE_RATE_TEMPERATE],
        service_type=SERVICE_TYPE_ELECTRICITY,
    )
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

    demand_charge_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyCurrentPeriodDemandChargeSensor)
    ]
    assert len(demand_charge_sensors) == 1
    assert demand_charge_sensors[0]._service_type == SERVICE_TYPE_ELECTRICITY
