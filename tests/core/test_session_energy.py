"""Session energy with the lagging Halo cloud counter (field night 18.10.2026).

The Halo counter is polled about every 30 s: energy flowed before
CHARGE_STABLE and the last readings arrived after SESSION_END. The session
counted 3.31 kWh while the counter rose by 3.43 kWh.
"""

from datetime import date, datetime, timedelta

import pytest

from custom_components.ev_charging_pilot.core.costs import FixedPriceHistory, PricePoint
from custom_components.ev_charging_pilot.core.model import (
    Category,
    Event,
    Quality,
    Severity,
    Value,
)
from custom_components.ev_charging_pilot.core.sessions import TAIL_S, SessionTracker

from .world import TZ

T0 = datetime(2026, 10, 18, 6, 0, 3, tzinfo=TZ)
PRICES = FixedPriceHistory([PricePoint(date(2026, 1, 1), 0.38)], TZ)


def kwh(n):
    return Value(n, n, "halo", None, Quality.GOOD)


def ev(code, severity=Severity.INFO):
    return Event(T0, Category.CHARGING, severity, code, "")


def step(tracker, at, total, events=()):
    return tracker.update(
        T0 + timedelta(seconds=at), list(events), total_energy=kwh(total),
        power=Value(9000, 9000, "halo", None), vehicle_power=Value.unavailable("ovms"),
        soc=Value(80, 80, "ovms", None), reason="one_shot", prices=PRICES)


def night(tracker):
    assert step(tracker, 0, 1.12, [ev("CHARGER_ENABLE")]) == []
    assert step(tracker, 40, 1.17, [ev("CHARGE_STABLE")]) == []
    assert step(tracker, 1000, 4.48) == []
    # Target reached: the session ends, the counter is not final yet.
    assert step(tracker, 1416, 4.48, [ev("SESSION_END"), ev("CHARGER_DISABLE")]) == []
    assert tracker.closing
    assert step(tracker, 1417, 4.54) == []
    assert step(tracker, 1447, 4.55) == []


def test_session_takes_energy_before_stable_and_after_the_end():
    tracker = SessionTracker()
    night(tracker)
    closed = step(tracker, 1416 + TAIL_S, 4.55)
    assert len(closed) == 1
    session = closed[0]
    assert session.start_total_energy_kwh == 1.12
    assert session.end_total_energy_kwh == 4.55
    assert session.grid_energy_kwh == 3.43
    assert session.ended_at == T0 + timedelta(seconds=1416)
    assert abs(sum(i["kwh"] for i in session.energy_intervals) - 3.43) < 1e-6
    assert tracker.open is None and not tracker.closing


def test_closing_session_survives_a_restart():
    tracker = SessionTracker()
    night(tracker)
    restored = SessionTracker()
    restored.restore(tracker.as_dict())
    assert restored.closing
    closed = step(restored, 1416 + TAIL_S, 4.55)
    assert closed[0].grid_energy_kwh == 3.43


def test_new_start_hands_out_the_ending_session_first():
    tracker = SessionTracker()
    night(tracker)
    closed = step(tracker, 1450, 4.55, [ev("CHARGER_ENABLE")])
    assert len(closed) == 1 and closed[0].grid_energy_kwh == 3.43
    assert step(tracker, 1490, 4.60, [ev("CHARGE_STABLE")]) == []
    assert tracker.open.start_total_energy_kwh == 4.55


def test_baseline_is_dropped_when_the_wallbox_is_switched_off_again():
    tracker = SessionTracker()
    step(tracker, 0, 1.12, [ev("CHARGER_ENABLE")])
    step(tracker, 30, 1.12, [ev("CHARGER_DISABLE")])
    step(tracker, 600, 1.50)  # someone else used the Halo meanwhile
    step(tracker, 640, 1.60, [ev("CHARGE_RESUMED")])
    assert tracker.open.start_total_energy_kwh == 1.60


def test_session_keeps_a_power_curve_once_per_minute():
    tracker = SessionTracker()
    night(tracker)
    session = step(tracker, 1416 + TAIL_S, 4.55)[0]
    # Stable at 40 s, samples at 40 s and 1000 s (others < 60 s apart), plus the close.
    offsets = [p[0] for p in session.trace]
    assert offsets[:2] == [0, 960]
    assert session.trace[0][1:] == [9000, None, 80.0]
    assert all(b - a >= 60 for a, b in zip(offsets, offsets[1:], strict=False))
    restored = type(session).from_dict(session.as_dict())
    assert restored.trace == session.trace


def climate_tick(tracker, at, total, events=(), climate=True, battery_w=0.0):
    return tracker.update(
        T0 + timedelta(seconds=at), list(events), total_energy=kwh(total),
        power=Value(5000, 5000, "halo", None),  # Halo shows 3 × one phase
        vehicle_power=Value.unavailable("ovms"), soc=Value(100, 100, "ovms", None),
        reason="climate", prices=PRICES, climate=climate,
        battery_power=Value(battery_w, battery_w, "ovms", T0, Quality.GOOD), efficiency=0.88)


def test_climate_energy_comes_from_the_counter_not_the_power():
    """Field 19.10.2026: Halo power 5 kW, counter 13.27 → 13.37 kWh, battery full."""
    tracker = SessionTracker()
    climate_tick(tracker, 0, 13.27, [ev("CHARGER_ENABLE")])
    climate_tick(tracker, 30, 13.27, [ev("CHARGE_STABLE")])
    for at in range(35, 270, 5):  # counter polled every 30 s, rising 1.6 kW
        climate_tick(tracker, at, round(13.27 + (at // 30 * 30 - 30) * 1.6 / 3600, 2))
    # HVAC off; the last counter readings arrive a poll later.
    climate_tick(tracker, 270, 13.36, [ev("SESSION_END")], climate=False)
    climate_tick(tracker, 300, 13.37, climate=False)
    session = climate_tick(tracker, 270 + TAIL_S, 13.37, climate=False)[0]
    assert session.grid_energy_kwh == pytest.approx(0.10)
    assert session.climate_energy_kwh == pytest.approx(0.10, abs=0.005)
    assert session.climate_cost_eur == pytest.approx(session.climate_energy_kwh * 0.38)


def test_battery_charging_is_not_counted_as_climate():
    """Field 18.10.2026: heating while charging at 89 %: Halo 8.8 kW, battery 5.4 kW."""
    tracker = SessionTracker()
    climate_tick(tracker, 0, 4.55, [ev("CHARGER_ENABLE")], battery_w=5400)
    climate_tick(tracker, 5, 4.55, [ev("CHARGE_STABLE")], battery_w=5400)
    for at in range(10, 310, 5):
        climate_tick(tracker, at, 4.55 + (at - 5) * 8.8 / 3600, battery_w=5400)
    climate_tick(tracker, 310, 4.55 + 305 * 8.8 / 3600, [ev("SESSION_END")], climate=False)
    session = climate_tick(tracker, 310 + TAIL_S, 4.55 + 305 * 8.8 / 3600, climate=False)[0]
    heating = (8.8 - 5.4 / 0.88) * 300 / 3600
    assert session.climate_energy_kwh == pytest.approx(heating, abs=0.015)  # + 5 s tail


def test_no_climate_share_without_climate():
    tracker = SessionTracker()
    night(tracker)
    session = step(tracker, 1416 + TAIL_S, 4.55)[0]
    assert session.climate_energy_kwh is None and session.climate_cost_eur is None


def test_session_takes_the_ovms_energy_of_this_charge():
    tracker = SessionTracker()

    def tick(at, total, ovms_kwh, events=()):
        return tracker.update(
            T0 + timedelta(seconds=at), list(events), total_energy=kwh(total),
            power=Value(9000, 9000, "halo", None), vehicle_power=Value.unavailable("ovms"),
            soc=Value(80, 80, "ovms", None), reason="schedule", prices=PRICES,
            charge_energy=Value(ovms_kwh, ovms_kwh, "ovms", T0, Quality.GOOD))

    tick(0, 4.55, 7.68, [ev("CHARGER_ENABLE")])
    tick(40, 4.60, 0.0, [ev("CHARGE_STABLE")])  # OVMS restarts its counter
    tick(1800, 13.10, 7.30)
    tick(1810, 13.54, 7.68, [ev("SESSION_END")])
    session = tick(1810 + TAIL_S, 13.54, 7.68)[0]
    assert session.grid_energy_kwh == pytest.approx(8.99)
    assert session.vehicle_charge_energy_kwh == 7.68
    assert session.vehicle_energy_source == "ovms_charge_energy"
