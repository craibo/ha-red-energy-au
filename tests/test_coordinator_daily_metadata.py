"""Tests for coordinator metadata (customer/properties) refresh on every poll."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.red_energy.coordinator import RedEnergyDataCoordinator

OLD_LAST_BILL = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
NEW_LAST_BILL = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

USAGE = {
    "consumer_number": "elec-1",
    "from_date": "2026-01-01",
    "to_date": "2026-01-02",
    "usage_data": [{"date": "2026-01-01", "usage": 1.0, "cost": 1.0}],
}


def _raw_property(last_bill_date, balance):
    return {
        "accountNumber": "1000001",
        "displayAddresses": {"shortForm": "1 Example Street"},
        "consumers": [{
            "consumerNumber": "elec-1",
            "utility": "E",
            "status": "ON",
            "meterType": "INTERVAL",
            "lastBillDate": last_bill_date,
            "nextBillDate": "2099-01-01",
            "balance": balance,
        }],
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
            selected_accounts=["1000001"],
            services=["electricity"],
        )
    coordinator.api = AsyncMock()
    coordinator.api._access_token = "test_token"
    coordinator.api.get_customer_data = AsyncMock(return_value={"id": "customer1", "name": "Test Customer"})
    coordinator.api.get_usage_data = AsyncMock(return_value=USAGE)
    return coordinator


@pytest.mark.asyncio
async def test_metadata_refreshed_on_every_poll(coordinator):
    """A bill issued mid-day must be picked up by the next poll, not the next day."""
    coordinator.api.get_properties = AsyncMock(
        side_effect=[
            [_raw_property(OLD_LAST_BILL, 0.0)],
            [_raw_property(NEW_LAST_BILL, 44.4)],
        ]
    )

    first = await coordinator._async_update_data()
    second = await coordinator._async_update_data()

    assert coordinator.api.get_properties.await_count == 2
    assert coordinator.api.get_customer_data.await_count == 2
    first_service = first["usage_data"]["1000001"]["property"]["services"][0]
    second_service = second["usage_data"]["1000001"]["property"]["services"][0]
    assert first_service["lastBillDate"] == OLD_LAST_BILL
    assert second_service["lastBillDate"] == NEW_LAST_BILL


@pytest.mark.asyncio
async def test_refresh_metadata_and_usage_requests_single_refresh(coordinator):
    """The manual refresh must not fetch metadata twice now that every poll does."""
    coordinator._async_refresh_metadata = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()

    await coordinator.async_refresh_metadata_and_usage()

    coordinator._async_refresh_metadata.assert_not_awaited()
    coordinator.async_request_refresh.assert_awaited_once()
