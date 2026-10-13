"""Engine: full ticks from raw states to commands, sessions and push intents."""

from __future__ import annotations

from datetime import datetime, time

from custom_components.smart_eq_charging.core.executor import ExecState
from custom_components.smart_eq_charging.core.inputs import Inp
from custom_components.smart_eq_charging.core.model import Reason
from custom_components.smart_eq_charging.core.planner import OverrideMode, WeeklySchedule
from custom_components.smart_eq_charging.core.ports import CommandKind

from .world import TZ, WITH_CP, WITH_OVMS, World


def local(*args):
    return datetime(*args, tzinfo=TZ)


def test_fixed_start_night_charges_and_records_session():
    # Tuesday 02:59, plan without SOC falls back to the fixed start 03:00.
    world = World(local(2026, 10, 13, 2, 59))
    world.run(55)
    assert CommandKind.ENABLE_CHARGER not in world.commands
    world.run(120)
    assert world.commands[0] is CommandKind.ENABLE_CHARGER
    assert world.engine.executor.state is ExecState.CHARGING
    assert world.engine.desired.reason is Reason.SCHEDULE
    # 05:30 departure ends the window → Halo off, session closed with energy and cost.
    world.now = local(2026, 10, 13, 5, 29, 55)
    world.tick(10)
    world.run(30)
    assert CommandKind.DISABLE_CHARGER in world.commands
    sessions = world.engine.monitor.data.sessions
    assert len(sessions) == 1
    assert sessions[0].success
    assert sessions[0].grid_energy_kwh > 0
    assert sessions[0].cost_eur > 0
    assert world.engine.last_result["success"] is True


def test_charge_now_override_and_unplug_ends_it():
    world = World(local(2026, 10, 13, 12, 0))
    world.engine.set_override(world.now, OverrideMode.UNTIL_UNPLUGGED)
    world.run(60)
    assert world.engine.executor.state is ExecState.CHARGING
    world.set(Inp.CABLE_CONNECTED, "off")
    world.tick()
    assert world.engine.override is None
    assert world.engine.executor.state is ExecState.DISCONNECTED
    assert "SESSION_END" in world.events


def test_automation_off_leaves_halo_alone():
    world = World(local(2026, 10, 13, 3, 30))
    world.engine.set_automation(world.now, False)
    world.set(Inp.CHARGER_ENABLE, "on")
    world.run(300)
    assert world.commands == []
    assert world.engine.desired.reason is Reason.AUTOMATION_OFF


def test_failed_start_pushes_and_records_failed_session():
    world = World(local(2026, 10, 13, 3, 0), configured=WITH_CP, cp_pulse=True,
                  cp_failsafe_verified=True)
    world.car_charges_when_enabled = False
    world.run(300)
    assert CommandKind.CP_PULSE in world.commands
    assert world.engine.executor.state is ExecState.START_FAILED
    assert "start_failed" in world.notifications
    failed = world.engine.monitor.data.sessions[-1]
    assert not failed.success
    assert failed.cp_wakeup_used
    assert failed.failure_code == "CHARGE_START_FAILED"


def test_shelly_unavailable_is_error_and_pushes_cp():
    world = World(local(2026, 10, 13, 12, 0), configured=WITH_CP)
    world.set(Inp.CP_RELAY, "unavailable")
    world.tick()
    assert world.engine.health.status == "ERROR"
    assert "cp" in world.notifications


def test_plug_in_offers_actionable_notification():
    world = World(local(2026, 10, 13, 18, 0))
    world.set(Inp.CABLE_CONNECTED, "off")
    world.tick()
    world.set(Inp.CABLE_CONNECTED, "on")
    result = world.tick()
    assert any(n.actionable for n in result.notifications)
    assert "PLUGGED_IN" in world.events


def test_evening_plug_reminder_once_per_day():
    world = World(local(2026, 10, 13, 20, 59, 50), plug_reminder_time="21:00:00")
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(30)
    world.run(30)
    assert world.notifications.count("plug_reminder") == 1


def test_target_soc_stops_charging_with_good_soc_only():
    world = World(local(2026, 10, 13, 4, 0), configured=WITH_OVMS)
    world.set(Inp.OVMS_SOC, "50")
    world.set(Inp.OVMS_CHARGING, "on")
    world.run(60)
    assert world.engine.executor.state is ExecState.CHARGING
    assert world.engine.desired.reason is Reason.SCHEDULE
    # An old SOC (sleeping car, no update) never switches off.
    world.set(Inp.OVMS_SOC, "91")
    world.updated[Inp.OVMS_SOC] = world.reported[Inp.OVMS_SOC] = world.now.replace(hour=2)
    world.run(150)
    assert CommandKind.DISABLE_CHARGER not in world.commands
    world.set(Inp.OVMS_SOC, "91")
    world.updated[Inp.OVMS_SOC] = world.reported[Inp.OVMS_SOC] = world.now
    world.run(30)
    assert world.engine.desired.reason is Reason.TARGET_SOC_REACHED
    assert CommandKind.DISABLE_CHARGER in world.commands
    assert CommandKind.CP_PULSE not in world.commands


def test_window_start_is_latched_while_soc_rises():
    world = World(local(2026, 10, 13, 4, 0), configured=WITH_OVMS)
    world.set(Inp.OVMS_SOC, "40")
    world.set(Inp.OVMS_CHARGING, "off")
    world.tick()
    start = world.engine.active_window.start if world.engine.active_window else None
    assert start is not None and start <= world.now
    world.set(Inp.OVMS_SOC, "85")
    world.tick()
    assert world.engine.active_window is not None
    assert world.engine.active_window.start == start


def test_one_shot_tonight_on_a_weekend():
    world = World(local(2026, 10, 17, 20, 0))  # Saturday – no weekday plan
    world.engine.start_one_shot(world.now)
    world.tick()
    assert world.engine.next_window.reason is Reason.ONE_SHOT
    world.now = local(2026, 10, 18, 3, 0)
    world.run(60)
    assert world.engine.desired.reason is Reason.ONE_SHOT
    world.now = local(2026, 10, 18, 5, 31)
    world.tick()
    assert world.engine.one_shot is None


def test_manual_cp_wakeup_respects_failsafe():
    world = World(local(2026, 10, 13, 12, 0), configured=WITH_CP, cp_pulse=True)
    world.tick()
    world.apply(world.engine.wakeup(world.now, CommandKind.CP_PULSE))
    assert CommandKind.CP_PULSE not in world.commands
    assert "WAKEUP_REJECTED" in world.events


def test_plans_round_trip_and_primary_update():
    world = World(local(2026, 10, 13, 12, 0))
    world.engine.update_primary_plan(world.now, departure_time="06:15")
    assert world.engine.plans[0].departure_time == time(6, 15)
    data = world.engine.as_dict()
    other = World(local(2026, 10, 13, 12, 0))
    other.engine.restore(data)
    assert other.engine.plans == world.engine.plans


def test_restart_during_session_resumes_it():
    world = World(local(2026, 10, 13, 12, 0))
    world.engine.set_override(world.now, OverrideMode.UNTIL_UNPLUGGED)
    world.run(60)
    saved = world.engine.as_dict()
    restarted = World(local(2026, 10, 13, 12, 1))
    restarted.states = dict(world.states)
    restarted.updated = dict(world.updated)
    restarted.reported = dict(world.reported)
    restarted.engine.restore(saved)
    restarted.run(30)
    assert restarted.engine.executor.state is ExecState.CHARGING
    assert restarted.engine.sessions.open is not None
    assert restarted.engine.sessions.open.session_id == world.engine.sessions.open.session_id


def test_disabled_plan_produces_no_window():
    world = World(local(2026, 10, 13, 3, 30))
    world.engine.set_plans(world.now, [WeeklySchedule(id="x", enabled=False)])
    world.tick()
    assert world.engine.next_window is None
    assert world.engine.desired.reason is Reason.DEFAULT_OFF


def test_data_conflict_is_flagged():
    world = World(local(2026, 10, 13, 12, 0), configured=WITH_OVMS)
    world.set(Inp.OVMS_CHARGING, "off")
    world.set(Inp.OVMS_SOC, "50")
    world.engine.set_override(world.now, OverrideMode.UNTIL_UNPLUGGED)
    world.run(30)
    assert world.engine.data_conflict
    assert "DATA_CONFLICT" in world.events


def climate_world(policy: str) -> World:
    """Tuesday 05:10, departure 05:30, target 90 % already reached, 10 °C outside → 10 min."""
    world = World(local(2026, 10, 13, 5, 10), configured=WITH_OVMS, ovms_port=True,
                  climate_enabled=True, ovms_enabled=True, climate_after_target_soc=policy,
                  ovms_climate_command="homelink {level}")
    world.set(Inp.OVMS_SOC, "92")
    world.set(Inp.OVMS_CHARGING, "off")
    world.set(Inp.OVMS_OUTSIDE_TEMP, "6")
    return world


def test_climate_allow_topup_enables_halo_and_starts_climate():
    world = climate_world("allow_topup")
    world.run(60)
    assert world.engine.desired.reason is Reason.TARGET_SOC_REACHED  # before the climate window
    world.now = local(2026, 10, 13, 5, 18, 30)  # 05:30 − 10 min − 2 min
    world.run(10)
    assert world.engine.desired.reason is Reason.CLIMATE
    assert world.engine.desired.charger_enabled is True
    assert CommandKind.CLIMATE_START in world.commands
    assert world.commands.count(CommandKind.CLIMATE_START) == 1


def test_climate_battery_only_keeps_halo_off():
    world = climate_world("battery_only")
    world.now = local(2026, 10, 13, 5, 18, 30)
    world.run(10)
    assert world.engine.desired.reason is Reason.TARGET_SOC_REACHED
    assert world.engine.desired.charger_enabled is False
    assert world.engine.desired.climate is not None
    assert CommandKind.CLIMATE_START in world.commands


def test_climate_blocked_without_soc():
    world = climate_world("allow_topup")
    world.set(Inp.OVMS_SOC, "20")
    world.now = local(2026, 10, 13, 5, 18, 30)
    world.run(10)
    assert world.engine.climate_blocked == "SOC_TOO_LOW"
    assert CommandKind.CLIMATE_START not in world.commands
