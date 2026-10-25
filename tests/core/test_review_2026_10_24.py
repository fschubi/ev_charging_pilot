"""Regression tests for the findings of the review of 2026-10-24 (docs/pruefbericht-2026-10-24.md).

Each scenario was reproduced with this simulation before the fix.
"""

from datetime import datetime, time

from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.planner import (
    WEEKDAYS,
    ScheduleMode,
    WeeklySchedule,
)
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


class SleepyCar(World):
    """Sleeps until a CP pulse, then charges and reports a rising SOC over OVMS;
    from ``refuse_after`` on it stops taking power (pause below the target)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.awake = False
        self.refuse_after = None
        self.soc = 50.0
        self.set(Inp.OVMS_SOC, "50.0")
        self.set(Inp.OVMS_CHARGING, "off")

    def tick(self, seconds=5):
        self.car_charges_when_enabled = self.awake and not (
            self.refuse_after and self.now >= self.refuse_after)
        result = super().tick(seconds)
        if any(c.kind is CommandKind.CP_PULSE for c in result.commands):
            self.awake = True
        if float(self.states[Inp.CHARGE_POWER][0]) > 0:
            self.soc += 0.01
            self.set(Inp.OVMS_CHARGING, "on")
        elif self.states[Inp.OVMS_CHARGING][0] == "on":
            self.set(Inp.OVMS_CHARGING, "off")
        if self.awake:
            self.set(Inp.OVMS_SOC, f"{self.soc:.2f}")
        return result


def test_h1_paused_charge_after_the_window_gets_no_second_wakeup_budget():
    """H1: holding a paused charge past the window changed its key – the pause recovery
    then woke the car a second time over OVMS and CP in the same night (rule 3)."""
    start = datetime(2026, 10, 20, 2, 55, tzinfo=TZ)
    world = SleepyCar(start, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                      ovms_enabled=True, cp_failsafe_verified=True)
    world.engine.set_plans(start, [WeeklySchedule(
        id="p", weekdays=frozenset(WEEKDAYS), mode=ScheduleMode.FIXED_START,
        charge_start_time=time(3, 0), departure_time=time(5, 30), ready_buffer_min=0)])
    world.refuse_after = datetime(2026, 10, 20, 5, 20, tzinfo=TZ)
    world.run(4 * 3600)
    assert "CHARGE_PAUSED" in world.events and "PAUSE_HOLD" in world.events
    assert world.commands.count(CommandKind.OVMS_WAKEUP) == 1
    assert world.commands.count(CommandKind.CP_PULSE) == 1


class FillingCar(World):
    """Charges whenever the wallbox offers power and reports its SOC over OVMS."""

    def __init__(self, *args, soc=80.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.soc = soc
        self.set(Inp.OVMS_SOC, f"{soc:.0f}")
        self.set(Inp.OVMS_CHARGING, "off")

    def tick(self, seconds=5):
        self.car_charges_when_enabled = self.soc < 100
        result = super().tick(seconds)
        if float(self.states[Inp.CHARGE_POWER][0]) > 0:
            self.soc += self.charging_power * seconds / 3600 / 1000 * 0.88 / 16.7 * 100
            self.set(Inp.OVMS_SOC, f"{self.soc:.2f}")
            self.set(Inp.OVMS_CHARGING, "on")
        return result


def test_h2_unreachable_shelly_still_stops_at_the_target():
    """H2: the Shelly dropped out of the WLAN for 3 h – health ERROR froze every switch,
    the car charged to 100 % instead of 90 % and the Halo stayed on after the departure.
    §8.2: a Shelly outage only locks the CP wakeup."""
    start = datetime(2026, 10, 20, 2, 55, tzinfo=TZ)
    world = FillingCar(start, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                       ovms_enabled=True, cp_failsafe_verified=True)
    world.engine.set_plans(start, [WeeklySchedule(
        id="p", weekdays=frozenset(WEEKDAYS), mode=ScheduleMode.FIXED_START,
        charge_start_time=time(3, 0), departure_time=time(5, 30), ready_buffer_min=0,
        preferred_departure_soc_pct=90)])
    world.run(15 * 60)
    assert world.states[Inp.CHARGER_ENABLE][0] == "on"
    for _ in range(int(3 * 3600 / 5)):
        world.set(Inp.CP_RELAY, "unavailable")
        world.tick(5)
    health = world.engine.health
    assert health.status.value == "ERROR" and health.reasons == ("CP_STATE_UNKNOWN",)
    assert world.soc < 92
    assert world.states[Inp.CHARGER_ENABLE][0] == "off"
    assert CommandKind.CP_PULSE not in world.commands
