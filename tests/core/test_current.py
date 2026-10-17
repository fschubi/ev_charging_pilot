"""Charging current per plan, one-off departure and "Jetzt laden"."""

from datetime import datetime, time, timedelta

from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.model import Quality, Value
from custom_components.ev_charging_pilot.core.planner import (
    OneShot,
    VehicleParams,
    WeeklySchedule,
    current_kw,
    one_shot_window,
)
from custom_components.ev_charging_pilot.core.ports import CommandKind

from .world import HALO, TZ, World

WITH_CURRENT = HALO | {Inp.MAX_CURRENT}
TUESDAY_3AM = datetime(2026, 10, 13, 3, 0, tzinfo=TZ)


def fixed_plan(**extra) -> WeeklySchedule:
    return WeeklySchedule.from_dict({
        "id": "nacht", "weekdays": ["tue"], "mode": "fixed_start",
        "charge_start_time": "02:00", "departure_time": "06:00", **extra})


def test_plan_current_is_set_at_the_wallbox_once():
    world = World(TUESDAY_3AM, configured=WITH_CURRENT, current_settable=True)
    world.engine.plans = [fixed_plan(charge_current_a=10)]
    world.run(30)
    assert world.engine.desired.current_a == 10
    assert world.commands.count(CommandKind.SET_CURRENT) == 1
    assert world.states[Inp.MAX_CURRENT][0] == "10"
    assert "CURRENT_SET" in world.events


def test_standard_leaves_the_wallbox_alone():
    world = World(TUESDAY_3AM, configured=WITH_CURRENT, current_settable=True)
    world.engine.plans = [fixed_plan()]
    world.run(30)
    assert world.engine.desired.charger_enabled is True
    assert CommandKind.SET_CURRENT not in world.commands


def test_default_current_and_manual_current():
    world = World(TUESDAY_3AM, configured=WITH_CURRENT, current_settable=True,
                  default_current_a=16, manual_current_a=8)
    world.engine.plans = [fixed_plan()]
    world.run(10)
    assert world.engine.desired.current_a == 16
    world.apply(world.engine.charge_now(world.now))
    world.run(10)
    assert world.engine.desired.current_a == 8


def test_nothing_is_set_while_the_wallbox_stays_off_or_cannot_be_set():
    world = World(datetime(2026, 10, 13, 12, 0, tzinfo=TZ), configured=WITH_CURRENT,
                  current_settable=True, default_current_a=16)
    world.run(30)
    assert CommandKind.SET_CURRENT not in world.commands
    world = World(TUESDAY_3AM, configured=HALO, default_current_a=16)
    world.engine.plans = [fixed_plan(charge_current_a=10)]
    world.run(30)
    assert CommandKind.SET_CURRENT not in world.commands


def test_lower_current_plans_a_longer_charge():
    soc = Value("50", 50.0, "ovms", TUESDAY_3AM, Quality.GOOD)
    departure = TUESDAY_3AM + timedelta(hours=10)
    params = VehicleParams(vehicle_charger_kw=22)

    def duration(amps):
        shot = OneShot(departure_at=departure, charge_current_a=amps)
        return one_shot_window(shot, TUESDAY_3AM, TZ, soc, params).estimate.duration

    assert current_kw(12) == 8.28
    assert duration(6) > duration(12) > duration(16)


def test_plan_round_trip_keeps_the_current():
    plan = fixed_plan(charge_current_a="12")
    assert WeeklySchedule.from_dict(plan.as_dict()).charge_current_a == 12
    assert fixed_plan(charge_current_a="").charge_current_a is None
    assert fixed_plan(charge_current_a=99).charge_current_a is None
    assert fixed_plan().departure_time == time(6, 0)
