"""The cockpit sentence: what happens now and next, in plain words."""

from datetime import datetime

from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.summary import summary

from .test_scenarios import TUESDAY_0255, SleepyCar
from .world import HALO, TZ, WITH_OVMS, World


def text(world, live=True):
    s = summary(world.engine, world.now, live)
    return f"{s['headline']} | {s['detail']}"


def test_upcoming_departure_based_charge():
    world = SleepyCar(datetime(2026, 10, 19, 21, 0, tzinfo=TZ), configured=WITH_OVMS, soc=50)
    world.run(30)
    line = text(world)
    assert line.startswith("Lädt Di ") and "auf 90 %" in line
    assert "Abfahrt Di 05:30" in line


def test_without_soc_it_explains_the_fixed_start():
    world = World(datetime(2026, 10, 19, 21, 0, tzinfo=TZ), configured=HALO)
    world.run(30)
    assert "Lädt ab Di 03:00" in text(world)
    assert "kein aktueller Ladestand" in text(world)


def test_charging_target_held_and_unplugged():
    world = SleepyCar(TUESDAY_0255, configured=WITH_OVMS)
    while world.engine.executor.state is None or world.engine.executor.state.value != "CHARGING":
        world.tick(5)
    assert text(world).startswith("Lädt mit 2,3 kW | Ziel 90 %")
    while not world.engine.target_held:
        world.tick(5)
    world.run(900)
    assert text(world).startswith("Ziel 90 % erreicht")
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(10)
    assert text(world) == ("Nicht eingesteckt | Nächste Abfahrt 05:30 („Werktage“) – "
                           "bitte jetzt einstecken.")


def test_failure_and_dry_run_wording():
    world = World(TUESDAY_0255.replace(hour=3), configured=HALO)
    world.car_charges_when_enabled = False
    world.run(900)
    assert text(world).startswith("Ladestart fehlgeschlagen | Bitte prüfen: Stecker")
    assert "Probebetrieb" in text(world, live=False)


def test_weekly_summary_line():
    from custom_components.ev_charging_pilot.core.summary import weekly_text

    from .test_learning import session

    world = World(datetime(2026, 10, 7, 12, 0, tzinfo=TZ))
    for n in range(3):
        s = session(n)
        s.cost_eur = 2.5
        world.engine.monitor.add_session(s)
    week = world.engine.monitor.week(world.now)
    assert week["charges"] == 3 and week["km"] is None
    line = weekly_text(week)
    assert line.startswith("25,2 kWh zuhause für 7,50 € · 3 Ladungen · 0× geweckt")
