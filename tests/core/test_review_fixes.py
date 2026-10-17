"""Regression tests for the findings of the review of 2026-10-18 (docs/pruefbericht-2026-10-18.md).

Each scenario was reproduced with this simulation before the fix.
"""

from dataclasses import replace
from datetime import datetime, timedelta

from custom_components.ev_charging_pilot.core.engine import Engine
from custom_components.ev_charging_pilot.core.executor import ExecState
from custom_components.ev_charging_pilot.core.health import HealthStatus
from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.model import Quality
from custom_components.ev_charging_pilot.core.planner import DEFAULT_PLAN
from custom_components.ev_charging_pilot.core.ports import CommandKind

from .world import TZ, WITH_CP, WITH_OVMS, World

NIGHT = datetime(2026, 10, 20, 2, 55, tzinfo=TZ)


def _restart(world: World) -> None:
    data = world.engine.as_dict()
    world.engine = Engine(world.engine.config)
    world.engine.restore(data)
    world.commands.clear()
    world.events.clear()
    world.notifications.clear()


def _taper_end(world: World) -> None:
    """The car ends the charge itself: power sinks, then stops."""
    for watts in (1800, 1200, 700):
        world.charging_power = watts
        world.run(120)
    world.car_charges_when_enabled = False


class CpWorld(World):
    """The wallbox sees "no vehicle" while the CP line is open."""

    pulse_until = None

    def apply(self, result):
        super().apply(result)
        for command in result.commands:
            if command.kind is CommandKind.CP_PULSE:
                self.pulse_until = self.now + timedelta(seconds=command.params["seconds"])
                self.set(Inp.CP_RELAY, "off")
                self.set(Inp.CABLE_CONNECTED, "off")

    def tick(self, seconds=5):
        if self.pulse_until and self.now >= self.pulse_until:
            self.set(Inp.CP_RELAY, "on")
            self.set(Inp.CABLE_CONNECTED, "on")
            self.pulse_until = None
            self.car_charges_when_enabled = True
        return super().tick(seconds)


def test_k1_soc_is_not_stale_after_a_normal_charge():
    world = World(datetime(2026, 10, 20, 1, 0, tzinfo=TZ), configured=WITH_OVMS, ovms_port=True,
                  ovms_enabled=True, climate_enabled=True)
    world.engine.plans = [replace(DEFAULT_PLAN, climate="10")]
    soc, elapsed, awake = 70.0, 0, True
    world.charging_power = 4600.0
    world.set(Inp.OVMS_SOC, f"{soc:.1f}")
    world.set(Inp.OVMS_CHARGING, "off")
    for _ in range(int(4.6 * 3600 / 5)):
        elapsed += 5
        world.car_charges_when_enabled = awake
        world.tick(5)
        if float(world.states[Inp.CHARGE_POWER][0]) > 0:
            soc += 4600 * 5 / 3600 / 1000 * 0.88 / 16.7 * 100
            if elapsed % 60 == 0:  # OVMS publishes the SOC every minute while charging
                world.set(Inp.OVMS_SOC, f"{soc:.1f}")
                world.set(Inp.OVMS_CHARGING, "on")
        elif world.states[Inp.OVMS_CHARGING][0] == "on":
            world.set(Inp.OVMS_CHARGING, "off")
            awake = False
    assert world.engine.soc.quality is Quality.LAST_KNOWN_VALID
    assert world.engine.health.status is HealthStatus.HEALTHY
    assert world.engine.climate_blocked is None
    assert "HEALTH_DEGRADED" not in world.events


def test_k2_restart_after_the_car_finished_never_wakes_it():
    world = World(NIGHT, configured=WITH_CP, cp_pulse=True, cp_failsafe_verified=True)
    world.run(1800)
    _taper_end(world)
    world.run(600)
    assert world.engine.executor.state is ExecState.CHARGE_ENDED
    _restart(world)
    world.run(600)
    assert CommandKind.CP_PULSE not in world.commands
    assert CommandKind.OVMS_WAKEUP not in world.commands
    assert "CHARGE_START_FAILED" not in world.events


def test_k3_failed_start_switches_the_wallbox_off():
    world = World(NIGHT, configured=WITH_CP, cp_pulse=True, cp_failsafe_verified=True)
    world.car_charges_when_enabled = False
    world.run(900)
    assert world.engine.executor.state is ExecState.START_FAILED
    assert world.states[Inp.CHARGER_ENABLE][0] == "off"


def test_k4_climate_gets_no_second_wakeup_after_a_failed_night():
    world = World(NIGHT, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                  ovms_enabled=True, cp_failsafe_verified=True, climate_enabled=True)
    world.engine.plans = [replace(DEFAULT_PLAN, climate="10")]
    world.car_charges_when_enabled = False
    wakeups = 0
    for _ in range(int(2.6 * 3600 / 5)):
        world.set(Inp.OVMS_SOC, "60")
        world.tick(5)
        wakeups += sum(c.kind in (CommandKind.OVMS_WAKEUP, CommandKind.CP_PULSE)
                       for c in world.results[-1].commands)
    assert wakeups == 2  # one OVMS, one CP – once for the whole window
    assert world.engine.health.status is not HealthStatus.ERROR
    assert world.engine.executor.consecutive_start_failures == 1


def test_k5_restart_in_a_failed_window_is_no_second_failure():
    world = World(NIGHT, configured=WITH_CP, cp_pulse=True, cp_failsafe_verified=True)
    world.car_charges_when_enabled = False
    world.run(900)
    _restart(world)
    world.run(600)
    assert world.engine.executor.consecutive_start_failures == 1
    assert world.notifications.count("start_failed") == 0
    assert world.engine.health.status is not HealthStatus.ERROR


def test_k6_cp_pulse_does_not_end_charge_now():
    world = CpWorld(datetime(2026, 10, 20, 12, 0, tzinfo=TZ), configured=WITH_CP, cp_pulse=True,
                    cp_failsafe_verified=True)
    world.car_charges_when_enabled = False
    world.tick()
    world.apply(world.engine.charge_now(world.now))
    world.run(600)
    assert world.engine.override is not None
    assert world.engine.executor.state is ExecState.CHARGING


def test_k8_each_night_is_its_own_session():
    world = World(NIGHT, configured=WITH_CP, cp_pulse=True, cp_failsafe_verified=True)

    def night():
        world.car_charges_when_enabled = True
        world.charging_power = 2300
        world.run(3600)
        _taper_end(world)
        world.run(3 * 3600)

    night()
    world.run(20 * 3600, step=30)
    night()
    assert world.engine.sessions.open is None
    assert len(world.engine.monitor.data.sessions) == 2


def test_k10_stop_inside_the_switch_interval_gives_one_session():
    world = World(datetime(2026, 10, 20, 12, 0, tzinfo=TZ), configured=WITH_CP)
    world.tick()
    world.apply(world.engine.start_charge_test(world.now))
    world.run(400)
    assert world.engine.charge_test.ok is True
    assert world.events.count("SESSION_END") == 1
    assert "SESSION_RESUMED" not in world.events
    assert len(world.engine.monitor.data.sessions) == 1
