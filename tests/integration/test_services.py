"""Replay service, notification actions, push delivery."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.ev_charging_pilot.const import ACTION_TONIGHT, CONF_NOTIFY_SERVICE, DOMAIN
from custom_components.ev_charging_pilot.core.inputs import Inp, RawState
from custom_components.ev_charging_pilot.core.replay import ReplayDataset

from .conftest import CABLE


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _dataset() -> dict:
    start = datetime(2026, 10, 13, 2, 50, tzinfo=dt_util.UTC)
    on, off = start + timedelta(minutes=10), start + timedelta(hours=2)
    states = {
        Inp.CHARGER_ENABLE: [RawState("off", start), RawState("on", on), RawState("off", off)],
        Inp.CABLE_CONNECTED: [RawState("on", start)],
        Inp.CHARGE_POWER: [RawState("0", start), RawState("2300", on + timedelta(seconds=40)),
                           RawState("0", off)],
        Inp.TOTAL_ENERGY: [RawState("100", start)],
    }
    return ReplayDataset("test", "UTC", start, off + timedelta(minutes=5), states,
                         plans=[{"id": "p", "weekdays": ["tue"], "mode": "fixed_start",
                                 "charge_start_time": "03:00", "departure_time": "04:50"}],
                         ).as_dict()


async def test_start_replay_with_inline_dataset(hass, entry, halo):
    calls = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)
    result = await hass.services.async_call(
        DOMAIN, "start_replay", {"dataset": _dataset(), "tick_s": 10}, blocking=True,
        return_response=True)
    assert result["agreement"] == 1.0
    assert calls == []  # replay never touches hardware
    assert entry.runtime_data.last_replay["name"] == "test"


async def test_plug_in_sends_actionable_push_and_action_sets_one_shot(hass, entry, halo):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={"mode": "dry_run"},
                            data={**entry.data, CONF_NOTIFY_SERVICE: "notify.mobile_app_phone"})
    pushes = async_mock_service(hass, "notify", "mobile_app_phone")
    await _setup(hass, entry)
    hass.states.async_set(CABLE, "off")
    await hass.async_block_till_done()
    hass.states.async_set(CABLE, "on")
    await hass.async_block_till_done()
    actionable = [p for p in pushes if "actions" in p.data.get("data", {})]
    if entry.runtime_data.engine.active_window is None:
        assert actionable, pushes
    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION_TONIGHT})
    await hass.async_block_till_done()
    assert entry.runtime_data.engine.one_shot is not None


async def test_set_plans_service_and_validation(hass, entry, halo):
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "set_plans", {"plans": [
        {"id": "a", "weekdays": ["mon"], "departure_time": "07:00"},
        {"id": "b", "weekdays": ["sat"], "departure_time": "10:00", "climate": "off"},
    ]}, blocking=True)
    assert [p.id for p in entry.runtime_data.engine.plans] == ["a", "b"]
    await hass.services.async_call(
        DOMAIN, "set_override", {"mode": "duration", "duration_min": 30}, blocking=True)
    assert entry.runtime_data.engine.override.expires_at is not None
    await hass.services.async_call(DOMAIN, "start_climate", {"minutes": "5"}, blocking=True)
    assert entry.runtime_data.engine.manual_climate.duration_min == 5


async def test_system_check_switches_nothing_and_can_send_a_test_push(hass, entry, halo,
                                                                      hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=2,
                            options={"mode": "live"},
                            data={**entry.data, CONF_NOTIFY_SERVICE: "notify.mobile_app_phone"})
    pushes = async_mock_service(hass, "notify", "mobile_app_phone")
    switched = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/run_system_check",
                            "send_test_push": True})
    msg = await client.receive_json()
    assert msg["success"], msg
    steps = {r["step"]: r for r in msg["result"]["results"]}
    assert steps["charger"]["status"] == "ok"
    assert steps["push"]["status"] == "ok"
    assert steps["mode"]["status"] == "ok"
    assert switched == []
    assert any(p.data["title"].endswith("Testnachricht") for p in pushes)
    assert any(e["code"] == "SYSTEM_CHECK" for e in entry.runtime_data.events)


async def test_weekly_summary_is_pushed(hass, entry, halo):
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=2,
                            options={"mode": "dry_run"},
                            data={**entry.data, CONF_NOTIFY_SERVICE: "notify.mobile_app_phone"})
    pushes = async_mock_service(hass, "notify", "mobile_app_phone")
    await _setup(hass, entry)
    text = await entry.runtime_data.async_weekly_summary(dt_util.utcnow())
    await hass.async_block_till_done()
    assert "kWh zuhause" in text
    assert any("Wochenrückblick" in p.data["title"] for p in pushes)


async def test_one_off_departure_service(hass, entry, halo):
    await _setup(hass, entry)
    await hass.services.async_call(DOMAIN, "start_one_shot", {
        "departure_at": "2026-10-16 07:00:00", "target_soc": 100}, blocking=True)
    shot = entry.runtime_data.engine.one_shot
    assert shot is not None and shot.preferred_departure_soc_pct == 100
