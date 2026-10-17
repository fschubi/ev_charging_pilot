"""Setup, entity IDs (§12), dry-run safety, services and WebSocket API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.ev_charging_pilot.const import DOMAIN
from custom_components.ev_charging_pilot.core.inputs import Inp

from .conftest import CABLE, CHARGER


async def _setup(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_follow_masterplan_ids(hass, entry, halo):
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    for entity_id in (
        "sensor.ev_pilot_executor_state", "sensor.ev_pilot_desired_reason",
        "sensor.ev_pilot_system_health", "sensor.ev_pilot_next_charge_start",
        "sensor.ev_pilot_month_home_energy", "sensor.ev_pilot_year_cost",
        "binary_sensor.ev_pilot_vehicle_connected", "binary_sensor.ev_pilot_manual_override",
        "switch.ev_pilot_automation", "switch.ev_pilot_dry_run",
        "select.ev_pilot_override_mode", "number.ev_pilot_minimum_departure_soc",
        "time.ev_pilot_departure", "button.ev_pilot_start_charge",
        "button.ev_pilot_one_shot_tonight",
    ):
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.states.get("switch.ev_pilot_dry_run").state == "on"
    assert hass.states.get("sensor.ev_pilot_executor_state").state == "idle"
    assert hass.states.get("sensor.ev_pilot_system_health").state == "healthy"
    # Without OVMS and Shelly no vehicle sensors and no CP button.
    assert hass.states.get("sensor.ev_pilot_soc") is None
    assert hass.states.get("button.ev_pilot_cp_wakeup") is None


async def test_optional_entities_with_ovms_and_shelly(hass, full_entry, halo):
    await _setup(hass, full_entry)
    assert hass.states.get("sensor.ev_pilot_soc").state == "55.0"
    assert hass.states.get("button.ev_pilot_cp_wakeup") is not None
    assert hass.states.get("binary_sensor.ev_pilot_cp_failsafe_ok").state == "off"


async def test_start_charge_in_dry_run_only_logs(hass, entry, halo):
    calls = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.ev_pilot_start_charge"}, blocking=True)
    await hass.async_block_till_done()
    assert calls == []
    center = entry.runtime_data
    assert any(e["code"] == "DRY_RUN" for e in center.events)
    assert hass.states.get("binary_sensor.ev_pilot_manual_override").state == "on"
    assert hass.states.get("select.ev_pilot_override_mode").state == "until_unplugged"


async def test_live_mode_switches_halo(hass, entry, halo):
    calls = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.ev_pilot_dry_run"}, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["mode"] == "live"
    assert entry.state is ConfigEntryState.LOADED
    await hass.services.async_call(DOMAIN, "start_charging", {}, blocking=True)
    await hass.async_block_till_done()
    assert [c.data["entity_id"] for c in calls] == [CHARGER]


async def test_automation_off_and_plan_entities(hass, entry, halo):
    await _setup(hass, entry)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.ev_pilot_automation"}, blocking=True)
    assert hass.states.get("sensor.ev_pilot_desired_reason").state == "automation_off"
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.ev_pilot_departure", "time": "06:45:00"},
        blocking=True)
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.ev_pilot_preferred_departure_soc", "value": 70}, blocking=True)
    plan = entry.runtime_data.engine.plans[0]
    assert plan.departure_time.strftime("%H:%M") == "06:45"
    assert plan.preferred_departure_soc_pct == 70
    assert plan.minimum_departure_soc_pct == 70


async def test_external_charge_export_and_statistics(hass, entry, halo, tmp_path):
    await _setup(hass, entry)
    response = await hass.services.async_call(
        DOMAIN, "add_external_charge",
        {"date": "2026-10-10", "energy_kwh": 7.5, "cost_eur": 4.2, "source": "public"},
        blocking=True, return_response=True)
    assert response["id"]
    center = entry.runtime_data
    assert len(center.monitor.data.external) == 1
    with patch.object(type(center), "data_dir", new=tmp_path):
        result = await hass.services.async_call(
            DOMAIN, "export", {"dataset": "external", "format": "csv"}, blocking=True,
            return_response=True)
    assert result["rows"] == 1
    assert (tmp_path / "export").exists()


async def test_websocket_state_and_plans(hass, entry, halo, hass_ws_client):
    await _setup(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/state"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["executor"]["state"] == "IDLE"
    manifest = json.loads((Path(__file__).parents[2] / "custom_components" / "ev_charging_pilot"
                           / "manifest.json").read_text())
    assert msg["result"]["version"] == manifest["version"]
    link = msg["result"]["vehicle_link"]
    assert link["data_configured"] is False
    assert link["read_write"] is False
    assert link["command_path"] is None
    assert link["commands_ready"] is False
    assert msg["result"]["plans"][0]["id"] == "plan-werktage"
    await client.send_json({"id": 2, "type": f"{DOMAIN}/set_plans", "plans": [
        {"id": "we", "name": "Wochenende", "weekdays": ["sat", "sun"],
         "departure_time": "09:00", "mode": "fixed_start", "charge_start_time": "04:00"}]})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert entry.runtime_data.engine.plans[0].id == "we"
    for number, kind in enumerate(("get_sessions", "get_trips", "get_external_charges",
                                   "get_month_statistics", "get_year_statistics",
                                   "get_temperature_statistics", "get_events", "get_health",
                                   "get_plan_preview", "get_replay"), start=3):
        await client.send_json({"id": number, "type": f"{DOMAIN}/{kind}"})
        msg = await client.receive_json()
        assert msg["success"], (kind, msg)


async def test_diagnostics(hass, full_entry, halo):
    from custom_components.ev_charging_pilot.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await _setup(hass, full_entry)
    diag = await async_get_config_entry_diagnostics(hass, full_entry)
    assert diag["config"]["shelly_host"] == "**REDACTED**"
    assert diag["state"]["executor"]["state"] == "IDLE"


async def test_unload_and_reload(hass, entry, halo):
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "start_charging")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_settings_and_deleted_plans_survive_restart(hass, entry, halo, hass_ws_client):
    """Regression: deleting every plan and switching vehicle access off must stick."""
    await _setup(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/set_settings",
                            "values": {"ovms_enabled": True}})
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    await client.send_json({"id": 2, "type": f"{DOMAIN}/set_settings",
                            "values": {"ovms_enabled": False}})
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    await client.send_json({"id": 3, "type": f"{DOMAIN}/set_plans", "plans": []})
    assert (await client.receive_json())["result"]["plans"] == []

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    center = entry.runtime_data
    assert center.engine.plans == []
    assert center.settings.ovms_enabled is False
    assert hass.states.get("number.ev_pilot_minimum_departure_soc").state == "unknown"
    # moving the slider without any plan creates the default plan instead of crashing
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.ev_pilot_minimum_departure_soc", "value": 60}, blocking=True)
    assert center.engine.plans[0].minimum_departure_soc_pct == 60


async def test_merged_safety_margin_is_migrated_away(hass, halo):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .conftest import DATA

    old = MockConfigEntry(domain=DOMAIN, version=2, minor_version=1, data=DATA,
                          options={"mode": "dry_run", "safety_margin_min": 20})
    await _setup(hass, old)
    assert old.minor_version == 2
    assert "safety_margin_min" not in old.options


async def test_existing_install_gets_the_ovms_plug(hass, full_entry, halo):
    registry = er.async_get(hass)
    plug = registry.async_get_or_create("sensor", "ovms", "plug",
                                        suggested_object_id="car_charge_plug_detected")
    tracker = registry.async_get_or_create("device_tracker", "ovms", "loc",
                                           suggested_object_id="car_location")
    hass.states.async_set(plug.entity_id, "yes")
    hass.states.async_set(tracker.entity_id, "home")
    hass.states.async_set(CABLE, "off")
    full_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    assert full_entry.data["ovms_plug"] == plug.entity_id
    assert full_entry.data["ovms_location"] == tracker.entity_id
    assert full_entry.runtime_data.engine.values[Inp.CABLE_CONNECTED].normalized is True


async def test_month_sensors_switch_period_together_with_their_values(hass, entry, halo, freezer):
    from datetime import datetime

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    tz = dt_util.get_default_time_zone()
    freezer.move_to(datetime(2026, 10, 31, 23, 59, 30, tzinfo=tz))
    await _setup(hass, entry)
    center = entry.runtime_data
    assert center.statistics["month"]["month"] == 10
    freezer.move_to(datetime(2026, 11, 1, 0, 0, 5, tzinfo=tz))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    # Figures and last_reset change in the same tick – no "new period, old total".
    assert center.statistics["month"]["month"] == 11
    state = hass.states.get("sensor.ev_pilot_month_home_energy")
    assert state.attributes["last_reset"].startswith("2026-11-01T00:00:00")


async def test_hanging_wallbox_command_times_out_and_frees_the_loop(hass, entry, halo):
    await _setup(hass, entry)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.ev_pilot_dry_run"}, blocking=True)
    await hass.async_block_till_done()
    center = entry.runtime_data

    async def hang(command, settings):
        raise TimeoutError  # what asyncio.timeout raises around a hanging cloud call

    with patch.object(center.ports, "execute", hang):
        await hass.services.async_call(DOMAIN, "start_charging", {}, blocking=True)
    assert any(e["code"] == "COMMAND_FAILED" and "keine Antwort nach 30 s" in e["message"]
               for e in center.events)
    assert not center._lock.locked()
