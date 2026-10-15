"""Shelly failsafe drift check and one-click configuration (§3.1, §7.5)."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charging_pilot.const import DOMAIN
from custom_components.ev_charging_pilot.ha_ports import shelly_deviations

from .conftest import DATA, RELAY

HOST = "192.0.2.10"


@pytest.fixture(autouse=True)
def no_shelly_network():
    """Override the shared mock – these tests talk to a fake Shelly instead."""
    yield


def test_deviations_report_actual_and_expected():
    config = {"initial_state": "restore_last", "auto_on": False, "auto_on_delay": 60.0}
    deviations = shelly_deviations(config, 10)
    assert {d["key"] for d in deviations} == {"initial_state", "auto_on", "auto_on_delay"}
    assert shelly_deviations({"initial_state": "on", "auto_on": True, "auto_on_delay": 10},
                             10) == []


async def _setup(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={"mode": "dry_run"},
                            data={**DATA, "cp_relay": RELAY, "shelly_host": HOST})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_drift_shown_and_fixed_by_service(hass, halo, aioclient_mock):
    get_url = f"http://{HOST}/rpc/Switch.GetConfig"
    aioclient_mock.get(get_url, json={"id": 0, "initial_state": "off", "auto_on": False,
                                      "auto_on_delay": 60.0})
    entry = await _setup(hass)
    center = entry.runtime_data
    assert center.engine.shelly_config_ok is False
    assert {d["key"] for d in center.shelly_deviations} == {"initial_state", "auto_on",
                                                          "auto_on_delay"}

    aioclient_mock.clear_requests()
    aioclient_mock.post(f"http://{HOST}/rpc", json={"id": 0, "result": {
        "restart_required": False}})
    aioclient_mock.get(get_url, json={"id": 0, "initial_state": "on", "auto_on": True,
                                      "auto_on_delay": 10.0})
    result = await hass.services.async_call(DOMAIN, "configure_shelly", {}, blocking=True,
                                            return_response=True)
    assert result == {"ok": True, "deviations": []}
    sent = next(call for call in aioclient_mock.mock_calls if call[0] == "POST")
    assert sent[2]["params"]["config"] == {"initial_state": "on", "auto_on": True,
                                           "auto_on_delay": 10.0}
    assert any(e["code"] == "SHELLY_CONFIGURED" for e in center.events)


async def test_password_protected_shelly_gives_clear_error(hass, halo, aioclient_mock):
    aioclient_mock.get(f"http://{HOST}/rpc/Switch.GetConfig", status=401)
    aioclient_mock.post(f"http://{HOST}/rpc", status=401)
    entry = await _setup(hass)
    assert entry.runtime_data.engine.shelly_config_ok is None
    with pytest.raises(ServiceValidationError, match="Passwort"):
        await hass.services.async_call(DOMAIN, "configure_shelly", {}, blocking=True,
                                       return_response=True)
