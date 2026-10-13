"""Replay of a recorded night reproduces the real decisions (Gate v0.1)."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.smart_eq_charging.core.inputs import Inp, RawState
from custom_components.smart_eq_charging.core.replay import ReplayDataset, run_replay

from .world import TZ


def local(*args):
    return datetime(*args, tzinfo=TZ)


def recorded_night() -> ReplayDataset:
    """Phase-0 automation switched the Halo on at 03:00 and off at 06:00."""
    t0 = local(2026, 10, 13, 2, 50)
    on, off = local(2026, 10, 13, 3, 0, 20), local(2026, 10, 13, 6, 0)

    def st(state, at, unit=None):
        attrs = {"unit_of_measurement": unit} if unit else {}
        return RawState(state, at, at, attrs)

    power = [st("0", t0, "W")]
    energy = [st("1000.0", t0, "kWh")]
    t = on + timedelta(seconds=30)
    kwh = 1000.0
    while t < off:
        kwh += 2.3 * 60 / 3600
        power.append(st("2300", t, "W"))
        energy.append(st(f"{kwh:.3f}", t, "kWh"))
        t += timedelta(seconds=60)
    power.append(st("0", off, "W"))
    return ReplayDataset(
        name="night",
        timezone="Europe/Berlin",
        start=t0,
        end=local(2026, 10, 13, 6, 10),
        inputs={
            Inp.CHARGER_ENABLE: [st("off", t0), st("on", on), st("off", off)],
            Inp.CABLE_CONNECTED: [st("on", t0)],
            Inp.CHARGE_POWER: power,
            Inp.TOTAL_ENERGY: energy,
        },
        plans=[{"id": "p", "weekdays": ["tue"], "mode": "fixed_start",
                "charge_start_time": "03:00", "departure_time": "06:00"}],
    )


def test_replay_matches_reality_and_round_trips():
    dataset = ReplayDataset.from_dict(recorded_night().as_dict())
    result = run_replay(dataset, tick_s=10)
    assert result.ticks > 1000
    assert [c["kind"] for c in result.commands][:1] == ["enable_charger"]
    assert result.agreement == 1.0
    assert len(result.matches) == 2
    assert any(s["state"] == "CHARGING" for s in result.states)
    assert result.as_dict()["agreement"] == 1.0


def test_replay_detects_disagreement():
    dataset = recorded_night()
    dataset.plans = [{"id": "p", "weekdays": ["tue"], "mode": "fixed_start",
                      "charge_start_time": "04:30", "departure_time": "06:00"}]
    result = run_replay(dataset, tick_s=10)
    assert result.agreement < 1.0
    assert result.mismatches
