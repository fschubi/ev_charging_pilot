"""Regression tests for the findings of the review of 2026-10-18 (docs/pruefbericht-2026-10-18.md).

Each scenario was reproduced with this simulation before the fix.
"""

from dataclasses import replace
from datetime import date, datetime, timedelta

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


def test_k9_interruption_far_below_target_is_no_end_of_charge():
    world = World(NIGHT, configured=WITH_OVMS)
    world.set(Inp.OVMS_SOC, "50")
    world.set(Inp.OVMS_CHARGING, "on")
    world.run(1800)
    assert world.engine.executor.state is ExecState.CHARGING
    # Wallbox fault: power gone, the car (awake) reports "not charging" at 55 %.
    world.car_charges_when_enabled = False
    world.set(Inp.OVMS_SOC, "55")
    world.set(Inp.OVMS_CHARGING, "off")
    world.run(400)
    assert "CHARGE_INTERRUPTED" in world.events
    assert "CHARGE_ENDED" not in world.events


def test_k9_new_request_after_end_of_charge_is_served():
    world = World(NIGHT, configured=WITH_CP, cp_pulse=True, cp_failsafe_verified=True)
    world.run(1800)
    _taper_end(world)
    world.run(600)
    assert world.engine.executor.state is ExecState.CHARGE_ENDED
    world.car_charges_when_enabled = True
    world.charging_power = 2300
    world.apply(world.engine.charge_now(world.now))
    world.run(300)
    assert world.engine.executor.state is ExecState.CHARGING


def test_k11_automation_off_override_end_switches_the_wallbox_off():
    world = World(datetime(2026, 10, 20, 12, 0, tzinfo=TZ), configured=WITH_OVMS,
                  manual_target_soc=60)
    world.engine.automation_enabled = False
    world.set(Inp.OVMS_SOC, "50")
    world.tick()
    world.apply(world.engine.charge_now(world.now))
    world.run(300)
    assert world.states[Inp.CHARGER_ENABLE][0] == "on"
    world.set(Inp.OVMS_SOC, "60")
    world.run(400)
    assert world.engine.override is None
    assert world.states[Inp.CHARGER_ENABLE][0] == "off"
    world.set(Inp.CHARGER_ENABLE, "on")  # switched on by hand later: hands off again
    world.run(300)
    assert world.states[Inp.CHARGER_ENABLE][0] == "on"


def test_k12_learning_uses_the_real_interval_length():
    from custom_components.ev_charging_pilot.core.learning import _session_power_kw
    from custom_components.ev_charging_pilot.core.sessions import ChargeSession

    start = datetime(2026, 10, 20, 2, 0, tzinfo=TZ)
    intervals = [{"start": (start + timedelta(minutes=5 * i)).isoformat(),
                  "end": (start + timedelta(minutes=5 * (i + 1))).isoformat(),
                  "kwh": 7.2 * 5 / 60} for i in range(12)]
    session = ChargeSession("s", start, reason="schedule", energy_intervals=intervals)
    assert abs(_session_power_kw(session) - 7.2) < 0.01


def test_k13_sleeping_car_temperature_is_used_as_last_resort():
    from custom_components.ev_charging_pilot.core.model import Value
    from custom_components.ev_charging_pilot.core.source_policy import outside_temperature

    car = Value("4", 4.0, "ovms", NIGHT, Quality.LAST_KNOWN_VALID)
    none = Value.unavailable("none")
    assert outside_temperature(car, none, none) is car


def _quarter_prices(start, values):
    from custom_components.ev_charging_pilot.core.prices import PriceSchedule, PriceSlot

    return PriceSchedule(PriceSlot(start + timedelta(minutes=15 * i),
                                   start + timedelta(minutes=15 * (i + 1)), p)
                         for i, p in enumerate(values))


def test_p1_two_blocks_find_the_optimum_fast():
    import time as clock

    from custom_components.ev_charging_pilot.core.prices import cheapest_blocks

    start = datetime(2026, 10, 20, 18, 0, tzinfo=TZ)
    # Cheap 20:00–21:30 and 04:30–06:00, everything else expensive; ready at 06:30.
    values = [0.10 if (8 <= i < 14) or (42 <= i < 48) else 0.40 for i in range(50)]
    schedule = _quarter_prices(start, values)
    began = clock.perf_counter()
    blocks, cost = cheapest_blocks(schedule, start, start + timedelta(hours=12, minutes=30),
                                   timedelta(hours=3), 4.6, max_blocks=2)
    assert clock.perf_counter() - began < 0.2
    assert blocks == [(start + timedelta(hours=2), start + timedelta(hours=3, minutes=30)),
                      (start + timedelta(hours=10, minutes=30), start + timedelta(hours=12))]
    assert abs(cost - 3 * 4.6 * 0.10) < 1e-6


def test_p2_cheap_and_negative_cent_prices_stay_cents():
    from custom_components.ev_charging_pilot.core.prices import parse_price_attributes

    day = date(2026, 10, 20)
    attrs = {"raw_today": [{"start": f"2026-10-20T{h:02d}:00:00+02:00", "value": v}
                           for h, v in enumerate([12.0, 8.5, 4.5, 3.2, -1.5, 10.0])]}
    prices = [s.eur_per_kwh for s in parse_price_attributes(attrs, TZ, day)]
    assert prices == [0.12, 0.085, 0.045, 0.032, -0.015, 0.1]
    epex = {"data": [{"start_time": "2026-10-20T00:00:00+02:00", "price_ct_per_kwh": 4.0}]}
    assert parse_price_attributes(epex, TZ, day)[0].eur_per_kwh == 0.04


def test_p3_a_hole_in_the_price_list_stays_a_hole():
    from custom_components.ev_charging_pilot.core.prices import parse_price_attributes

    attrs = {"prices": [{"start": "2026-10-20T10:00:00+02:00", "price": 0.2},
                        {"start": "2026-10-20T11:00:00+02:00", "price": 0.2},
                        {"start": "2026-10-21T10:00:00+02:00", "price": 0.3}]}
    slots = parse_price_attributes(attrs, TZ, date(2026, 10, 20))
    assert all((s.end - s.start) == timedelta(hours=1) for s in slots)


def test_p5_hourly_prices_replace_old_quarter_hours():
    from custom_components.ev_charging_pilot.core.prices import PriceSlot

    world = World(NIGHT, configured=WITH_OVMS)
    start = datetime(2026, 10, 20, 10, 0, tzinfo=TZ)
    world.engine.set_prices(_quarter_prices(start, [0.5] * 4).slots)
    world.engine.set_prices([PriceSlot(start, start + timedelta(hours=1), 0.2)])
    assert world.engine.price_schedule.price_at(start + timedelta(minutes=20)) == 0.2
    assert len(world.engine.price_schedule.slots) == 1
