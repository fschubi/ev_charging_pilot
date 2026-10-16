"""Fixtures for the Home Assistant side of the integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charging_pilot.const import CONF_SHELLY_HOST, DOMAIN

CHARGER = "switch.halo_wallbox_connector_1"
CABLE = "binary_sensor.halo_wallbox_connector_1_cable_connected"
POWER = "sensor.halo_wallbox_connector_1_power"
ENERGY = "sensor.halo_wallbox_total_energy"
RELAY = "switch.mini_1_wallbox_wallbox_cp_unterbrechung"
SOC = "sensor.ovms_soc"

DATA = {
        "charger_enable": CHARGER,
    "cable_connected": CABLE,
    "charge_power": POWER,
    "total_energy": ENERGY,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fixed_time(freezer):
    """Tuesday noon in the test time zone – outside every default charging window.

    Without this the outcome depends on the wall clock (the default plan charges
    on weekday mornings).
    """
    freezer.move_to("2026-10-13 19:00:00+00:00")


@pytest.fixture(autouse=True)
def no_shelly_network():
    """The drift check would call the Shelly over HTTP – tests have no network."""
    with patch("custom_components.ev_charging_pilot.ha_ports.HaPorts.shelly_switch_config",
               return_value=None):
        yield


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data=dict(DATA), options={"mode": "dry_run"},
                           title="Mein EV Charging Pilot", version=2)


@pytest.fixture
def full_entry() -> MockConfigEntry:
    data = {**DATA, "cp_relay": RELAY, CONF_SHELLY_HOST: "192.0.2.10", "ovms_soc": SOC}
    return MockConfigEntry(domain=DOMAIN, data=data, options={"mode": "dry_run"},
                           title="Mein EV Charging Pilot", version=2)


@pytest.fixture
def halo(hass):
    """Halo entities: plugged in, switched off, no power."""
    hass.states.async_set(CHARGER, "off")
    hass.states.async_set(CABLE, "on")
    hass.states.async_set(POWER, "0", {"unit_of_measurement": "W"})
    hass.states.async_set(ENERGY, "1234.5", {"unit_of_measurement": "kWh"})
    hass.states.async_set(RELAY, "on")
    hass.states.async_set(SOC, "55", {"unit_of_measurement": "%"})
