"""Engine: full ticks from raw states to commands, sessions and push intents."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta

import pytest

from custom_components.ev_charging_pilot.core.executor import ExecState
from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.model import Reason
from custom_components.ev_charging_pilot.core.planner import OverrideMode, WeeklySchedule
from custom_components.ev_charging_pilot.core.ports import CommandKind

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
    world.run(60)  # the session waits for late Halo counter readings
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
    # different polling delays: a short contradiction is no conflict yet
    assert not world.engine.data_conflict
    world.run(180)
    assert world.engine.data_conflict
    assert "DATA_CONFLICT" in world.events


def climate_world(policy: str, configured=WITH_OVMS) -> World:
    """Tuesday 05:10, departure 05:30, target 90 % already reached, 10 °C outside → 10 min."""
    world = World(local(2026, 10, 13, 5, 10), configured=configured, ovms_port=True,
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
    world.now = local(2026, 10, 13, 5, 22, 30)  # 05:30 + 2 min − 10 min
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(10)
    assert world.engine.desired.reason is Reason.CLIMATE
    assert world.engine.desired.charger_enabled is True
    assert CommandKind.CLIMATE_START in world.commands
    assert world.commands.count(CommandKind.CLIMATE_START) == 1


def test_climate_battery_only_keeps_halo_off():
    world = climate_world("battery_only")
    world.now = local(2026, 10, 13, 5, 22, 30)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(10)
    assert world.engine.desired.reason is Reason.TARGET_SOC_REACHED
    assert world.engine.desired.charger_enabled is False
    assert world.engine.desired.climate is not None
    assert CommandKind.CLIMATE_START in world.commands


def test_climate_blocked_without_soc():
    world = climate_world("allow_topup")
    world.set(Inp.OVMS_SOC, "20")
    world.now = local(2026, 10, 13, 5, 22, 30)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(10)
    assert world.engine.climate_blocked == "SOC_TOO_LOW"
    assert CommandKind.CLIMATE_START not in world.commands


def test_plug_in_push_buttons_expire_with_the_plug_in():
    world = World(local(2026, 10, 13, 12, 0))
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(10)
    world.set(Inp.CABLE_CONNECTED, "on")
    world.run(10)
    assert world.engine.plug_offer_valid(world.now)
    assert not world.engine.plug_offer_valid(world.now + timedelta(hours=13))
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(10)
    assert not world.engine.plug_offer_valid(world.now)  # unplugged since the push


def test_failed_start_push_offers_retry():
    world = World(local(2026, 10, 13, 4, 0))
    world.car_charges_when_enabled = False
    world.run(900)
    failed = [n for r in world.results for n in r.notifications if n.category == "start_failed"]
    assert failed and failed[0].actions == ("retry",)
    assert "Stecker" in failed[0].message
    world.car_charges_when_enabled = True
    world.engine.retry(world.now)
    world.run(300)
    assert world.engine.executor.state is ExecState.CHARGING


def test_one_off_departure_with_date_and_target():
    world = World(local(2026, 10, 13, 12, 0), configured=WITH_OVMS)
    friday = datetime(2026, 10, 16, 7, 0)  # naive = local time, as the panel sends it
    world.engine.start_one_shot(world.now, departure_at=friday, target_soc=100)
    shot = world.engine.one_shot
    assert shot.departure_at.astimezone(TZ).hour == 7
    assert shot.preferred_departure_soc_pct == 100
    assert shot.minimum_departure_soc_pct == 80
    with pytest.raises(ValueError):
        world.engine.start_one_shot(world.now, departure_at=datetime(2026, 11, 30, 7, 0))


def test_restart_before_the_ovms_plug_is_known_is_no_plug_in():
    from custom_components.ev_charging_pilot.core.inputs import Inp as I

    world = World(datetime(2026, 10, 17, 20, 49, tzinfo=TZ),
                  configured=WITH_OVMS | {I.OVMS_PLUG})
    # Halo locked: it reports no cable; the OVMS integration has not loaded yet.
    world.set(I.CABLE_CONNECTED, "off")
    world.run(10)
    world.set(I.OVMS_PLUG, "yes")
    world.run(10)
    assert world.engine.values[I.CABLE_CONNECTED].normalized is True
    assert "PLUGGED_IN" not in world.events
    assert "CABLE_CONNECTED" not in world.events


def test_one_off_departure_stops_at_its_own_target():
    world = World(local(2026, 10, 20, 12, 0), configured=WITH_OVMS)
    world.engine.plans = []
    world.set(Inp.OVMS_SOC, "50")
    world.tick()
    world.apply(world.engine.start_one_shot(world.now, departure_at=world.now + timedelta(hours=3),
                                            target_soc=70))
    world.tick()
    world.now = world.engine.next_window.start
    world.run(60)
    world.set(Inp.OVMS_SOC, "70")
    world.run(60)
    assert world.engine.desired.charger_enabled is False


CLIMATE_START_AT = (2026, 10, 13, 5, 22, 30)  # 05:30 + 2 min − 10 min


def hvac_world() -> World:
    world = climate_world("allow_topup", WITH_OVMS | {Inp.OVMS_HVAC})
    world.set(Inp.OVMS_HVAC, "off")
    world.set(Inp.OVMS_HV_CYCLES, "100")
    return world


def test_climate_command_waits_for_the_halo_release():
    world = climate_world("allow_topup")
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.tick()
    assert world.commands == [CommandKind.ENABLE_CHARGER]  # Halo first, no climate yet
    world.tick()
    assert world.commands.index(CommandKind.CLIMATE_START) > \
        world.commands.index(CommandKind.ENABLE_CHARGER)


def test_climate_is_skipped_when_the_halo_does_not_confirm():
    world = climate_world("allow_topup")
    original = world.apply

    def halo_refuses(result):
        original(result)
        world.set(Inp.CHARGER_ENABLE, "off")
    world.apply = halo_refuses
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(70)
    assert CommandKind.CLIMATE_START not in world.commands
    assert "CLIMATE_SKIPPED" in world.events
    assert "start_failed" in world.notifications
    assert world.engine.climate_phase == "skipped"
    world.run(10)
    assert world.engine.desired.reason is not Reason.CLIMATE


def test_climate_wish_ends_when_the_car_reports_hvac_off():
    world = hvac_world()
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(10)
    assert world.engine.climate_phase == "sent"
    world.set(Inp.OVMS_HVAC, "on")
    world.set(Inp.OVMS_HV_CYCLES, "99")  # the HV contactor closes for the climate
    world.run(60)
    assert world.engine.climate_phase == "running"
    assert world.engine.desired.reason is Reason.CLIMATE
    world.set(Inp.OVMS_HVAC, "off")
    world.run(10)
    assert "CLIMATE_ENDED" in world.events
    # 92 % ≥ 90 %: the target rules again and the Halo goes off before departure.
    assert world.engine.desired.reason is Reason.TARGET_SOC_REACHED
    assert world.engine.desired.charger_enabled is False
    assert "HV_CYCLE_WITHOUT_ACTIVITY" not in world.events
    assert world.commands.count(CommandKind.CLIMATE_START) == 1


def test_climate_start_is_frozen_once_reached():
    world = climate_world("allow_topup")
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(10)
    world.set(Inp.OVMS_OUTSIDE_TEMP, "-5")  # would mean 15 min – must not send again
    world.run(60)
    assert world.commands.count(CommandKind.CLIMATE_START) == 1
    assert world.engine.climate_plan.duration_min == 10


def test_climate_is_not_sent_twice_after_a_restart():
    world = climate_world("allow_topup")
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(10)
    stored = world.engine.as_dict()
    fresh = climate_world("allow_topup")
    fresh.now = world.now
    fresh.engine.restore(stored)
    fresh.set(Inp.CHARGER_ENABLE, "on")
    fresh.run(30)
    assert CommandKind.CLIMATE_START not in fresh.commands
    assert fresh.engine.climate_phase == "sent"


def test_short_shelly_dropout_is_tolerated_for_three_minutes():
    """Field 18.10.2026: the Shelly dropped off the WLAN for a minute, 30 times."""
    from custom_components.ev_charging_pilot.core.health import HealthStatus

    world = World(local(2026, 10, 13, 12, 0), configured=WITH_CP)
    world.run(30)
    assert world.engine.health.status is HealthStatus.HEALTHY
    world.set(Inp.CP_RELAY, "unavailable")
    world.run(170)
    assert world.engine.health.status is HealthStatus.HEALTHY
    world.run(20)
    assert world.engine.health.status is HealthStatus.ERROR
    assert "CP_STATE_UNKNOWN" in world.engine.health.reasons
    world.set(Inp.CP_RELAY, "on")
    world.run(10)
    assert world.engine.health.status is HealthStatus.HEALTHY


def test_no_dropout_grace_right_after_a_cp_pulse_or_an_open_cp():
    from datetime import timedelta

    from custom_components.ev_charging_pilot.core.health import HealthStatus

    world = World(local(2026, 10, 13, 12, 0), configured=WITH_CP)
    world.run(30)
    world.engine.executor.last_pulse_at = world.now - timedelta(minutes=2)
    world.set(Inp.CP_RELAY, "unavailable")
    world.tick()
    assert world.engine.health.status is HealthStatus.ERROR

    world = World(local(2026, 10, 13, 12, 0), configured=WITH_CP)
    world.set(Inp.CP_RELAY, "off")
    world.run(30)
    world.set(Inp.CP_RELAY, "unavailable")
    world.tick()
    assert "CP_STATE_UNKNOWN" in world.engine.health.reasons


def full_charge_world() -> World:
    """One-off departure in 3 h with target 100 %, charging at 60 %."""
    world = World(local(2026, 10, 20, 12, 0), configured=WITH_OVMS)
    world.engine.plans = []
    world.set(Inp.OVMS_SOC, "60")
    world.set(Inp.OVMS_CHARGING, "off")
    world.tick()
    world.apply(world.engine.start_one_shot(world.now, departure_at=world.now + timedelta(hours=3),
                                            target_soc=100))
    world.tick()
    world.now = world.engine.next_window.start
    world.run(60)
    world.set(Inp.OVMS_CHARGING, "on")
    world.run(60)
    assert world.engine.executor.state is ExecState.CHARGING
    return world


def test_target_100_lets_the_car_finish_and_balance():
    """Field 19.10.2026: the display read 100 % at a real ~93 % – the pilot cut too early."""
    world = full_charge_world()
    world.set(Inp.OVMS_SOC, "100")
    world.run(600)  # the car keeps balancing at 100 %
    assert world.engine.desired.charger_enabled is True
    assert world.engine.executor.state is ExecState.CHARGING
    # The car ends the charge itself.
    world.car_charges_when_enabled = False
    world.set(Inp.OVMS_CHARGING, "off")
    world.run(60)
    assert world.engine.executor.state is ExecState.CHARGE_ENDED
    assert world.engine.desired.charger_enabled is True  # not before three minutes
    world.run(150)
    assert world.engine.desired.charger_enabled is False
    assert world.engine.desired.reason is Reason.TARGET_SOC_REACHED
    world.run(30)
    assert world.states[Inp.CHARGER_ENABLE][0] == "off"
    assert "CHARGE_INTERRUPTED" not in world.events


def test_target_100_resumed_balancing_restarts_the_wait():
    world = full_charge_world()
    world.set(Inp.OVMS_SOC, "100")
    world.car_charges_when_enabled = False
    world.run(120)
    assert world.engine.executor.state is ExecState.CHARGE_ENDED
    world.car_charges_when_enabled = True  # balancing pulls power again
    world.run(120)
    assert world.engine.desired.charger_enabled is True
    world.car_charges_when_enabled = False
    world.run(150)
    assert world.engine.desired.charger_enabled is True
    world.run(60)
    assert world.engine.desired.charger_enabled is False


def test_target_below_100_still_stops_at_the_soc():
    world = full_charge_world()
    world.engine.one_shot = replace(world.engine.one_shot, preferred_departure_soc_pct=90)
    world.set(Inp.OVMS_SOC, "90")
    world.run(30)
    assert world.engine.desired.charger_enabled is False


def test_a_new_start_after_session_end_gets_a_new_session_id():
    """Field 19.10.2026: the climate session reused the night's session ID."""
    world = full_charge_world()
    world.engine.one_shot = replace(world.engine.one_shot, preferred_departure_soc_pct=90)
    first = world.engine.executor.session_id
    assert first
    world.set(Inp.OVMS_SOC, "90")
    world.run(30)
    assert "SESSION_END" in world.events
    assert world.engine.executor.session_id is None


def test_heating_from_the_grid_is_no_data_conflict():
    """Field 19.10.2026: DATA_CONFLICT while the full car heated from the wallbox."""
    world = hvac_world()
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, world.states[Inp.OVMS_SOC][0])  # keep the SOC fresh
    world.run(10)
    world.set(Inp.OVMS_HVAC, "on")
    world.set(Inp.OVMS_CHARGING, "off")
    world.run(200)  # longer than the conflict grace of 180 s
    assert world.engine.desired.reason is Reason.CLIMATE
    assert "DATA_CONFLICT" not in world.events
    assert not world.engine.data_conflict
