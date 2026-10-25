"""Regression tests for the findings of the review of 2026-10-24 (docs/pruefbericht-2026-10-24.md).

Each scenario was reproduced with this simulation before the fix.
"""

from datetime import datetime, time

from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.planner import WEEKDAYS, WeeklySchedule
from custom_components.ev_charging_pilot.core.ports import CommandKind

from .world import TZ, WITH_OVMS, World

EVENING = datetime(2026, 10, 20, 0, 0, tzinfo=TZ)
WAKEUPS = (CommandKind.OVMS_WAKEUP, CommandKind.CP_PULSE)


def _ovms_world(**options) -> World:
    world = World(EVENING, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                  ovms_enabled=True, cp_failsafe_verified=True, **options)
    world.set(Inp.OVMS_CHARGING, "off")
    return world


def _plan(world: World, target: int = 90) -> None:
    world.engine.set_plans(world.now, [WeeklySchedule(
        id="p", weekdays=frozenset(WEEKDAYS), departure_time=time(6, 0),
        ready_buffer_min=30, preferred_departure_soc_pct=target)])


def test_k2_sleeping_car_at_its_target_is_not_woken():
    """K2: SOC 92 % (last known, car asleep) at a 90 % target – the plan opened its
    window, nothing flowed, and the wakeup chain woke the full car every night."""
    world = _ovms_world()
    world.car_charges_when_enabled = False
    world.set(Inp.OVMS_SOC, "92.0")
    _plan(world)
    world.run(7 * 3600)
    assert not set(WAKEUPS) & set(world.commands)
    assert "CHARGE_START_FAILED" not in world.events
    assert world.states[Inp.CHARGER_ENABLE][0] == "off"


def test_k2_sleeping_car_below_its_target_is_still_woken():
    world = _ovms_world()
    world.car_charges_when_enabled = False
    world.set(Inp.OVMS_SOC, "60.0")
    _plan(world)
    world.run(7 * 3600)
    assert CommandKind.OVMS_WAKEUP in world.commands
