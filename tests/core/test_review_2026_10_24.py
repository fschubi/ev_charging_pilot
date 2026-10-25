"""Regression tests for the findings of the review of 2026-10-24 (docs/pruefbericht-2026-10-24.md).

Each scenario was reproduced with this simulation before the fix.
"""

from dataclasses import replace
from datetime import datetime, time

from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.planner import (
    WEEKDAYS,
    ScheduleMode,
    WeeklySchedule,
)
from custom_components.ev_charging_pilot.core.ports import CommandKind

from .world import HALO, TZ, WITH_OVMS, World

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
    """Charges whenever the wallbox offers power and reports its SOC over OVMS
    (or ``fake_soc`` instead, to fake an outlier)."""

    fake_soc = None

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
            self.set(Inp.OVMS_SOC, f"{self.fake_soc or self.soc:.2f}")
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


def _fixed_night_plan(world: World) -> None:
    world.engine.set_plans(world.now, [WeeklySchedule(
        id="p", weekdays=frozenset(WEEKDAYS), mode=ScheduleMode.FIXED_START,
        charge_start_time=time(3, 0), departure_time=time(5, 30), ready_buffer_min=0)])


def test_h3_repeated_start_failures_lock_only_until_the_next_window():
    """H3: after two failed nights health stayed ERROR forever – nothing reset the counter
    without a charge, so the third night (car accepting power) was never even tried."""
    world = World(datetime(2026, 10, 20, 2, 55, tzinfo=TZ), configured=HALO)
    _fixed_night_plan(world)
    world.car_charges_when_enabled = False
    world.run(2 * 86400, step=10)
    assert world.engine.health.reasons == ("REPEATED_START_FAILURE",)
    world.car_charges_when_enabled = True
    world.run(86400, step=10)
    assert "START_FAILURES_RELEASED" in world.events
    assert "CHARGE_STABLE" in world.events


def test_h3_unplugging_clears_the_start_failures():
    world = World(datetime(2026, 10, 20, 2, 55, tzinfo=TZ), configured=HALO)
    _fixed_night_plan(world)
    world.car_charges_when_enabled = False
    world.run(2 * 86400, step=10)
    assert world.engine.executor.consecutive_start_failures == 2
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(60)
    assert world.engine.executor.consecutive_start_failures == 0
    assert world.engine.health.status.value != "ERROR"


class DryRunWorld(World):
    """Like the coordinator: in the dry run commands are only logged, never applied."""

    def apply(self, result):
        if self.engine.shadow:
            result = replace(result, commands=[])
        super().apply(result)


def test_h4_switching_to_live_mid_window_starts_without_dry_run_leftovers():
    """H4: in the dry run no power ever flows, so the window ended in START_FAILED –
    after switching to live in the same window nothing was switched, 0 kWh."""
    world = DryRunWorld(datetime(2026, 10, 20, 2, 55, tzinfo=TZ), configured=HALO)
    _fixed_night_plan(world)
    world.engine.set_shadow(True)
    world.car_charges_when_enabled = False
    world.run(3600)
    assert world.engine.executor.failure_code == "CHARGE_START_FAILED"
    world.engine.set_shadow(False)
    world.car_charges_when_enabled = True
    world.commands.clear()
    world.run(1800)
    assert CommandKind.ENABLE_CHARGER in world.commands
    assert "CHARGE_STABLE" in world.events


def test_h4_live_wakeup_budget_survives_a_dry_run_detour():
    """The other way round: live attempts are not wiped by a short dry run."""
    world = _ovms_world()
    world.car_charges_when_enabled = False
    world.set(Inp.OVMS_SOC, "60.0")
    _plan(world)
    world.run(6 * 3600)
    executor = world.engine.executor
    spent = {key: (a.ovms, a.cp) for key, a in executor._attempts.items()}
    assert spent
    world.engine.set_shadow(True)
    world.engine.set_shadow(False)
    assert {key: (a.ovms, a.cp) for key, a in executor._attempts.items()} == spent


class FrozenHaloCar(FillingCar):
    """The Halo cloud stops reporting while the car keeps charging and says so."""

    halo_frozen = False

    def set(self, key, state, **attributes):
        if self.halo_frozen and key in (Inp.CHARGE_POWER, Inp.TOTAL_ENERGY):
            return
        super().set(key, state, **attributes)


def test_h5_frozen_halo_power_does_not_wake_a_charging_car():
    """H5: the Halo reported nothing for 30 min while OVMS said "charging" (GOOD) –
    the executor saw a pause, woke the car and its CP pulse cut the running charge."""
    start = datetime(2026, 10, 20, 2, 55, tzinfo=TZ)
    world = FrozenHaloCar(start, soc=50.0, configured=WITH_OVMS, cp_pulse=True,
                          ovms_port=True, ovms_enabled=True, cp_failsafe_verified=True)
    world.charging_power = 4600.0
    _fixed_night_plan(world)
    world.run(30 * 60)
    assert "CHARGE_STABLE" in world.events
    world.halo_frozen = True
    world.run(40 * 60)
    assert "CHARGE_PAUSED" not in world.events
    assert not set(WAKEUPS) & set(world.commands)


def test_m2_normalized_value_carries_its_own_unit():
    """Diagnosis showed "9139.369999999999 kW": watts with the source's kW label."""
    from custom_components.ev_charging_pilot.core.inputs import RawState, to_value

    at = datetime(2026, 10, 24, 23, 0, tzinfo=TZ)
    power = to_value(Inp.OVMS_BATTERY_POWER,
                     RawState("9.13937", at, at, {"unit_of_measurement": "kW"}))
    assert (round(power.normalized, 2), power.unit) == (9139.37, "W")
    energy = to_value(Inp.TOTAL_ENERGY, RawState("41220", at, at, {"unit_of_measurement": "Wh"}))
    assert (energy.normalized, energy.unit) == (41.22, "kWh")


def test_m7_infinite_readings_are_invalid_and_never_crash_the_tick():
    """"inf" (or "1e308 kW", infinite in W) passed as GOOD – round() in the session
    trace then raised on every tick and its commands were lost."""
    from custom_components.ev_charging_pilot.core.inputs import RawState, to_value
    from custom_components.ev_charging_pilot.core.model import Quality

    at = datetime(2026, 10, 24, 23, 0, tzinfo=TZ)
    for state, unit in (("inf", "W"), ("nan", "W"), ("1e308", "kW"), ("-inf", "W")):
        value = to_value(Inp.CHARGE_POWER, RawState(state, at, at, {"unit_of_measurement": unit}))
        assert value.quality is Quality.INVALID and value.normalized is None
    world = FillingCar(datetime(2026, 10, 20, 2, 55, tzinfo=TZ), soc=50.0,
                       configured=WITH_OVMS)
    _fixed_night_plan(world)
    world.run(15 * 60)
    world.states[Inp.CHARGE_POWER] = ("inf", {"unit_of_measurement": "W"})
    world.engine.tick(world.now, world.raw())
    world.set(Inp.OVMS_BATTERY_POWER, "1e308", unit_of_measurement="kW")
    world.engine.tick(world.now, world.raw())


def _charging_night(soc=60.0):
    world = FillingCar(datetime(2026, 10, 20, 0, 25, tzinfo=TZ), soc=soc,
                       configured=WITH_OVMS, ovms_port=True, ovms_enabled=True)
    world.charging_power = 4600.0
    world.engine.set_plans(world.now, [WeeklySchedule(
        id="p", weekdays=frozenset(WEEKDAYS), mode=ScheduleMode.FIXED_START,
        charge_start_time=time(0, 30), departure_time=time(5, 30), ready_buffer_min=0,
        preferred_departure_soc_pct=90)])
    world.run(15 * 60)
    assert "CHARGE_STABLE" in world.events
    return world


def test_m3_single_soc_outlier_does_not_end_the_charge():
    """OVMS reported 95 % for a minute at a real 65 % – the charge was switched off."""
    world = _charging_night()
    world.fake_soc = 95.0
    world.run(60)
    world.fake_soc = None
    world.run(60)
    assert CommandKind.DISABLE_CHARGER not in world.commands


def test_m3_top_up_after_the_target_runs_to_the_target():
    """Once restarted below target − 3 %, the top-up stopped at 87 instead of 90 %."""
    world = _charging_night()
    world.run(3 * 3600)
    assert world.states[Inp.CHARGER_ENABLE][0] == "off" and world.soc >= 90
    world.soc = 85.0
    world.set(Inp.OVMS_SOC, "85.00")
    world.run(60 * 60)
    assert world.soc >= 90


def test_m4_enforce_target_frees_the_wallbox_for_the_climate():
    """enforce_target behaved like battery_only: the target hold kept the Halo off and
    the car heated from its battery (§9.1: the Halo is free, only exceeding stops)."""
    from .test_engine import CLIMATE_START_AT, climate_world, local

    world = climate_world("enforce_target")
    world.set(Inp.OVMS_SOC, "90")
    world.run(60)
    assert world.engine.desired.charger_enabled is False  # target held before the climate
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, "90")
    world.set(Inp.OVMS_OUTSIDE_TEMP, "6")
    world.run(30)
    assert world.engine.desired.charger_enabled is True
    world.set(Inp.OVMS_SOC, "91")  # target + margin exceeded
    world.run(30)
    assert world.engine.desired.charger_enabled is False


def test_m5_paused_charge_keeps_its_wallbox_across_a_restart():
    """A restart during a pause after the window switched the Halo off although the
    pilot had promised "free until unplugged"."""
    from custom_components.ev_charging_pilot.core.engine import Engine

    start = datetime(2026, 10, 20, 2, 55, tzinfo=TZ)
    world = SleepyCar(start, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                      ovms_enabled=True, cp_failsafe_verified=True)
    world.engine.set_plans(start, [WeeklySchedule(
        id="p", weekdays=frozenset(WEEKDAYS), mode=ScheduleMode.FIXED_START,
        charge_start_time=time(3, 0), departure_time=time(5, 30), ready_buffer_min=0)])
    world.refuse_after = datetime(2026, 10, 20, 5, 20, tzinfo=TZ)
    world.run(3 * 3600)
    assert "PAUSE_HOLD" in world.events and world.states[Inp.CHARGER_ENABLE][0] == "on"
    data = world.engine.as_dict()
    world.engine = Engine(world.engine.config)
    world.engine.restore(data)
    world.commands.clear()
    world.run(30 * 60)
    assert world.states[Inp.CHARGER_ENABLE][0] == "on"
    assert not {CommandKind.DISABLE_CHARGER, *WAKEUPS} & set(world.commands)


class NappingCar(SleepyCar):
    """Falls asleep as soon as the wallbox is off (gap between two price blocks)."""

    def tick(self, seconds=5):
        if self.states[Inp.CHARGER_ENABLE][0] == "off":
            self.awake = False
        return super().tick(seconds)


def test_m6_second_price_block_without_wakeups_left_is_no_failed_start():
    """Two blocks share one window and its wakeups (rule 3): the car slept again in the
    gap, the second block ended as "Ladestart fehlgeschlagen" and counted as a failure."""
    from datetime import timedelta

    from custom_components.ev_charging_pilot.core.prices import PriceSlot

    start = datetime(2026, 10, 19, 21, 0, tzinfo=TZ)
    world = NappingCar(start, configured=WITH_OVMS, cp_pulse=True, ovms_port=True,
                       ovms_enabled=True, cp_failsafe_verified=True, price_source="tibber",
                       price_optimization=True, price_blocks=2)
    cheap = {23: 0.10, 3: 0.11}
    world.engine.set_prices([PriceSlot(
        start + timedelta(hours=h), start + timedelta(hours=h + 1),
        cheap.get((start + timedelta(hours=h)).hour, 0.40)) for h in range(12)])
    world.engine.set_plans(start, [WeeklySchedule(
        id="p", weekdays=frozenset(WEEKDAYS), departure_time=time(6, 0), ready_buffer_min=30,
        preferred_departure_soc_pct=80)])
    world.tick()
    assert len(world.engine.next_window.blocks) == 2
    world.run(9 * 3600)
    assert world.events.count("CHARGE_STABLE") == 1
    assert "BLOCK_NOT_STARTED" in world.events
    assert "CHARGE_START_FAILED" not in world.events
    assert world.engine.executor.consecutive_start_failures == 0
    assert world.commands.count(CommandKind.OVMS_WAKEUP) == 1
    assert world.commands.count(CommandKind.CP_PULSE) == 1
