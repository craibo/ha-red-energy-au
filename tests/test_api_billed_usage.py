"""Tests for the /usage/billed API call."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.red_energy.api import RedEnergyAPI, RedEnergyAPIError

BILLED_PERIOD = {
    "fromDate": "2026-01-01",
    "toDate": "2026-03-31",
    "consumptionMj": 3600.0,
    "consumptionKwh": 1000.0,
    "totalChargesDollar": 220.0,
    "isPricingReliable": True,
}


def _api_with_response(status, json_value=None, json_side_effect=None):
    api = RedEnergyAPI(MagicMock())
    api._access_token = "test_token"
    api._ensure_valid_token = AsyncMock()

    response = AsyncMock()
    response.status = status
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=json_value, side_effect=json_side_effect)

    api._session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    api._session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    return api


@pytest.mark.asyncio
async def test_get_billed_usage_returns_raw_periods_and_sends_params():
    api = _api_with_response(200, json_value=[BILLED_PERIOD])

    result = await api.get_billed_usage("4000004", datetime(2025, 3, 1), datetime(2026, 4, 5))

    assert result == [BILLED_PERIOD]
    url = api._session.get.call_args.args[0]
    params = api._session.get.call_args.kwargs["params"]
    assert url.endswith("/usage/billed")
    assert params == {"consumerNumber": "4000004", "fromDate": "2025-03-01", "toDate": "2026-04-05"}


@pytest.mark.asyncio
async def test_get_billed_usage_400_raises_api_error_with_message():
    api = _api_with_response(400, json_value={"message": "Invalid consumer number"})

    with pytest.raises(RedEnergyAPIError, match="Invalid consumer number"):
        await api.get_billed_usage("4000004", datetime(2025, 3, 1), datetime(2026, 4, 5))


@pytest.mark.asyncio
async def test_get_billed_usage_400_without_json_still_raises_api_error():
    api = _api_with_response(400, json_side_effect=Exception("Invalid JSON"))

    with pytest.raises(RedEnergyAPIError, match="Bad Request"):
        await api.get_billed_usage("4000004", datetime(2025, 3, 1), datetime(2026, 4, 5))


@pytest.mark.asyncio
async def test_get_bills_returns_raw_bills():
    bills = [{"consumerNumber": 4000004, "toDate": "2026-03-31"}]
    api = _api_with_response(200, json_value=bills)

    result = await api.get_bills()

    assert result == bills
    assert api._session.get.call_args.args[0].endswith("/bills")
