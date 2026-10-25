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
    assert line.startswith("25,2 kWh zu Hause für 7,50 € · 3 Ladungen · 0× geweckt")


def test_target_reached_in_price_block_stays_reached_after_the_block():
    """Field 18.10.2026: at 08:29 the cockpit still said "Lädt in der günstigsten
    Zeit 06:00–06:36" although the car had reached 90 % at 06:23."""
    from datetime import timedelta

    from .test_prices_external_report import local, night_prices

    world = World(local(2026, 10, 13, 22, 0), configured=WITH_OVMS, price_source="tibber")
    world.engine.set_prices(night_prices().slots)
    world.set(Inp.OVMS_SOC, "70")
    world.set(Inp.OVMS_CHARGING, "off")
    world.tick()
    start, end = world.engine.next_window.blocks[-1]
    world.now = start
    world.run(60)
    world.set(Inp.OVMS_CHARGING, "on")
    world.run(60)
    world.set(Inp.OVMS_SOC, "90")
    world.run(60)
    world.set(Inp.OVMS_CHARGING, "off")
    world.now = end + timedelta(minutes=30)
    world.run(60)
    assert world.engine.desired.charger_enabled is False
    assert text(world) == "Ziel 90 % erreicht | Das Auto ruht bis zur Abfahrt 05:30."


def test_soc_correction_after_the_block_plans_nothing_more():
    """Field 18.10.2026: the display SOC fell from 90 to 88 % at rest – the cockpit
    then claimed "Lädt 06:00–15:54" although nothing would switch on any more."""
    from datetime import timedelta

    from .test_prices_external_report import local, night_prices

    world = World(local(2026, 10, 13, 22, 0), configured=WITH_OVMS, price_source="tibber")
    world.engine.set_prices(night_prices().slots)
    world.set(Inp.OVMS_SOC, "70")
    world.set(Inp.OVMS_CHARGING, "off")
    world.tick()
    start, end = world.engine.next_window.blocks[-1]
    world.now = start
    world.run(60)
    world.set(Inp.OVMS_SOC, "90")
    world.run(60)
    world.now = end + timedelta(minutes=30)
    world.set(Inp.OVMS_SOC, "88")
    world.run(60)
    assert world.engine.desired.charger_enabled is False
    line = text(world)
    assert line == "Kein Laden mehr geplant – 88 % | Ladeblock vorbei, Abfahrt 05:30."


def test_climate_ahead_and_running_are_named():
    from .test_engine import CLIMATE_START_AT, climate_world, local

    world = climate_world("allow_topup")
    world.run(60)
    assert text(world).startswith("Vorklimatisierung um 05:25 für 10 min | Abfahrt 05:30 · ")
    assert "Strom aus der Wallbox. Ziel 90 % erreicht." in text(world)
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, "92")
    world.set(Inp.OVMS_OUTSIDE_TEMP, "6")
    world.run(30)
    assert text(world).startswith("Vorklimatisierung läuft | Bis spätestens 05:35")


def test_charging_away_is_shown_and_raises_no_false_warnings():
    """Field 21.10.2026: charging at a supermarket – nothing in the cockpit, but a
    DATA_CONFLICT and an HV warning."""
    world = World(datetime(2026, 10, 21, 16, 0, tzinfo=TZ), configured=WITH_OVMS)
    world.set(Inp.CABLE_CONNECTED, "off")
    world.set(Inp.OVMS_SOC, "66")
    world.set(Inp.OVMS_HV_CYCLES, "100")
    world.run(30)
    world.set(Inp.OVMS_CHARGING, "on")
    world.set(Inp.OVMS_HV_CYCLES, "99")  # the contactor closes for the public charger
    for minute in range(6):
        world.set(Inp.OVMS_CHARGE_POWER, str(15000 - minute * 500), unit_of_measurement="W")
        world.set(Inp.OVMS_SOC, str(66 + minute))
        world.run(60)
    line = text(world)
    assert line.startswith("Lädt unterwegs mit 12,5 kW | seit 16:00"), line
    assert "66 → 71 %" in line
    assert "DATA_CONFLICT" not in world.events
    assert "HV_CYCLE_WITHOUT_ACTIVITY" not in world.events


def test_climate_running_unplugged_is_named_with_the_battery():
    """Review 24.10.2026: unplugged, the cockpit said "Nicht eingesteckt" while the
    pre-climatisation ran from the battery."""
    from .test_engine import CLIMATE_START_AT, climate_world, local

    world = climate_world("allow_topup")
    world.run(60)
    world.now = local(*CLIMATE_START_AT)
    world.set(Inp.OVMS_SOC, "92")
    world.set(Inp.OVMS_OUTSIDE_TEMP, "6")
    world.run(30)
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(30)
    line = text(world)
    assert line.startswith("Vorklimatisierung läuft | Bis spätestens 05:35")
    assert "Strom aus dem Akku" in line
