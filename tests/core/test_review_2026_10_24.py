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


def test_m9_vehicle_consumption_only_over_trips_with_energy():
    """40 km with 6 kWh plus 60 km reconstructed without energy gave 6 instead of 15."""
    from datetime import date

    from custom_components.ev_charging_pilot.core.costs import FixedPriceHistory, PricePoint
    from custom_components.ev_charging_pilot.core.statistics import MonitorData, period_summary
    from custom_components.ev_charging_pilot.core.trips import Trip

    def trip(trip_id, km, kwh, day):
        at = datetime(2026, 10, day, 9, 0, tzinfo=TZ)
        return Trip(trip_id=trip_id, started_at=at, ended_at=at.replace(hour=10),
                    odometer_start_km=1000.0 + day * 100, odometer_end_km=1000.0 + day * 100 + km,
                    distance_km=km, duration_min=60, average_speed_kmh=km,
                    vehicle_energy_used_kwh=kwh, recovered_energy_kwh=0.0 if kwh else None,
                    auxiliary_energy_kwh=None, consumption_kwh_100km=None,
                    outside_temp_avg_c=10.0, season="autumn", soc_start_pct=None, soc_end_pct=None)

    data = MonitorData([], [trip("a", 40.0, 6.0, 5), trip("b", 60.0, None, 6)], [], [], [], set())
    month = period_summary(data, datetime(2026, 10, 1, tzinfo=TZ), datetime(2026, 11, 1, tzinfo=TZ),
                           prices=FixedPriceHistory([PricePoint(date(2026, 1, 1), 0.3)], TZ),
                           capacity_kwh=16.7, efficiency=0.88, odometer_source="ovms")
    assert month["vehicle_consumption_kwh_100km"] == 15.0


def test_m9_learned_energy_per_percent_leaves_the_climate_out():
    from custom_components.ev_charging_pilot.core.learning import learn
    from custom_components.ev_charging_pilot.core.sessions import ChargeSession

    sessions = [ChargeSession(session_id=f"s{i}", reason="schedule", source="home_halo",
                              started_at=datetime(2026, 10, 10 + i, 2, 0, tzinfo=TZ),
                              start_soc_pct=40, end_soc_pct=90, grid_energy_kwh=10.6,
                              climate_energy_kwh=1.6, success=True) for i in range(3)]
    learned = learn(sessions, nominal_kwh_per_pct=0.19, max_power_kw=11)
    assert learned.grid_kwh_per_pct == 0.18


def test_m9_external_energy_detected_late_counts_the_whole_charge():
    from custom_components.ev_charging_pilot.core.external import _charge_battery_kwh

    assert _charge_battery_kwh((1.2, 1.2, 4.35)) == 4.35   # counting before detection
    assert _charge_battery_kwh((8.34, 0.0, 4.35)) == 4.35  # dropped: new charge
    assert _charge_battery_kwh((8.34, 8.34, 8.34)) is None  # the previous charge's value


def test_m9_climate_without_battery_power_is_not_all_climate():
    """Without a GOOD battery power the whole counter rise of a charging session was
    booked as climate (2.32 of 4.52 kWh)."""
    from datetime import timedelta

    from custom_components.ev_charging_pilot.core.costs import FixedPriceHistory, PricePoint
    from custom_components.ev_charging_pilot.core.model import (
        Category,
        Event,
        Quality,
        Severity,
        Value,
    )
    from custom_components.ev_charging_pilot.core.sessions import TAIL_S, SessionTracker

    t0 = datetime(2026, 10, 20, 5, 0, tzinfo=TZ)
    prices = FixedPriceHistory([PricePoint(t0.date(), 0.30)], TZ)
    tracker = SessionTracker()

    def tick(at, total, events=(), climate=False):
        def ev(code):
            return Event(t0, Category.CHARGING, Severity.INFO, code, "")
        return tracker.update(
            t0 + timedelta(seconds=at), [ev(c) for c in events],
            total_energy=Value(total, total, "halo", None, Quality.GOOD),
            power=Value(4600, 4600, "halo", None), vehicle_power=Value.unavailable("ovms"),
            soc=Value(80, 80, "ovms", None), reason="schedule", prices=prices,
            climate=climate, battery_power=Value.unavailable("ovms"))

    tick(0, 100.0, ["CHARGER_ENABLE"])
    tick(5, 100.0, ["CHARGE_STABLE"])
    for at in range(10, 3600, 10):
        tick(at, round(100.0 + at * 4.6 / 3600, 4), climate=1800 <= at < 3600)
    tick(3600, 104.6, ["SESSION_END"])
    session = tick(3600 + TAIL_S, 104.6)[0]
    assert not session.climate_energy_kwh


def test_low_charge_ended_says_full_only_with_a_full_soc():
    """CHARGE_ENDED also comes from a falling power: "der Akku ist voll" at 80 % was wrong."""
    from custom_components.ev_charging_pilot.core.executor import ExecState
    from custom_components.ev_charging_pilot.core.summary import summary

    world = FillingCar(datetime(2026, 10, 20, 2, 55, tzinfo=TZ), soc=80.0, configured=WITH_OVMS)
    world.tick()
    world.engine.executor.state = ExecState.CHARGE_ENDED
    assert summary(world.engine, world.now, True)["detail"] == \
        "Das Auto hat bei 80 % selbst aufgehört."
    world.set(Inp.OVMS_SOC, "100")
    world.tick()
    world.engine.executor.state = ExecState.CHARGE_ENDED
    assert "der Akku ist voll" in summary(world.engine, world.now, True)["detail"]


def test_low_external_charge_without_any_price_marks_the_month_estimated():
    from datetime import date

    from custom_components.ev_charging_pilot.core.costs import FixedPriceHistory, PricePoint
    from custom_components.ev_charging_pilot.core.statistics import (
        ExternalCharge,
        MonitorData,
        Reading,
        period_summary,
    )

    edges = (datetime(2026, 10, 1, tzinfo=TZ), datetime(2026, 11, 1, tzinfo=TZ))
    readings = [Reading(edges[0], 9000.0), Reading(edges[1], 9500.0)]
    socs = [Reading(edges[0], 60.0), Reading(edges[1], 60.0)]
    priced = MonitorData([], [], [ExternalCharge("e", date(2026, 10, 2), "public", 7.0,
                                                 price_eur_kwh=0.49)], readings, socs, set())
    data = MonitorData([], [], [ExternalCharge("e", date(2026, 10, 2), "public", 7.0)],
                       readings, socs, set())
    assert period_summary(priced, *edges, prices=FixedPriceHistory(
        [PricePoint(date(2026, 1, 1), 0.3)], TZ), capacity_kwh=16.7, efficiency=0.88,
        odometer_source="manual")["quality"] == "GOOD"
    month = period_summary(data, datetime(2026, 10, 1, tzinfo=TZ), datetime(2026, 11, 1, tzinfo=TZ),
                           prices=FixedPriceHistory([PricePoint(date(2026, 1, 1), 0.3)], TZ),
                           capacity_kwh=16.7, efficiency=0.88, odometer_source="manual")
    assert month["quality"] == "ESTIMATED"


def test_low_halo_refusing_to_switch_off_is_not_retried_for_ever():
    """Unplugged with the Halo stuck on: an off command every 120 s, endlessly."""
    from datetime import timedelta

    world = World(datetime(2026, 10, 20, 12, 0, tzinfo=TZ), configured=HALO)
    world.engine.set_plans(world.now, [])
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(60)
    world.set(Inp.CHARGER_ENABLE, "on")
    offs = 0
    for _ in range(int(3600 / 5)):
        result = world.engine.tick(world.now, world.raw())
        world.now += timedelta(seconds=5)
        offs += sum(c.kind is CommandKind.DISABLE_CHARGER for c in result.commands)
        world.events += [e.code for e in result.events]
        world.notifications += [n.category for n in result.notifications]
    # A few tries per half hour instead of one every 120 s (30 per hour before).
    assert offs <= 2 * (world.engine.executor.config.max_confirm_attempts + 1)
    assert "CHARGER_OFF_REFUSED" in world.events
    assert "CHARGER_NOT_CONFIRMED" not in world.events


def test_low_average_power_counts_from_the_enable_and_stays_below_the_peak():
    """Field 24.10.2026: "Leistung Ø / max 10,6 / 10,4 kW"."""
    world = FillingCar(datetime(2026, 10, 20, 2, 55, tzinfo=TZ), soc=50.0, configured=WITH_OVMS)
    world.charging_power = 4600.0
    _fixed_night_plan(world)
    world.run(3 * 3600)
    session = next(s for r in world.results for s in r.sessions)
    assert session.average_power_w <= session.max_power_w


def test_low_energy_intervals_always_divide_the_hour():
    """45 min intervals overlapped: 00:00–00:45, 00:45–01:30, then 01:00–01:45."""
    from custom_components.ev_charging_pilot.core.settings import Settings

    assert Settings.from_options({"interval_min": 45}).interval_min in (30, 60)
    assert Settings.from_options({"interval_min": 15}).interval_min == 15
    assert 60 % Settings.from_options({"interval_min": 25}).interval_min == 0


def test_low_mixed_hourly_and_quarter_hour_prices_keep_their_length():
    """Tibber without end times, hourly then 15 min: the shortest step cut every hour
    to 15 min, coverage failed and price optimisation was off for the whole day."""
    from datetime import timedelta

    from custom_components.ev_charging_pilot.core.prices import _close

    start = datetime(2026, 10, 26, 0, 0, tzinfo=TZ)
    hourly = [(start + timedelta(hours=h), None, 0.30) for h in range(3)]
    quarter = [(start + timedelta(hours=3, minutes=15 * q), None, 0.25) for q in range(4)]
    slots = _close(hourly + quarter)
    assert [s.end - s.start for s in slots[:3]] == [timedelta(hours=1)] * 3
    assert slots[-1].end - slots[-1].start == timedelta(minutes=15)


def test_low_replay_ticks_through_the_extra_hour_of_the_dst_change():
    """24.10. 23:00 → 25.10. 05:00 is 7 real hours; local wall-clock steps made it 6."""
    from custom_components.ev_charging_pilot.core.inputs import RawState
    from custom_components.ev_charging_pilot.core.replay import ReplayDataset, run_replay

    start = datetime(2026, 10, 24, 23, 0, tzinfo=TZ)
    end = datetime(2026, 10, 25, 5, 0, tzinfo=TZ)
    cable = [RawState("on", start, start, {})]
    result = run_replay(ReplayDataset("dst", "Europe/Berlin", start, end,
                                      {Inp.CABLE_CONNECTED: cable}), tick_s=60)
    assert result.ticks == 7 * 60 + 1


def test_low_gap_in_the_speed_curve_is_no_hard_braking():
    from custom_components.ev_charging_pilot.core.trips import driving_style

    steady = [[i * 15, 70.0, -8000.0, 80] for i in range(30)]
    after_gap = [[30 * 15 + 120 + i * 15, 0.0 if i == 0 else 70.0, -8000.0, 80]
                 for i in range(30)]
    style = driving_style(steady + after_gap)
    assert style["anticipating"] == 100


def test_low_imperial_units_are_converted():
    from custom_components.ev_charging_pilot.core.inputs import RawState, to_value

    at = datetime(2026, 10, 24, 12, 0, tzinfo=TZ)

    def value(key, state, unit):
        return to_value(key, RawState(state, at, at, {"unit_of_measurement": unit}))

    assert round(value(Inp.OVMS_RANGE, "50", "mi").normalized, 1) == 80.5
    assert round(value(Inp.OVMS_SPEED, "60", "mph").normalized, 1) == 96.6
    assert value(Inp.OVMS_OUTSIDE_TEMP, "50", "°F").normalized == 10.0
    assert value(Inp.TOTAL_ENERGY, "0.04122", "MWh").normalized == 41.22


def test_low_climate_belongs_to_the_month_the_session_ended_in():
    """A night across the month change heats on the 1st: its climate went to the old
    month while the energy went to the new one (driving energy could turn negative)."""
    from datetime import date

    from custom_components.ev_charging_pilot.core.costs import FixedPriceHistory, PricePoint
    from custom_components.ev_charging_pilot.core.sessions import ChargeSession
    from custom_components.ev_charging_pilot.core.statistics import MonitorData, period_summary

    night = ChargeSession(session_id="s", reason="schedule",
                          started_at=datetime(2026, 10, 31, 23, 0, tzinfo=TZ),
                          ended_at=datetime(2026, 11, 1, 5, 30, tzinfo=TZ),
                          grid_energy_kwh=5.0, climate_energy_kwh=0.5, success=True)
    data = MonitorData([night], [], [], [], [], set())
    prices = FixedPriceHistory([PricePoint(date(2026, 1, 1), 0.3)], TZ)

    def month(m):
        return period_summary(data, datetime(2026, m, 1, tzinfo=TZ),
                              datetime(2026, m + 1, 1, tzinfo=TZ), prices=prices,
                              capacity_kwh=16.7, efficiency=0.88, odometer_source="manual")

    assert month(10)["climate_energy_kwh"] is None
    assert month(11)["climate_energy_kwh"] == 0.5


def test_low_stored_sessions_get_their_average_power_capped():
    """Sessions stored before v0.27.24 kept "Ø 10,6 / max 10,4 kW" in the panel."""
    from custom_components.ev_charging_pilot.core.monitor import Monitor
    from custom_components.ev_charging_pilot.core.sessions import ChargeSession

    old = ChargeSession(session_id="s", reason="override",
                        started_at=datetime(2026, 10, 24, 13, 35, tzinfo=TZ), grid_energy_kwh=4.4,
                        max_power_w=10400.0, average_power_w=10560.0)
    monitor = Monitor(TZ)
    monitor.restore({"sessions": [old.as_dict()]})
    assert monitor.data.sessions[0].average_power_w == 10400.0
