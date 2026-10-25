"""Dynamic prices, cheapest blocks, external charge detection, PDF reports."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from custom_components.ev_charging_pilot.core.executor import ExecState
from custom_components.ev_charging_pilot.core.external import ExternalChargeDetector
from custom_components.ev_charging_pilot.core.inputs import Inp
from custom_components.ev_charging_pilot.core.model import Quality, Value
from custom_components.ev_charging_pilot.core.monitor import Monitor
from custom_components.ev_charging_pilot.core.pdf import PdfDocument, text_width
from custom_components.ev_charging_pilot.core.prices import (
    PriceSchedule,
    PriceSlot,
    cheapest_blocks,
    parse_price_attributes,
    parse_tibber_response,
)
from custom_components.ev_charging_pilot.core.report import month_report, year_report
from custom_components.ev_charging_pilot.core.sessions import ChargeSession
from custom_components.ev_charging_pilot.core.settings import Settings
from custom_components.ev_charging_pilot.core.statistics import ExternalCharge

from .world import TZ, WITH_OVMS, World


def local(*args):
    return datetime(*args, tzinfo=TZ)


def night_prices(day=13) -> PriceSchedule:
    """Hourly prices 18:00–08:00, cheapest 02:00–04:00."""
    cheap = {2: 0.18, 3: 0.17}
    slots = []
    start = local(2026, 10, day, 18)
    for h in range(14):
        t = start + timedelta(hours=h)
        slots.append(PriceSlot(t, t + timedelta(hours=1), cheap.get(t.hour, 0.32)))
    return PriceSchedule(slots)


# ---------------------------------------------------------------- parsing

def test_parse_tibber_response():
    response = {"prices": {"Zuhause": [
        {"start_time": "2026-10-14T00:00:00+02:00", "price": 0.25},
        {"start_time": "2026-10-14T01:00:00+02:00", "price": 0.21},
    ]}}
    slots = parse_tibber_response(response, TZ)
    assert [s.eur_per_kwh for s in slots] == [0.25, 0.21]
    assert slots[0].end == slots[1].start
    assert slots[1].end - slots[1].start == timedelta(hours=1)


def test_parse_nordpool_epex_and_plain_lists():
    nordpool = {"raw_today": [{"start": "2026-10-14T00:00:00+02:00",
                               "end": "2026-10-14T01:00:00+02:00", "value": 23.5}]}
    assert parse_price_attributes(nordpool, TZ, date(2026, 10, 14))[0].eur_per_kwh == 0.235
    epex = {"data": [{"start_time": "2026-10-14T00:00:00+02:00",
                      "end_time": "2026-10-14T00:15:00+02:00", "price_per_kwh": 0.2}]}
    slot = parse_price_attributes(epex, TZ, date(2026, 10, 14))[0]
    assert slot.end - slot.start == timedelta(minutes=15)
    plain = {"today": [0.3] * 24}
    slots = parse_price_attributes(plain, TZ, date(2026, 10, 14))
    assert len(slots) == 24
    assert slots[0].start == local(2026, 10, 14, 0)


def test_dst_day_with_25_hourly_prices():
    slots = parse_price_attributes({"today": [0.3] * 25}, TZ, date(2026, 10, 25))
    assert slots[-1].end == local(2026, 10, 26, 0)


# ---------------------------------------------------------------- planning

def test_cheapest_single_block():
    best = cheapest_blocks(night_prices(), local(2026, 10, 13, 20), local(2026, 10, 14, 5),
                           timedelta(hours=2), 4.6)
    blocks, cost = best
    assert blocks == [(local(2026, 10, 14, 2), local(2026, 10, 14, 4))]
    assert cost == pytest.approx((0.18 + 0.17) * 4.6)


def test_two_blocks_only_when_allowed():
    slots = [PriceSlot(local(2026, 10, 14, h), local(2026, 10, 14, h + 1), p)
             for h, p in zip(range(0, 6), [0.1, 0.5, 0.5, 0.5, 0.1, 0.5], strict=True)]
    schedule = PriceSchedule(slots)
    one = cheapest_blocks(schedule, local(2026, 10, 14, 0), local(2026, 10, 14, 6),
                          timedelta(hours=2), 4.6, 1)
    two = cheapest_blocks(schedule, local(2026, 10, 14, 0), local(2026, 10, 14, 6),
                          timedelta(hours=2), 4.6, 2)
    assert len(one[0]) == 1
    assert len(two[0]) == 2
    assert two[1] < one[1]


def test_no_plan_without_full_price_coverage():
    assert cheapest_blocks(night_prices(), local(2026, 10, 13, 20), local(2026, 10, 14, 12),
                           timedelta(hours=2), 4.6) is None


def test_engine_charges_only_in_cheap_block():
    world = World(local(2026, 10, 13, 22, 0), configured=WITH_OVMS, price_source="tibber")
    world.engine.set_prices(night_prices().slots)
    world.set(Inp.OVMS_SOC, "70")
    world.set(Inp.OVMS_CHARGING, "off")
    world.tick()
    window = world.engine.next_window
    assert window.price_optimized
    assert window.blocks[0][0] >= local(2026, 10, 14, 2)
    # Only the energy the car needs, at the cheap block's price – not full power
    # over the whole block including the reserve.
    estimate = window.estimate
    assert estimate.needed_kwh * 0.17 <= estimate.cost_eur <= estimate.needed_kwh * 0.18 + 0.01
    world.run(60)
    assert world.engine.desired.charger_enabled is False
    world.now = window.blocks[0][0] - timedelta(seconds=5)
    world.run(60)
    assert world.engine.desired.charger_enabled is True
    # A rising SOC must not move the running block (latched).
    world.set(Inp.OVMS_SOC, "85")
    world.run(30)
    assert world.engine.next_window.blocks == window.blocks


def test_charge_runs_past_the_block_until_the_target():
    world = World(local(2026, 10, 13, 22, 0), configured=WITH_OVMS, price_source="tibber")
    world.engine.set_prices(night_prices().slots)
    world.set(Inp.OVMS_SOC, "70")
    world.set(Inp.OVMS_CHARGING, "off")
    world.tick()
    window = world.engine.next_window
    start, end = window.blocks[-1]
    world.now = start
    world.run(120)
    world.set(Inp.OVMS_CHARGING, "on")
    world.run(60)
    assert world.engine.executor.state is ExecState.CHARGING
    # Waking up took long / cold battery: the block ends below the target.
    world.now = end - timedelta(seconds=10)
    world.run(60)
    engine = world.engine
    assert engine.active_window is not None and engine.active_window.overrun
    assert engine.desired.charger_enabled is True
    assert engine.desired.wake_allowed is False
    assert "BLOCK_EXTENDED" in world.events
    # Target reached → off; the overrun ends with it.
    world.set(Inp.OVMS_SOC, "88")  # OVMS reports the SOC step by step
    world.run(5)
    world.set(Inp.OVMS_SOC, "90")
    world.run(60)
    assert engine.desired.charger_enabled is False
    assert not (engine.active_window and engine.active_window.overrun)


def test_block_is_not_extended_when_nothing_charges():
    world = World(local(2026, 10, 13, 22, 0), configured=WITH_OVMS, price_source="tibber")
    world.engine.set_prices(night_prices().slots)
    world.set(Inp.OVMS_SOC, "70")
    world.tick()
    start, end = world.engine.next_window.blocks[-1]
    world.car_charges_when_enabled = False
    world.now = start
    world.run(60)
    world.now = end - timedelta(seconds=10)
    world.run(60)
    assert not any(w.overrun for w in world.engine.windows)
    assert "BLOCK_EXTENDED" not in world.events


def test_cheap_block_while_away_is_planned_again():
    world = World(local(2026, 10, 13, 22, 0), configured=WITH_OVMS, price_source="tibber")
    world.engine.set_prices(night_prices().slots)
    world.set(Inp.OVMS_SOC, "70")
    world.set(Inp.OVMS_CHARGING, "off")
    world.set(Inp.CABLE_CONNECTED, "off")
    world.tick()
    block = world.engine.next_window.blocks[0]
    # The cheap block passes while the car is not at home ...
    world.now = block[0] + timedelta(minutes=1)
    world.run(30)
    world.now = block[1] + timedelta(minutes=10)
    world.run(30)
    assert not world.commands
    # ... plugged in afterwards it still charges before the departure.
    world.set(Inp.CABLE_CONNECTED, "on")
    world.run(30)
    assert block not in world.engine.next_window.blocks
    assert world.engine.desired.charger_enabled is True


def test_session_cost_uses_dynamic_price():
    world = World(local(2026, 10, 14, 1, 59), configured=WITH_OVMS, price_source="tibber",
                  price_optimization=False)
    world.engine.set_prices(night_prices().slots)
    world.engine.set_override(world.now, __import__(
        "custom_components.ev_charging_pilot.core.planner", fromlist=["OverrideMode"]
    ).OverrideMode.UNTIL_UNPLUGGED)
    world.run(30 * 60)
    world.set(Inp.CABLE_CONNECTED, "off")
    world.run(70)  # late Halo counter readings
    session = world.engine.monitor.data.sessions[-1]
    prices = {i["eur_per_kwh"] for i in session.energy_intervals}
    assert prices <= {0.32, 0.18}
    assert 0.18 in prices


# ---------------------------------------------------------------- external

def v(value, at, quality=Quality.GOOD):
    return Value(value, value, "ovms", at, quality)


def detector():
    return ExternalChargeDetector(capacity_kwh=16.7, efficiency=0.88, min_kwh=1.0,
                                  soc_jump_pct=5, price_eur_kwh=0.59, threshold_w=300)


def test_live_external_charge_detected_from_ovms():
    d = detector()
    t = local(2026, 10, 14, 12, 0)
    found = []
    for minute in range(61):
        now = t + timedelta(minutes=minute)
        found += d.update(now, vehicle_charging=v(True, now), vehicle_power=v(6000.0, now),
                          soc=v(40 + minute * 0.5, now), halo_power=v(0.0, now),
                          cable_connected=False, halo_total=v(1000.0, now))
    for minute in range(61, 75):
        now = t + timedelta(minutes=minute)
        found += d.update(now, vehicle_charging=v(False, now), vehicle_power=v(0.0, now),
                          soc=v(70.0, now), halo_power=v(0.0, now), cable_connected=False,
                          halo_total=v(1000.0, now))
    assert len(found) == 1
    assert found[0].energy_kwh == pytest.approx(6.0 / 0.88, rel=0.02)
    assert found[0].detected and found[0].quality == "ESTIMATED"


def test_home_charging_is_not_external():
    d = detector()
    t = local(2026, 10, 14, 3, 0)
    found = []
    for minute in range(60):
        now = t + timedelta(minutes=minute)
        found += d.update(now, vehicle_charging=v(True, now), vehicle_power=v(2200.0, now),
                          soc=v(40 + minute * 0.2, now), halo_power=v(2300.0, now),
                          cable_connected=True, halo_total=v(1000 + minute * 0.04, now))
    assert found == []


def test_soc_jump_without_halo_energy_is_detected():
    d = detector()
    t = local(2026, 10, 14, 8, 0)
    d.update(t, vehicle_charging=v(False, t), vehicle_power=Value.unavailable("ovms"),
             soc=v(40.0, t), halo_power=v(0.0, t), cable_connected=False,
             halo_total=v(1000.0, t))
    later = t + timedelta(hours=5)
    found = d.update(later, vehicle_charging=v(False, later),
                     vehicle_power=Value.unavailable("ovms"), soc=v(70.0, later),
                     halo_power=v(0.0, later), cable_connected=False,
                     halo_total=v(1000.0, later))
    assert len(found) == 1
    assert found[0].energy_kwh == pytest.approx(0.30 * 16.7 / 0.88, rel=0.01)
    # A jump explained by the Halo counter is home charging.
    d2 = detector()
    d2.update(t, vehicle_charging=v(False, t), vehicle_power=Value.unavailable("ovms"),
              soc=v(40.0, t), halo_power=v(0.0, t), cable_connected=True,
              halo_total=v(1000.0, t))
    assert d2.update(later, vehicle_charging=v(False, later),
                     vehicle_power=Value.unavailable("ovms"), soc=v(70.0, later),
                     halo_power=v(0.0, later), cable_connected=True,
                     halo_total=v(1005.7, later)) == []


def test_detector_round_trip():
    d = detector()
    t = local(2026, 10, 14, 12, 0)
    d.update(t, vehicle_charging=v(True, t), vehicle_power=v(6000.0, t), soc=v(40.0, t),
             halo_power=v(0.0, t), cable_connected=False, halo_total=v(1.0, t))
    copy = detector()
    copy.restore(d.as_dict())
    assert copy.as_dict() == d.as_dict()


def test_wallbox_outage_is_not_mistaken_for_external_charging():
    """Cable state unknown and no counter: a home charge must not become external."""
    d = detector()
    t = local(2026, 10, 14, 3, 0)
    found = []
    for minute in range(75):
        now = t + timedelta(minutes=minute)
        charging = minute < 60
        found += d.update(now, vehicle_charging=v(charging, now),
                          vehicle_power=v(2200.0 if charging else 0.0, now),
                          soc=v(40 + min(minute, 60) * 0.2, now),
                          halo_power=Value.unavailable("halo"), cable_connected=None,
                          halo_total=Value.unavailable("halo"))
    assert found == []


def test_external_note_uses_local_time():
    d = ExternalChargeDetector(capacity_kwh=16.7, efficiency=0.88, min_kwh=1.0, soc_jump_pct=5,
                               price_eur_kwh=0.59, threshold_w=300, tz=local(2026, 1, 1).tzinfo)
    t = local(2026, 10, 14, 12, 0)
    charge = d._charge(t, t + timedelta(hours=1), 5.0, 40, 70, "ovms_live")
    assert "12:00–13:00" in charge.note


# ---------------------------------------------------------------- reports

def test_pdf_writer_produces_valid_structure():
    doc = PdfDocument(title="Test äöü €")
    doc.text(50, 800, "Grüße – 12,50 €", 12, bold=True)
    doc.rect(50, 700, 100, 50, fill=(0.2, 0.4, 0.6))
    doc.new_page()
    doc.line(0, 0, 100, 100)
    data = doc.to_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert data.rstrip().endswith(b"%%EOF")
    assert b"/Count 2" in data
    assert text_width("100", 10) == pytest.approx(16.68)


def test_month_and_year_report():
    monitor = Monitor(TZ)
    start = local(2026, 10, 5, 3)
    monitor.add_session(ChargeSession(
        "s1", start, "schedule", ended_at=start + timedelta(hours=2), grid_energy_kwh=8.0,
        cost_eur=2.32, energy_intervals=[{"start": start.isoformat(),
                                          "end": (start + timedelta(minutes=15)).isoformat(),
                                          "kwh": 8.0, "eur_per_kwh": 0.29}]))
    monitor.add_external(ExternalCharge("e", date(2026, 10, 9), "public", 5.0, cost_eur=3.0,
                                        detected=True, quality="ESTIMATED"))
    settings = Settings.from_options({})
    now = local(2026, 11, 1, 6)
    month = month_report(monitor, settings, 2026, 10, now)
    year = year_report(monitor, settings, 2026, now)
    assert month.startswith(b"%PDF") and len(month) > 1500
    assert year.startswith(b"%PDF")


def test_typed_price_answers():
    from custom_components.ev_charging_pilot.core.statistics import parse_price_input

    assert parse_price_input("0,59") == 0.59
    assert parse_price_input("0.49 €/kWh") == 0.49
    assert parse_price_input("59 ct") == 0.59
    assert parse_price_input("79") == 0.79
    assert parse_price_input("") is None
    assert parse_price_input("weiß nicht") is None
    assert parse_price_input("450") is None  # 4,50 €/kWh is no plausible price


def test_quick_pick_price_setting():
    from custom_components.ev_charging_pilot.core.prices import parse_price_list

    assert parse_price_list("0,39; 0,49; 0,59; 0,69") == (0.39, 0.49, 0.59, 0.69)
    assert parse_price_list("49 ; 59ct ; quatsch ; 0,49 ; 0,79 ; 0,89") == (0.49, 0.59, 0.79,
                                                                              0.89)
    assert parse_price_list("") == ()
    assert Settings.from_options({}).external_price_buttons == (0.39, 0.49, 0.59, 0.69)


def test_more_price_formats():
    from custom_components.ev_charging_pilot.core.prices import describe_prices

    day = date(2026, 10, 17)
    # Pairs with epoch milliseconds and cents under an unknown name (sensor.tibber_preisprognose).
    start_ms = int(local(2026, 10, 17, 0).timestamp() * 1000)
    pairs = {"daten": [[start_ms + i * 900_000, 40 + i % 10] for i in range(192)],
             "unit_of_measurement": "EUR/kWh"}
    slots = parse_price_attributes(pairs, TZ, day)
    assert len(slots) == 192
    assert slots[0].start == local(2026, 10, 17, 0) and slots[0].eur_per_kwh == 0.40
    assert slots[-1].end == local(2026, 10, 19, 0)
    info = describe_prices(slots, TZ)
    assert info["minutes"] == 15 and info["max_eur_kwh"] == 0.49
    # ENTSO-e style.
    entsoe = {"prices_today": [{"time": "2026-10-17 00:00:00+02:00", "price": 0.21},
                               {"time": "2026-10-17 01:00:00+02:00", "price": 0.19}]}
    assert [s.eur_per_kwh for s in parse_price_attributes(entsoe, TZ, day)] == [0.21, 0.19]
    # €/MWh – including small values that must not be mistaken for €/kWh.
    mwh = {"data": [{"start_time": "2026-10-17T00:00:00+02:00", "price_per_kwh": 120.0},
                    {"start_time": "2026-10-17T01:00:00+02:00", "price_per_kwh": 3.0}],
           "unit_of_measurement": "EUR/MWh"}
    assert [s.eur_per_kwh for s in parse_price_attributes(mwh, TZ, day)] == [0.12, 0.003]
    # Epoch seconds work too.
    secs = {"forecast": [[int(local(2026, 10, 17, h).timestamp()), 0.3] for h in range(3)]}
    assert len(parse_price_attributes(secs, TZ, day)) == 3


def test_lidl_charge_with_a_charging_flag_sent_only_once():
    """Field 21.10.2026: OVMS sent "charging" at 16:01 and nothing more for 26 minutes;
    the charge power and "energy of this charge" kept coming. The live detection never
    started, a SOC jump at 16:14 reported 2.47 kWh – the car charged on to 4.35 kWh."""
    d = detector()
    t = local(2026, 10, 21, 16, 1)
    flag = Value(True, True, "ovms", t, Quality.LAST_KNOWN_VALID)  # aged single report
    found = []
    d.update(t - timedelta(minutes=1), vehicle_charging=v(False, t), vehicle_power=v(0.0, t),
             soc=v(66.0, t), halo_power=v(0.0, t), cable_connected=False,
             halo_total=v(22.36, t), charge_energy=v(8.34, t))  # the night's value
    for minute in range(27):
        now = t + timedelta(minutes=minute)
        found += d.update(now, vehicle_charging=flag, vehicle_power=v(18000.0 - minute * 450, now),
                          soc=v(66 + minute, now), halo_power=v(0.0, now),
                          cable_connected=False, halo_total=v(22.36, now),
                          charge_energy=v(round(0.36 + minute * 0.15, 2), now))
        if minute == 13:
            status = d.status
            assert status is not None and status["power_w"] > 10000
            assert status["battery_kwh"] == pytest.approx(0.36 + 13 * 0.15)
    assert found == []  # no early "finished" from the SOC jump
    for minute in range(27, 40):
        now = t + timedelta(minutes=minute)
        found += d.update(now, vehicle_charging=v(False, now), vehicle_power=v(0.0, now),
                          soc=v(92.0, now), halo_power=v(0.0, now), cable_connected=False,
                          halo_total=v(22.36, now), charge_energy=v(4.26, now))
    assert len(found) == 1
    assert found[0].energy_kwh == pytest.approx(4.26 / 0.88, rel=0.01)
    assert "(ovms_live)" in found[0].note
    assert d.status is None


def test_frozen_charge_power_after_the_charge_is_no_charge():
    """Field 22.10.2026: after Lidl OVMS kept repeating 5.695 kW (charging "off");
    the cockpit said "charging away" all day and would have booked a huge charge."""
    d = detector()
    t = local(2026, 10, 22, 4, 18)
    off = Value(False, False, "ovms", t, Quality.LAST_KNOWN_VALID)
    # A bogus live charge restored from the store, started at the HA restart.
    d.restore({"live": {"started_at": t.isoformat(), "soc_start": 80, "kwh_vehicle": 0.0,
                        "soc_end": 80, "charge_kwh": [4.35, 4.35, 4.35]}})
    found = []
    for minute in range(0, 6 * 60, 5):
        now = t + timedelta(minutes=minute)
        found += d.update(now, vehicle_charging=off, vehicle_power=v(5695.0, now),
                          soc=v(80.0, now), halo_power=v(0.0, now), cable_connected=False,
                          halo_total=v(22.36, now), charge_energy=v(4.35, now))
        if minute >= 15:
            assert d.status is None
    assert found == []
    assert d.live is None


def test_fresh_power_without_the_flag_still_counts():
    d = detector()
    t = local(2026, 10, 21, 16, 1)
    for minute in range(5):
        now = t + timedelta(minutes=minute)
        d.update(now, vehicle_charging=Value.unavailable("ovms"),
                 vehicle_power=v(18000.0 - minute * 400, now), soc=v(66 + minute, now),
                 halo_power=v(0.0, now), cable_connected=False, halo_total=v(22.36, now))
    assert d.status is not None and d.status["power_w"] == 16400.0
