"""Fixtures for the Home Assistant side of the integration."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_eq_charging.const import (
    CONF_CABLE_CONNECTED,
    CONF_CHARGE_POWER,
    CONF_CHARGER_ENABLE,
    CONF_TOTAL_ENERGY,
    DOMAIN,
)

CHARGER = "switch.halo_wallbox_connector_1"
CABLE = "binary_sensor.halo_wallbox_connector_1_cable_connected"
POWER = "sensor.halo_wallbox_connector_1_power"
ENERGY = "sensor.halo_wallbox_total_energy"

DATA = {
    CONF_CHARGER_ENABLE: CHARGER,
    CONF_CABLE_CONNECTED: CABLE,
    CONF_CHARGE_POWER: POWER,
    CONF_TOTAL_ENERGY: ENERGY,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data=dict(DATA), title="Smart EQ Charging Center")


@pytest.fixture
def halo(hass):
    """Halo entities: plugged in, switched off, no power."""
    hass.states.async_set(CHARGER, "off")
    hass.states.async_set(CABLE, "on")
    hass.states.async_set(POWER, "0", {"unit_of_measurement": "W"})
    hass.states.async_set(ENERGY, "1234.5", {"unit_of_measurement": "kWh"})
