"""Whole nights with a realistic car: it falls asleep, it gets full, nothing is switched.

The simple world lets the car resume charging whenever the wallbox allows it.
These scenarios add what a real smart 453 does and guard the transitions
around the target SOC, the end of charge and the dry run.
"""

from datetime import datetime

from custom_components.ev_charging_pilot.core.executor import ExecState
from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.ports import CommandKind

from .world import HALO, TZ, WITH_CP, WITH_OVMS, World

TUESDAY_0255 = datetime(2026, 10, 20, 2, 55, tzinfo=TZ)
WAKEUPS = (CommandKind.OVMS_WAKEUP, CommandKind.CP_PULSE)


class SleepyCar(World):
    """Charges while enabled, reports SOC via OVMS and falls asleep after a charge."""

    def __init__(self, *args, soc: float = 85.0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.soc = soc
        self.awake = True
        self.set(Inp.OVMS_SOC, f"{soc:.1f}")
        self.set(Inp.OVMS_CHARGING, "off")

    def tick(self, seconds: float = 5):
        self.car_charges_when_enabled = self.awake and self.soc < 100
        result = super().tick(seconds)
        if float(self.states[Inp.CHARGE_POWER][0]) > 0:
            self.soc += self.charging_power * seconds / 3600 / 1000 * 0.88 / 16.7 * 100
            self.set(Inp.OVMS_SOC, f"{self.soc:.1f}")
            self.set(Inp.OVMS_CHARGING, "on")
        elif self.states[Inp.OVMS_CHARGING][0] == "on":
            self.set(Inp.OVMS_CHARGING, "off")
            self.awake = False  # no more updates – the SOC ages from now on
        return result


def test_target_reached_is_held_without_wakeup_until_departure():
    world = SleepyCar(TUESDAY_0255, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                      ovms_enabled=True, cp_failsafe_verified=True)
    world.run(3 * 3600)
    assert world.commands.count(CommandKind.ENABLE_CHARGER) == 1
    assert not any(c in world.commands for c in WAKEUPS)
    assert "start_failed" not in world.notifications
    assert world.soc < 92


def test_fresh_soc_far_below_target_tops_up_once_without_wakeup():
    world = SleepyCar(TUESDAY_0255, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                      ovms_enabled=True, cp_failsafe_verified=True)
    while world.engine.desired is None or world.engine.desired.reason != "target_soc_reached":
        world.tick(5)
    world.run(900)  # the car is asleep now, the SOC ages
    assert world.engine.desired.reason == "target_soc_reached"
    # the car reports a clearly lower SOC (e.g. climate used energy) while it sleeps
    world.soc = 84.0
    world.set(Inp.OVMS_SOC, "84.0")
    world.run(600)
    assert world.commands.count(CommandKind.ENABLE_CHARGER) == 2
    assert "TOPUP_SKIPPED" in world.events
    assert not any(c in world.commands for c in WAKEUPS)
    assert "start_failed" not in world.notifications


def test_tapering_charge_ends_as_finished_without_wakeup():
    world = World(TUESDAY_0255, configured=WITH_CP, cp_pulse=True, cp_failsafe_verified=True)
    world.run(3600)
    for watts in (1800, 1200, 700):  # the battery is nearly full
        world.charging_power = watts
        world.run(120)
    world.car_charges_when_enabled = False
    world.run(600)
    assert world.engine.executor.state is ExecState.CHARGE_ENDED
    assert CommandKind.CP_PULSE not in world.commands
    assert "start_failed" not in world.notifications


def test_abrupt_loss_without_signal_pauses_wakes_once_and_keeps_the_wallbox():
    """Since v0.24.0 a lost power is a pause: 15 min wait, one wakeup, then the
    wallbox stays on until unplugged – with exactly one push."""
    world = World(TUESDAY_0255, configured=WITH_CP, cp_pulse=True, cp_failsafe_verified=True)
    world.run(3600)
    world.car_charges_when_enabled = False
    world.run(1800)
    assert "CHARGE_PAUSED" in world.events and "PAUSE_HOLD" in world.events
    assert world.notifications.count("start_failed") == 1
    assert world.states[Inp.CHARGER_ENABLE][0] == "on"


def test_full_battery_ends_the_charge():
    world = SleepyCar(TUESDAY_0255, configured=WITH_OVMS, soc=97.0,
                      preferred_departure_soc_pct=100)
    world.engine.set_plans(world.now, [])
    world.engine.charge_now(world.now)
    world.run(3600)
    assert world.engine.executor.state is ExecState.CHARGE_ENDED
    assert "start_failed" not in world.notifications


class DryRun(World):
    """Dry run: commands are only logged, the hardware never changes."""

    def apply(self, result):
        self.results.append(result)
        self.events += [e.code for e in result.events]
        self.notifications += [n.category for n in result.notifications]


def test_dry_run_night_has_no_false_alarm():
    world = DryRun(TUESDAY_0255, configured=HALO)
    world.engine.set_shadow(True)
    world.run(3 * 3600)
    assert "CHARGER_ENABLE" in world.events
    assert "CHARGER_NOT_CONFIRMED" not in world.events
    assert world.notifications == []
    assert world.engine.monitor.data.sessions == []
    assert world.engine.executor.consecutive_start_failures == 0


def test_normal_start_is_not_reported_as_resumed():
    world = World(TUESDAY_0255, configured=HALO)
    world.run(600)
    assert "CHARGE_STABLE" in world.events
    assert "SESSION_RESUMED" not in world.events
