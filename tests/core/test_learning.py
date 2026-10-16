"""Learning the real charging behaviour and the slower charging near full."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.ev_charging_pilot.core.learning import learn
from custom_components.ev_charging_pilot.core.planner import (
    VehicleParams,
    charge_duration,
    soc_after,
)
from custom_components.ev_charging_pilot.core.sessions import ChargeSession

NOMINAL = VehicleParams()
T0 = datetime(2026, 10, 1, 2, 0, tzinfo=UTC)


def session(n, *, kw=4.1, start=40.0, end=80.0, kwh_per_pct=0.21, success=True):
    started = T0 + timedelta(days=n)
    energy = (end - start) * kwh_per_pct
    quarters = max(3, round(energy / kw / 0.25))
    intervals = [{"start": (started + timedelta(minutes=15 * i)).isoformat(),
                  "end": (started + timedelta(minutes=15 * (i + 1))).isoformat(),
                  "kwh": kw * 0.25} for i in range(quarters)]
    return ChargeSession(session_id=f"s{n}", started_at=started, reason="schedule",
                         ended_at=started + timedelta(hours=3), start_soc_pct=start,
                         end_soc_pct=end, grid_energy_kwh=energy, success=success,
                         energy_intervals=intervals)


def test_needs_three_sessions():
    learned = learn([session(1), session(2)], nominal_kwh_per_pct=NOMINAL.kwh_per_pct,
                    nominal_power_kw=NOMINAL.expected_power_kw)
    assert not learned.active


def test_learns_power_and_energy_per_percent_and_ignores_outliers():
    sessions = [session(n) for n in range(5)] + [
        session(9, kwh_per_pct=0.9),        # wrong SOC jump – implausible
        session(10, success=False),         # failed start
    ]
    learned = learn(sessions, nominal_kwh_per_pct=NOMINAL.kwh_per_pct,
                    nominal_power_kw=NOMINAL.expected_power_kw)
    assert learned.active
    assert learned.grid_kwh_per_pct == pytest.approx(0.21)
    assert learned.power_kw == pytest.approx(4.1)


def test_learned_values_change_the_duration():
    learned = VehicleParams(learned_kwh_per_pct=0.21, learned_power_kw=4.1)
    assert charge_duration(40, 80, learned)[1] > charge_duration(40, 80, NOMINAL)[1]


def test_charging_above_90_percent_is_slower_and_consistent():
    _, to_90 = charge_duration(80, 90, NOMINAL)
    _, to_100 = charge_duration(90, 100, NOMINAL)
    assert to_100 > to_90 * 1.5
    hours = charge_duration(70, 100, NOMINAL)[1].total_seconds() / 3600
    assert soc_after(70, hours, NOMINAL) == pytest.approx(100, abs=0.1)
