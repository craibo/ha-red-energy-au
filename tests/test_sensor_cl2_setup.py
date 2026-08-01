"""Tests for CL2/TOU derived sensor creation gating in async_setup_entry."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.red_energy.const import DOMAIN, CONF_ENABLE_ADVANCED_SENSORS
from custom_components.red_energy.sensor import async_setup_entry, RedEnergyCl2EnergySensor

RATES_WITH_CL2 = [
    {"rate_code": "P1", "rate_desc": "Peak", "rate_incl_gst_dollars": 0.4576},
    {"rate_code": "S1", "rate_desc": "Shoulder", "rate_incl_gst_dollars": 0.41745},
    {"rate_code": "O1", "rate_desc": "Off-peak", "rate_incl_gst_dollars": 0.32483},
    {"rate_code": "C1", "rate_desc": "CL2", "rate_incl_gst_dollars": 0.18425},
]

RATES_WITHOUT_CL2 = [
    {"rate_code": "P1", "rate_desc": "Peak", "rate_incl_gst_dollars": 0.4576},
]

# CL2 resolves unambiguously, but there are no separate Peak/Off-peak/Shoulder
# rates - some accounts use a single flat TOU rate ("Anytime") alongside CL2.
# PEAK/OFFPEAK/SHOULDER all land in unresolved_roles in this case.
RATES_CL2_RESOLVED_TOU_UNRESOLVED = [
    {"rate_code": "A1", "rate_desc": "Anytime", "rate_incl_gst_dollars": 0.35},
    {"rate_code": "C1", "rate_desc": "CL2", "rate_incl_gst_dollars": 0.18425},
]


def _make_coordinator(rates):
    coordinator = MagicMock()
    coordinator.get_service_metadata = MagicMock(
        return_value={"meterType": "SMART", "rates": rates}
    )
    coordinator.get_service_rates = MagicMock(return_value=rates)
    coordinator.last_update_success = True
    coordinator.data = {"usage_data": {"prop-001": {}}}
    return coordinator


def _make_config_entry(advanced_enabled=True):
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {CONF_ENABLE_ADVANCED_SENSORS: advanced_enabled}
    return entry


def _make_hass(coordinator, config_entry):
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            config_entry.entry_id: {
                "coordinator": coordinator,
                "selected_accounts": ["prop-001"],
                "services": ["electricity"],
            }
        }
    }
    return hass


@pytest.mark.asyncio
async def test_cl2_sensors_created_when_cl2_rate_resolves():
    coordinator = _make_coordinator(RATES_WITH_CL2)
    config_entry = _make_config_entry(advanced_enabled=True)
    hass = _make_hass(coordinator, config_entry)

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    cl2_energy_sensors = [e for e in added_entities if isinstance(e, RedEnergyCl2EnergySensor)]
    assert len(cl2_energy_sensors) == 1


@pytest.mark.asyncio
async def test_cl2_sensors_not_created_when_no_cl2_rate():
    coordinator = _make_coordinator(RATES_WITHOUT_CL2)
    config_entry = _make_config_entry(advanced_enabled=True)
    hass = _make_hass(coordinator, config_entry)

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    cl2_energy_sensors = [e for e in added_entities if isinstance(e, RedEnergyCl2EnergySensor)]
    assert len(cl2_energy_sensors) == 0


@pytest.mark.asyncio
async def test_cl2_sensors_not_created_when_tou_roles_unresolved():
    """CL2 alone resolving isn't enough - if PEAK/OFFPEAK/SHOULDER don't all
    resolve too, the coordinator's get_cl2_inference() would return None, so
    the sensors must not be created either (see final-review bug report)."""
    coordinator = _make_coordinator(RATES_CL2_RESOLVED_TOU_UNRESOLVED)
    config_entry = _make_config_entry(advanced_enabled=True)
    hass = _make_hass(coordinator, config_entry)

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    cl2_energy_sensors = [e for e in added_entities if isinstance(e, RedEnergyCl2EnergySensor)]
    assert len(cl2_energy_sensors) == 0


@pytest.mark.asyncio
async def test_cl2_sensors_not_created_when_advanced_sensors_disabled():
    coordinator = _make_coordinator(RATES_WITH_CL2)
    config_entry = _make_config_entry(advanced_enabled=False)
    hass = _make_hass(coordinator, config_entry)

    added_entities = []
    async_add_entities = MagicMock(side_effect=lambda entities: added_entities.extend(entities))

    await async_setup_entry(hass, config_entry, async_add_entities)

    cl2_energy_sensors = [e for e in added_entities if isinstance(e, RedEnergyCl2EnergySensor)]
    assert len(cl2_energy_sensors) == 0
