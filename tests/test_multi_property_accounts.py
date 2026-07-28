"""Test accounts that bill more than one property.

Red Energy can bill several properties (different addresses, each with their
own consumer/meter) under a single accountNumber. accountNumber is the fallback
used for the property id, so without disambiguation every such property
collapses into one coordinator key, one device and one set of sensor
unique_ids - the user sees a single device and a single account to monitor no
matter how many services they actually have.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.red_energy.config_flow import (
    ConfigFlow,
    RedEnergyOptionsFlowHandler,
)
from custom_components.red_energy.const import (
    DATA_ACCOUNTS,
    DATA_CUSTOMER_DATA,
    DATA_SELECTED_ACCOUNTS,
    DOMAIN,
    SERVICE_TYPE_ELECTRICITY,
)
from custom_components.red_energy.coordinator import RedEnergyDataCoordinator
from custom_components.red_energy.data_validation import (
    format_account_label,
    validate_properties_data,
)

SHARED_ACCOUNT_NUMBER = 1001100


def _raw_property(account_number, property_number, consumer_number, short_form):
    """Build a raw /properties entry in the shape the API returns."""
    raw = {
        "accountNumber": account_number,
        "address": {
            "house": "1",
            "street": "SOME ST",
            "suburb": short_form.split(", ")[-1].upper(),
            "state": "NSW",
            "postcode": "2000",
            "displayAddresses": {"shortForm": short_form},
        },
        "consumers": [
            {
                "consumerNumber": consumer_number,
                "utility": "E",
                "status": "ON",
            }
        ],
    }
    if property_number is not None:
        raw["propertyNumber"] = property_number
    return raw


MULTI_PROPERTY_RESPONSE = [
    _raw_property(SHARED_ACCOUNT_NUMBER, 5000001, 3000003, "1 First St, Suburbia"),
    _raw_property(SHARED_ACCOUNT_NUMBER, 5000002, 3000004, "2 Second Ave, Othertown"),
]


def test_properties_sharing_an_account_number_get_unique_ids():
    """Two properties on one account must not collapse into a single id."""
    properties = validate_properties_data(MULTI_PROPERTY_RESPONSE)

    ids = [prop["id"] for prop in properties]
    assert len(properties) == 2
    assert len(set(ids)) == 2, f"ids collided: {ids}"
    assert ids == ["1001100_5000001", "1001100_5000002"]


def test_duplicate_ids_fall_back_to_consumer_number():
    """Without propertyNumber the consumer number keeps the properties apart."""
    raw = [
        _raw_property(SHARED_ACCOUNT_NUMBER, None, 3000003, "1 First St, Suburbia"),
        _raw_property(SHARED_ACCOUNT_NUMBER, None, 3000004, "2 Second Ave, Othertown"),
    ]

    ids = [prop["id"] for prop in validate_properties_data(raw)]

    assert ids == ["1001100_3000003", "1001100_3000004"]


def test_distinct_account_numbers_keep_their_existing_ids():
    """Only colliding ids are rewritten - existing entities must not churn.

    A suffix applied unconditionally would change the unique_id of every
    already-registered sensor, orphaning their history.
    """
    raw = [
        _raw_property(1000001, 5000001, 3000003, "27 Sunnyside Crescent, Castlecrag"),
        _raw_property(2000002, 5000002, 4000004, "9 Other Road, Elsewhere"),
    ]

    ids = [prop["id"] for prop in validate_properties_data(raw)]

    assert ids == ["1000001", "2000002"]


def test_property_and_account_numbers_are_preserved():
    """Both raw identifiers stay available for disambiguation and diagnostics."""
    prop = validate_properties_data(MULTI_PROPERTY_RESPONSE)[0]

    assert prop["property_number"] == "5000001"
    assert prop["account_number"] == "1001100"


def test_account_label_distinguishes_properties_on_one_account():
    """Labels for a shared account must differ - the address is the only clue."""
    properties = validate_properties_data(MULTI_PROPERTY_RESPONSE)

    labels = [
        format_account_label(
            prop["id"], prop["name"], [s["type"] for s in prop["services"]]
        )
        for prop in properties
    ]

    assert labels == [
        "1001100_5000001 - 1 First St, Suburbia - Electricity",
        "1001100_5000002 - 2 Second Ave, Othertown - Electricity",
    ]


def test_account_label_omits_a_name_that_only_repeats_the_id():
    """The synthetic "Property <id>" fallback name adds nothing to the label."""
    assert (
        format_account_label("1000001", "Property 1000001", ["electricity"])
        == "1000001 - Electricity"
    )


@pytest.mark.asyncio
async def test_config_flow_selects_every_property_on_a_shared_account(monkeypatch):
    """Initial setup must adopt both properties, not just one."""
    properties = validate_properties_data(MULTI_PROPERTY_RESPONSE)

    async def fake_validate_input(hass, data):
        return {
            DATA_CUSTOMER_DATA: {"name": "Test Customer"},
            DATA_ACCOUNTS: properties,
            "title": "Test Customer",
        }

    monkeypatch.setattr(
        "custom_components.red_energy.config_flow.validate_input", fake_validate_input
    )

    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = AsyncMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    await flow.async_step_user({"username": "test@example.com", "password": "testpass"})

    flow.async_create_entry.assert_called_once()
    _, kwargs = flow.async_create_entry.call_args
    assert kwargs["data"][DATA_SELECTED_ACCOUNTS] == [
        "1001100_5000001",
        "1001100_5000002",
    ]
    assert "2 properties" in kwargs["title"]


@pytest.mark.asyncio
async def test_options_flow_lists_every_property_on_a_shared_account():
    """The options checklist must offer both properties with distinct labels."""
    entry = MagicMock()
    entry.data = {
        "username": "test@example.com",
        "password": "testpass",
        DATA_SELECTED_ACCOUNTS: ["1001100_5000001", "1001100_5000002"],
        "services": [SERVICE_TYPE_ELECTRICITY],
    }
    entry.options = {}
    entry.entry_id = "test_entry_id"

    coordinator = MagicMock(update_interval=MagicMock(total_seconds=lambda: 1800))
    coordinator.api.get_properties = AsyncMock(return_value=MULTI_PROPERTY_RESPONSE)
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}
    hass.config_entries.async_get_known_entry = MagicMock(return_value=entry)

    flow = RedEnergyOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_init()

    accounts_validator = next(
        v for k, v in result["data_schema"].schema.items() if str(k) == "accounts"
    )
    labels = accounts_validator.options

    assert set(labels) == {"1001100_5000001", "1001100_5000002"}
    assert len(set(labels.values())) == 2


def _make_coordinator(selected_accounts, config_entry=None):
    hass = MagicMock()
    coordinator = RedEnergyDataCoordinator.__new__(RedEnergyDataCoordinator)
    coordinator.hass = hass
    coordinator.selected_accounts = selected_accounts
    coordinator.config_entry = config_entry
    coordinator._properties = validate_properties_data(MULTI_PROPERTY_RESPONSE)
    return coordinator


def test_coordinator_expands_a_legacy_bare_account_id():
    """An entry saved before disambiguation must adopt the derived properties.

    Its stored selection is the bare account number, which now matches no
    property id at all - left alone the entry fails to load with "No usage data
    retrieved" and the user has to delete and re-add the integration.
    """
    entry = MagicMock()
    entry.data = {DATA_SELECTED_ACCOUNTS: ["1001100"]}
    coordinator = _make_coordinator(["1001100"], config_entry=entry)

    coordinator._resolve_selected_accounts()

    assert coordinator.selected_accounts == ["1001100_5000001", "1001100_5000002"]
    _, kwargs = coordinator.hass.config_entries.async_update_entry.call_args
    assert kwargs["data"][DATA_SELECTED_ACCOUNTS] == [
        "1001100_5000001",
        "1001100_5000002",
    ]


def test_coordinator_leaves_a_matching_selection_alone():
    """A selection that already matches must not be rewritten or re-persisted."""
    coordinator = _make_coordinator(["1001100_5000001", "1001100_5000002"])

    coordinator._resolve_selected_accounts()

    assert coordinator.selected_accounts == ["1001100_5000001", "1001100_5000002"]
    coordinator.hass.config_entries.async_update_entry.assert_not_called()


def test_coordinator_keeps_an_account_the_api_did_not_return():
    """A transient API omission must not silently drop the user's selection."""
    coordinator = _make_coordinator(["1001100_5000001", "9999999"])

    coordinator._resolve_selected_accounts()

    assert "9999999" in coordinator.selected_accounts
