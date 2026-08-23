"""Tests for the Projected Charges sensor (issue #75).

Projected charges is not a value the Red Energy API exposes anywhere -
unlike the billing period service charge (issue #71), which is derived
from a real rate the API does return. This is a linear extrapolation of
net cost-to-date (import cost minus export credit) across the full
billing cycle, so it must never be confused with an authoritative
Red Energy figure - hence the "estimation_method" attribute on the
sensor and the "estimated" framing throughout.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.const import (
    CONF_ENABLE_ADVANCED_SENSORS,
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
    SERVICE_TYPE_GAS,
)
from custom_components.red_energy.sensor import (
    RedEnergyProjectedChargesSensor,
    async_setup_entry,
)


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
    total_cost=None,
):
    """Build coordinator.data with both the property.services (metadata)
    and top-level services (usage) shapes get_service_metadata/get_service_usage
    expect."""
    service_metadata = {
        "type": SERVICE_TYPE_ELECTRICITY,
        "consumer_number": "elec-1",
        "meterType": "INTERVAL",
        "rates": [],
    }
    if last_bill_date is not None:
        service_metadata["lastBillDate"] = last_bill_date
    if next_bill_date is not None:
        service_metadata["nextBillDate"] = next_bill_date

    services_usage = {}
    if usage_entries is not None:
        services_usage[SERVICE_TYPE_ELECTRICITY] = {
            "consumer_number": "elec-1",
            "last_updated": "2024-01-30T10:00:00",
            "usage_data": {
                "from_date": "2024-01-01",
                "to_date": "2024-01-30",
                "usage_data": usage_entries,
                "total_cost": total_cost if total_cost is not None else 0.0,
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


class TestGetProjectedCharges:
    def test_seven_day_period_extrapolates_to_full_cycle(self, coordinator):
        """7 days elapsed, $35 net cost so far, 28-day cycle -> $140 projected."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            total_cost=35.0,
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        # elapsed = 2025-07-26..2025-08-01 inclusive = 7 days
        # cycle = 2025-07-25..2025-08-22 = 28 days
        assert result["projected_charges"] == pytest.approx(35.0 / 7 * 28)
        assert result["net_cost_to_date"] == pytest.approx(35.0)
        assert result["days_elapsed"] == 7
        assert result["days_in_cycle"] == 28

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
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date=None,
            total_cost=35.0,
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_next_bill_date_invalid(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date="not-a-date",
            total_cost=35.0,
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_next_bill_date_not_after_last_bill_date(self, coordinator):
        """A stale/inconsistent nextBillDate must not produce a zero or negative cycle length."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date="2025-07-25",
            total_cost=35.0,
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_returns_none_when_latest_usage_date_before_period_start(self, coordinator):
        """Stale/cached usage predating a just-rolled billing period must not produce a negative day count."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-07-20", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            total_cost=35.0,
        )
        assert coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY) is None

    def test_single_day_period_counts_as_one_day(self, coordinator):
        """lastBillDate + 1 == latest usageDate must count as exactly 1 day, not 0."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-07-26", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            total_cost=5.0,
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        # elapsed = 1 day, cycle = 28 days
        assert result["projected_charges"] == pytest.approx(5.0 / 1 * 28)

    def test_falls_back_to_30_day_period_when_last_bill_date_missing(self, coordinator):
        today = datetime.now()
        latest_usage_date = today.strftime("%Y-%m-%d")
        next_bill_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": latest_usage_date, "import_usage": 10.0}],
            last_bill_date=None,
            next_bill_date=next_bill_date,
            total_cost=60.0,
        )
        # billing_period_start falls back to (today - 30 days); nextBillDate
        # is still used verbatim as the cycle end even though lastBillDate
        # (the true cycle start metadata field) is missing.
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result is not None

    def test_uses_net_cost_not_gross(self, coordinator):
        """total_cost already reflects import minus export credit
        (see data_validation.py aggregation of the per-day "cost" field) -
        the projection must use it as-is, not re-derive a gross figure."""
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            total_cost=-2.0,  # net exporter/credit for the period so far
        )
        result = coordinator.get_projected_charges("2000002", SERVICE_TYPE_ELECTRICITY)
        assert result["projected_charges"] == pytest.approx(-2.0 / 7 * 28)


from homeassistant.components.sensor import SensorDeviceClass


def _config_entry():
    entry = MagicMock()
    entry.entry_id = "entry1"
    return entry


class TestProjectedChargesSensor:
    def test_native_value_and_attributes(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            next_bill_date="2025-08-22",
            total_cost=35.0,
        )
        sensor = RedEnergyProjectedChargesSensor(
            coordinator, _config_entry(), "2000002", SERVICE_TYPE_ELECTRICITY
        )
        assert sensor.native_value == pytest.approx(35.0 / 7 * 28)
        assert sensor.device_class == SensorDeviceClass.MONETARY
        assert sensor.native_unit_of_measurement == "AUD"
        assert sensor.state_class is None

        attrs = sensor.extra_state_attributes
        assert attrs["net_cost_to_date"] == pytest.approx(35.0)
        assert attrs["days_elapsed"] == 7
        assert attrs["days_in_cycle"] == 28
        assert attrs["estimation_method"] == "linear"

    def test_native_value_none_when_next_bill_date_missing(self, coordinator):
        _set_coordinator_data(
            coordinator,
            usage_entries=[{"date": "2025-08-01", "import_usage": 10.0}],
            last_bill_date="2025-07-25",
            total_cost=35.0,
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
async def test_projected_charges_sensor_not_created_when_advanced_disabled():
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

    projected_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyProjectedChargesSensor)
    ]
    assert projected_sensors == []


@pytest.mark.asyncio
async def test_projected_charges_sensor_created_for_electricity_and_gas_when_advanced_enabled():
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

    projected_sensors = [
        e for e in added_entities if isinstance(e, RedEnergyProjectedChargesSensor)
    ]
    assert len(projected_sensors) == 2
