"""Charge test: the whole start chain once, on demand."""

from datetime import datetime

import pytest

from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.ports import CommandKind

from .world import TZ, WITH_OVMS, World

NOON = datetime(2026, 10, 13, 12, 0, tzinfo=TZ)


def world(**kwargs) -> World:
    w = World(NOON, configured=WITH_OVMS, **kwargs)
    w.set(Inp.OVMS_SOC, "70")
    w.tick()
    return w


def start(w: World) -> None:
    w.apply(w.engine.start_charge_test(w.now))


def test_car_that_charges_at_once_needs_no_wakeup():
    w = world()
    start(w)
    w.run(240)
    test = w.engine.charge_test
    assert test.phase == "done" and test.ok is True
    assert test.woke_by is None
    assert "ohne Wecken" in test.summary
    assert w.commands.count(CommandKind.ENABLE_CHARGER) == 1
    assert w.commands[-1] is CommandKind.DISABLE_CHARGER
    assert w.states[Inp.CHARGER_ENABLE][0] == "off"
    assert w.engine.override is None
    assert "CHARGE_TEST_RESULT" in w.events


def test_sleeping_car_is_woken_by_ovms():
    w = world(ovms_port=True, ovms_enabled=True)
    w.car_charges_when_enabled = False
    start(w)
    for _ in range(120):
        w.tick()
        if CommandKind.OVMS_WAKEUP in w.commands:
            w.car_charges_when_enabled = True
    test = w.engine.charge_test
    assert test.ok is True and test.woke_by == "OVMS"
    assert CommandKind.CP_PULSE not in w.commands
    assert any(step["text"] == "Auto per OVMS geweckt" for step in test.steps)


def test_car_that_never_charges_fails_and_locks_the_wallbox():
    w = world()
    w.car_charges_when_enabled = False
    start(w)
    w.run(600)
    test = w.engine.charge_test
    assert test.phase == "done" and test.ok is False
    assert w.states[Inp.CHARGER_ENABLE][0] == "off"
    assert w.engine.override is None


def test_refused_when_unplugged_or_in_dry_run():
    w = world()
    w.set(Inp.CABLE_CONNECTED, "off")
    w.tick()
    with pytest.raises(ValueError, match="nicht eingesteckt"):
        w.engine.start_charge_test(w.now)
    w = world()
    w.engine.set_shadow(True)
    with pytest.raises(ValueError, match="Live-Modus"):
        w.engine.start_charge_test(w.now)


def test_unplugging_aborts_the_test():
    w = world()
    start(w)
    w.run(20)
    w.set(Inp.CABLE_CONNECTED, "off")
    w.run(60)
    test = w.engine.charge_test
    assert test.ok is False and "Abgebrochen" in test.summary
