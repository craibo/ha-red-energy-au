"""Tests for coordinator routing of gas/BASIC meters to /usage/billed."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.red_energy.api import RedEnergyAPIError
from custom_components.red_energy.coordinator import (
    RedEnergyDataCoordinator,
    service_has_interval_usage,
)

RECENT_BILL_DATE = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

BILLED_PERIOD = {
    "fromDate": "2026-01-01",
    "toDate": "2026-03-31",
    "consumptionMj": 3600.0,
    "consumptionKwh": 1000.0,
    "totalChargesDollar": 220.0,
    "isPricingReliable": True,
}

INTERVAL_USAGE = {
    "consumer_number": "1000001",
    "from_date": "2026-01-01",
    "to_date": "2026-01-02",
    "usage_data": [{"date": "2026-01-01", "usage": 15.5, "cost": 25.50}],
}

BILL = {
    "consumerNumber": "gas-1",
    "fromDate": "2026-01-01",
    "toDate": "2026-03-31",
    "estimated": False,
    "meterReadings": [{
        "meterNumber": "MTR0001",
        "readingDate": "2026-03-31",
        "registers": [{"registerId": "1", "previousRead": 1000, "currentRead": 1091, "readType": "R"}],
    }],
}


def _service(service_type, consumer_number, meter_type):
    return {
        "type": service_type,
        "consumer_number": consumer_number,
        "active": True,
        "meterType": meter_type,
        "lastBillDate": RECENT_BILL_DATE,
    }


@pytest.fixture
def coordinator():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    with patch(
        "custom_components.red_energy.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        coordinator = RedEnergyDataCoordinator(
            hass=hass,
            username="test_user",
            password="test_pass",
            selected_accounts=["1000001", "2000002"],
            services=["electricity", "gas"],
        )
    coordinator.api = AsyncMock()
    coordinator.api._access_token = "test_token"
    coordinator._properties = [
        {"id": "1000001", "name": "Electricity", "services": [_service("electricity", "elec-1", "INTERVAL")]},
        {"id": "2000002", "name": "Gas", "services": [_service("gas", "gas-1", "BASIC")]},
    ]
    coordinator._customer_data = {"id": "customer1", "name": "Test Customer"}
    coordinator._last_metadata_refresh_date = datetime.now(timezone.utc).date()
    coordinator.api.get_usage_data = AsyncMock(return_value=INTERVAL_USAGE)
    coordinator.api.get_billed_usage = AsyncMock(return_value=[BILLED_PERIOD])
    coordinator.api.get_bills = AsyncMock(return_value=[BILL])
    return coordinator


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        ({"type": "electricity", "meterType": "INTERVAL"}, True),
        ({"type": "electricity"}, True),
        ({"type": "electricity", "meterType": "BASIC"}, False),
        ({"type": "gas", "meterType": "BASIC"}, False),
        ({"type": "gas"}, False),
    ],
)
def test_service_has_interval_usage(service, expected):
    assert service_has_interval_usage(service) is expected


@pytest.mark.asyncio
async def test_gas_service_uses_billed_endpoint_not_interval(coordinator):
    data = await coordinator._async_update_data()

    coordinator.api.get_billed_usage.assert_awaited_once()
    assert coordinator.api.get_billed_usage.call_args.args[0] == "gas-1"
    interval_consumers = [call.args[0] for call in coordinator.api.get_usage_data.call_args_list]
    assert interval_consumers == ["elec-1"]

    gas_service = data["usage_data"]["2000002"]["services"]["gas"]
    assert gas_service["consumer_number"] == "gas-1"
    assert gas_service["billed_usage"]["consumption_mj"] == 3600.0
    assert "usage_data" not in gas_service


@pytest.mark.asyncio
async def test_basic_electricity_service_uses_billed_endpoint(coordinator):
    coordinator._properties[0]["services"][0]["meterType"] = "BASIC"

    data = await coordinator._async_update_data()

    billed_consumers = sorted(call.args[0] for call in coordinator.api.get_billed_usage.call_args_list)
    assert billed_consumers == ["elec-1", "gas-1"]
    coordinator.api.get_usage_data.assert_not_awaited()
    # Meter reads are gas-only: /bills is fetched once, for the gas service
    coordinator.api.get_bills.assert_awaited_once()
    assert "meter_reading" not in data["usage_data"]["1000001"]["services"]["electricity"]


@pytest.mark.asyncio
async def test_billed_lookback_window_ends_today(coordinator):
    await coordinator._async_update_data()

    _, from_date, to_date = coordinator.api.get_billed_usage.call_args.args
    assert to_date.date() == datetime.now().date()
    assert (to_date - from_date).days == 400


@pytest.mark.asyncio
async def test_get_billed_usage_getter(coordinator):
    coordinator.data = await coordinator._async_update_data()

    assert coordinator.get_billed_usage("2000002", "gas")["days"] == 90
    assert coordinator.get_billed_usage("1000001", "electricity") is None
    assert coordinator.get_billed_usage("9999999", "gas") is None


@pytest.mark.asyncio
async def test_no_bills_yet_keeps_property_without_service_entry(coordinator):
    coordinator.api.get_billed_usage = AsyncMock(return_value=[])

    data = await coordinator._async_update_data()

    assert "2000002" in data["usage_data"]
    assert "gas" not in data["usage_data"]["2000002"]["services"]


@pytest.mark.asyncio
async def test_billed_400_skips_service_but_updates_others(coordinator, caplog):
    coordinator.api.get_billed_usage = AsyncMock(side_effect=RedEnergyAPIError("rejected"))

    data = await coordinator._async_update_data()

    assert "2000002" in data["usage_data"]
    assert "gas" not in data["usage_data"]["2000002"]["services"]
    assert "electricity" in data["usage_data"]["1000001"]["services"]
    assert "rejected" in caplog.text


@pytest.mark.asyncio
async def test_fetch_property_usage_path_also_uses_billed_endpoint(coordinator):
    result = await coordinator._fetch_property_usage(coordinator._properties[1])

    coordinator.api.get_usage_data.assert_not_awaited()
    assert result["services"]["gas"]["billed_usage"]["to_date"] == "2026-03-31"


@pytest.mark.asyncio
async def test_gas_service_stores_meter_reading(coordinator):
    coordinator.data = await coordinator._async_update_data()

    reading = coordinator.get_meter_reading("2000002", "gas")
    assert reading["previous_read"] == 1000.0
    assert reading["current_read"] == 1091.0
    assert coordinator.get_meter_reading("1000001", "electricity") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bills_mock",
    [
        AsyncMock(return_value=[]),
        AsyncMock(side_effect=aiohttp.ClientError("bills down")),
    ],
    ids=["no-bill-for-consumer", "bills-request-fails"],
)
async def test_missing_meter_reading_keeps_billed_usage(coordinator, bills_mock):
    coordinator.api.get_bills = bills_mock

    coordinator.data = await coordinator._async_update_data()

    assert coordinator.get_billed_usage("2000002", "gas")["consumption_mj"] == 3600.0
    assert coordinator.get_meter_reading("2000002", "gas") is None
