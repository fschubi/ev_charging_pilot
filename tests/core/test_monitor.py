"""Trips, statistics with ΔSOC, climate profiles, settings, monitor storage."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from custom_components.ev_charging_pilot.core.climate import (
    climate_blocker,
    climate_request,
    homelink_level,
    planned_duration,
)
from custom_components.ev_charging_pilot.core.costs import FixedPriceHistory, PricePoint
from custom_components.ev_charging_pilot.core.model import Quality, Value
from custom_components.ev_charging_pilot.core.monitor import Monitor
from custom_components.ev_charging_pilot.core.sessions import ChargeSession
from custom_components.ev_charging_pilot.core.settings import Settings
from custom_components.ev_charging_pilot.core.statistics import (
    ExternalCharge,
    MonitorData,
    Reading,
    period_summary,
    temperature_statistics,
)
from custom_components.ev_charging_pilot.core.trips import Trip, TripTracker

from .world import TZ


def local(*args):
    return datetime(*args, tzinfo=TZ)


def v(value, at, quality=Quality.GOOD):
    return Value(value, value, "ovms", at, quality)


# ------------------------------------------------------------------ trips

def drive(tracker, start, minutes, km_start, km_end, used_start=0.0, used_end=2.0, temp=5.0):
    trips = []
    for i in range(minutes + 1):
        now = start + timedelta(minutes=i)
        frac = i / minutes
        trips += tracker.update(
            now, vehicle_on=v(True, now), odometer=v(km_start + (km_end - km_start) * frac, now),
            energy_used=v(used_start + (used_end - used_start) * frac, now),
            energy_recd=v(0.3 * frac, now), aux=v(0.1 * frac, now), soc=v(80 - 5 * frac, now),
            outside_temp=v(temp, now))
    return trips


def park(tracker, start, minutes, km):
    trips = []
    for i in range(1, minutes + 1):
        now = start + timedelta(minutes=i)
        trips += tracker.update(
            now, vehicle_on=v(False, now), odometer=v(km, now), energy_used=v(0, now),
            energy_recd=v(0, now), aux=v(0, now), soc=v(75, now), outside_temp=v(5, now))
    return trips


def test_trip_closes_after_merge_gap_and_short_stops_merge():
    tracker = TripTracker(10, TZ)
    start = local(2026, 10, 13, 7, 0)
    assert drive(tracker, start, 20, 1000, 1012) == []
    assert park(tracker, start + timedelta(minutes=20), 5, 1012) == []  # short stop
    assert drive(tracker, start + timedelta(minutes=25), 10, 1012, 1018, 2.0, 3.0) == []
    trips = park(tracker, start + timedelta(minutes=35), 11, 1018)
    assert len(trips) == 1
    trip = trips[0]
    assert trip.distance_km == pytest.approx(18)
    assert trip.vehicle_energy_used_kwh == pytest.approx(3.0)
    # The recuperation counter restarts with each drive (0 → 0.3 twice): both count.
    assert trip.recovered_energy_kwh == pytest.approx(0.6)
    # Net: drawn minus recuperated energy (OVMS counts both separately).
    assert trip.consumption_kwh_100km == pytest.approx((3.0 - 0.6) / 18 * 100, rel=1e-3)
    assert trip.quality == "GOOD"
    assert trip.season == "autumn"


def test_trip_reconstructed_from_odometer_is_partial():
    tracker = TripTracker(10, TZ)
    now = local(2026, 10, 13, 18, 0)
    unknown = Value.unavailable("ovms")
    tracker.update(now, vehicle_on=unknown, odometer=v(1000.0, now), energy_used=unknown,
                   energy_recd=unknown, aux=unknown, soc=None, outside_temp=unknown)
    later = now + timedelta(hours=3)
    trips = tracker.update(later, vehicle_on=unknown, odometer=v(1023.0, later),
                           energy_used=unknown, energy_recd=unknown, aux=unknown, soc=None,
                           outside_temp=unknown)
    assert len(trips) == 1
    assert trips[0].quality == "PARTIAL"
    assert trips[0].distance_km == pytest.approx(23)


# ------------------------------------------------------------- statistics

PRICES = FixedPriceHistory([PricePoint(date(2026, 1, 1), 0.30)], TZ)


def session(start, kwh, vehicle=None):
    return ChargeSession(
        session_id=f"s-{start:%d%H}", started_at=start, ended_at=start + timedelta(hours=2),
        reason="schedule", grid_energy_kwh=kwh, vehicle_charge_energy_kwh=vehicle,
        energy_intervals=[{"start": start.isoformat(),
                           "end": (start + timedelta(minutes=15)).isoformat(), "kwh": kwh}],
        cost_eur=kwh * 0.30)


def trip(start, km, used, temp):
    return Trip(f"t-{start:%d%H}", start, start + timedelta(minutes=30), None, None, km, 30,
                None, used, used * 0.1, used * 0.05, used / km * 100, temp, "autumn",
                None, None)


def test_month_balance_with_soc_correction():
    start, end = local(2026, 10, 1), local(2026, 11, 1)
    data = MonitorData(
        sessions=[session(local(2026, 10, 5, 3), 10.0, 9.0),
                  session(local(2026, 10, 31, 23, 50), 2.0)],  # interval belongs to October
        trips=[trip(local(2026, 10, 6, 7), 50, 8.0, 4.0),
               trip(local(2026, 10, 7, 7), 50, 7.0, 12.0)],
        external=[ExternalCharge("e1", date(2026, 10, 10), "public", 5.0, cost_eur=3.0)],
        odometer_readings=[Reading(local(2026, 9, 30, 20), 1000),
                           Reading(local(2026, 10, 31, 20), 1100)],
        soc_log=[Reading(local(2026, 9, 30, 22), 60), Reading(local(2026, 10, 31, 22), 80)],
        days_seen=set(),
    )
    month = period_summary(data, start, end, prices=PRICES, capacity_kwh=16.7, efficiency=0.88,
                           odometer_source="manual")
    assert month["home_energy_kwh"] == pytest.approx(12.0)
    assert month["external_energy_kwh"] == pytest.approx(5.0)
    assert month["distance_km"] == pytest.approx(100)
    assert month["delta_soc_pct"] == pytest.approx(20)
    # Ladeverlust nur aus Sessions mit gemessener Fahrzeugenergie: 10 − 9.
    assert month["charging_loss_kwh"] == pytest.approx(1.0)
    assert month["charging_loss_pct"] == pytest.approx(10.0)
    # (17 − 0.2·16.7/0.88) / 100 km · 100
    assert month["grid_consumption_kwh_100km"] == pytest.approx(17 - 0.2 * 16.7 / 0.88, rel=1e-3)
    assert month["cost_eur"] == pytest.approx(12 * 0.30 + 3.0)
    assert month["quality"] == "GOOD"
    assert month["outside_temp_avg_c"] == pytest.approx(8.0)


def test_missing_soc_marks_estimated_and_external_not_in_home_bill():
    data = MonitorData([], [], [ExternalCharge("e", date(2026, 10, 2), "workplace", 7.0)], [],
                       [], set())
    month = period_summary(data, local(2026, 10, 1), local(2026, 11, 1), prices=PRICES,
                           capacity_kwh=16.7, efficiency=0.88, odometer_source="manual")
    assert month["home_energy_kwh"] == 0
    assert month["external_energy_kwh"] == 7.0
    assert month["quality"] == "ESTIMATED"


def test_price_change_keeps_old_month():
    prices = FixedPriceHistory([PricePoint(date(2026, 1, 1), 0.30),
                                PricePoint(date(2026, 11, 1), 0.40)], TZ)
    data = MonitorData([session(local(2026, 10, 5, 3), 10.0)], [], [], [], [], set())
    month = period_summary(data, local(2026, 10, 1), local(2026, 11, 1), prices=prices,
                           capacity_kwh=16.7, efficiency=0.88, odometer_source="manual")
    assert month["home_cost_eur"] == pytest.approx(3.0)


def test_temperature_groups():
    stats = temperature_statistics(
        [trip(local(2026, 1, 6, 7), 20, 4.0, -3.0), trip(local(2026, 7, 7, 7), 20, 2.4, 22.0)],
        loss_pct=10, price_eur_kwh=0.3)
    assert stats["bands"]["<0"]["vehicle_kwh_100km"] == pytest.approx((4.0 - 0.4) / 20 * 100)
    assert stats["bands"][">=20"]["distance_km"] == 20
    assert stats["bands"]["<0"]["recuperation_share_pct"] == pytest.approx(10)
    assert stats["bands"]["<0"]["quality"] == "ESTIMATED"


def test_short_and_inconsistent_trips_do_not_distort_consumption():
    from custom_components.ev_charging_pilot.core.trips import net_energy

    assert net_energy(0.077, 0.155) is None  # counters reset mid-trip
    assert net_energy(1.0, None) == 1.0
    from dataclasses import replace

    real = trip(local(2026, 10, 16, 15), 20, 3.0, 20.0)
    parked = replace(real, trip_id="parked", distance_km=0, vehicle_energy_used_kwh=0.04)
    stats = temperature_statistics([parked, real], loss_pct=None, price_eur_kwh=0.3)
    assert stats["bands"][">=20"]["trips"] == 1
    assert stats["bands"][">=20"]["vehicle_kwh_100km"] == pytest.approx((3.0 - 0.3) / 20 * 100)


def test_odometer_source_auto_uses_ovms_when_mapped():
    from custom_components.ev_charging_pilot.core.settings import OdometerSource

    monitor = Monitor(TZ)
    auto = Settings.from_options({})
    assert auto.odometer_source is OdometerSource.AUTO
    assert not monitor.odometer_from_ovms(auto)
    monitor.ovms_odometer = True
    assert monitor.odometer_from_ovms(auto)
    assert not monitor.odometer_from_ovms(Settings.from_options({"odometer_source": "manual"}))


def test_monitor_round_trip():
    monitor = Monitor(TZ)
    monitor.add_session(session(local(2026, 10, 5, 3), 10.0))
    monitor.add_external(ExternalCharge("e1", date(2026, 10, 10), "public", 5.0))
    monitor.add_odometer(local(2026, 10, 1), 1000)
    monitor.record_soc(local(2026, 10, 1, 1), 50)
    monitor.record_soc(local(2026, 10, 1, 1, 30), 55)  # replaces, same hour
    monitor.record_day(date(2026, 10, 1))
    copy = Monitor(TZ)
    copy.restore(monitor.as_dict())
    assert copy.as_dict() == monitor.as_dict()
    assert len(copy.data.soc_log) == 1
    assert copy.delete_external("e1")


# ---------------------------------------------------------------- climate

def test_climate_profiles_and_blockers():
    settings = Settings.from_options({"climate_enabled": True, "ovms_enabled": True})
    now = local(2026, 1, 10, 6, 0)
    assert planned_duration("auto", v(-5.0, now), settings) == 15
    assert planned_duration("auto", v(20.0, now), settings) == 0
    assert planned_duration("auto", v(30.0, now), settings) == 10
    assert planned_duration("10", v(20.0, now), settings) == 10
    assert planned_duration("off", v(-5.0, now), settings) == 0
    assert homelink_level(15) == 3
    request = climate_request(local(2026, 1, 10, 7, 0), 10)
    # Ends two minutes after the departure, not before it (field 19.10.2026).
    assert request.start_at == local(2026, 1, 10, 6, 52)
    assert request.until == local(2026, 1, 10, 7, 2)
    assert climate_blocker(v(30.0, now), settings, False) == "SOC_TOO_LOW"
    assert climate_blocker(v(50.0, now, Quality.LAST_KNOWN_VALID), settings, False) is None
    assert climate_blocker(v(50.0, now), settings, True) == "HEALTH_NOT_HEALTHY"


def test_settings_defaults_follow_masterplan():
    s = Settings.from_options({})
    assert s.charge_efficiency == 0.88
    assert s.loss_timeout_s == 180
    assert not hasattr(s, "safety_margin_min")
    assert s.mode == "dry_run"
    assert s.grid_limit_kw is None
    assert Settings.from_options({"grid_limit_kw": 4.2}).grid_limit_kw == 4.2


def test_trip_keeps_a_drive_curve_every_15_seconds():
    tracker = TripTracker(10, TZ)
    start = local(2026, 10, 18, 19, 14, 45)
    for i in range(0, 241, 5):  # four minutes, ticks every 5 s
        now = start + timedelta(seconds=i)
        tracker.update(
            now, vehicle_on=v(True, now), odometer=v(9118.4 + i / 240, now),
            energy_used=v(i / 400, now), energy_recd=v(0, now), aux=v(0, now),
            soc=v(76 - i / 120, now), outside_temp=v(12, now),
            speed=v(60.0, now), battery_power=v(-21000.0, now))
    stored = tracker.as_dict()
    restored = TripTracker(10, TZ)
    restored.restore(stored)
    trips = park(restored, start + timedelta(seconds=240), 11, 9119.4)
    assert len(trips) == 1
    trace = trips[0].trace
    assert [p[0] for p in trace[:3]] == [0, 15, 30]
    assert trace[0][1:] == [60.0, -21000, 76.0]
    assert len(trace) == 17  # 0 … 240 s, survives the restart
    assert Trip.from_dict(trips[0].as_dict()).trace == trace


def lock_state(tracker, now, km, locked):
    return tracker.update(
        now, vehicle_on=v(False, now), odometer=v(km, now), energy_used=v(2.0, now),
        energy_recd=v(0.3, now), aux=v(0.1, now), soc=v(75, now), outside_temp=v(5, now),
        locked=v(locked, now))


def test_locking_after_switching_off_ends_the_trip_at_once():
    """Field 18.10.2026: off 19:32:23, unlocked, locked again 19:32:29."""
    tracker = TripTracker(10, TZ)
    start = local(2026, 10, 18, 19, 14, 45)
    drive(tracker, start, 17, 9118.4, 9132.8)  # the smart locks itself while driving
    off = start + timedelta(minutes=17, seconds=5)
    assert lock_state(tracker, off, 9132.8, True) == []  # still the driving lock
    assert lock_state(tracker, off + timedelta(seconds=2), 9132.8, False) == []  # door open
    trips = lock_state(tracker, off + timedelta(seconds=6), 9132.8, True)
    assert len(trips) == 1
    assert trips[0].ended_at == off
    assert trips[0].distance_km == pytest.approx(14.4)


def test_without_unlocking_the_merge_gap_still_applies():
    tracker = TripTracker(10, TZ)
    start = local(2026, 10, 18, 19, 0)
    drive(tracker, start, 10, 100, 105)
    off = start + timedelta(minutes=10, seconds=5)
    assert lock_state(tracker, off, 105, True) == []
    assert lock_state(tracker, off + timedelta(minutes=5), 105, True) == []
    assert len(lock_state(tracker, off + timedelta(minutes=10), 105, True)) == 1


def test_lock_binary_sensor_on_means_unlocked():
    from custom_components.ev_charging_pilot.core.inputs import Inp, RawState, to_value

    at = local(2026, 10, 18, 19, 32)
    sensor = {"device_class": "lock"}
    assert to_value(Inp.OVMS_LOCKED, RawState("on", at, at, sensor)).normalized is False
    assert to_value(Inp.OVMS_LOCKED, RawState("off", at, at, sensor)).normalized is True
    assert to_value(Inp.OVMS_LOCKED, RawState("locked", at, at, {})).normalized is True
    assert to_value(Inp.OVMS_LOCKED, RawState("unlocked", at, at, {})).normalized is False


def test_restore_repairs_duplicate_ids_and_overstated_climate():
    """Field 19.10.2026: the climate session reused the night's ID, climate 0.34 > 0.10 kWh."""
    from custom_components.ev_charging_pilot.core.monitor import Monitor
    from custom_components.ev_charging_pilot.core.sessions import ChargeSession

    night = ChargeSession(session_id="s-20261019-003045", reason="schedule",
                          started_at=local(2026, 10, 19, 2, 30, 45), grid_energy_kwh=7.92)
    climate = ChargeSession(session_id="s-20261019-003045", reason="climate",
                            started_at=local(2026, 10, 19, 5, 24, 31), grid_energy_kwh=0.10,
                            climate_energy_kwh=0.3448, climate_cost_eur=0.1512)
    monitor = Monitor(TZ)
    monitor.restore({"sessions": [night.as_dict(), climate.as_dict()]})
    first, second = monitor.data.sessions
    assert first.session_id == "s-20261019-003045"
    assert second.session_id == "s-20261019-003045-052431"
    assert second.climate_energy_kwh == 0.10
    assert second.climate_cost_eur == round(0.1512 * 0.10 / 0.3448, 4)


def _short_trip(trip_id, km, kwh100, temp=16.0):
    return Trip(trip_id=trip_id, started_at=local(2026, 10, 17, 9, 5),
                ended_at=local(2026, 10, 17, 9, 6), odometer_start_km=9103.0,
                odometer_end_km=9103.0 + km, distance_km=km, duration_min=1.1,
                average_speed_kmh=None, vehicle_energy_used_kwh=0.121,
                recovered_energy_kwh=0.0, auxiliary_energy_kwh=0.0,
                consumption_kwh_100km=kwh100, outside_temp_avg_c=temp, season="autumn",
                soc_start_pct=70, soc_end_pct=70)


def test_moving_the_car_shows_no_consumption_and_stays_out_of_the_groups():
    """Field 17.10.2026: 0.14 km showed 86.4 kWh/100 km, also in the 15–20 °C band."""
    from custom_components.ev_charging_pilot.core.monitor import Monitor
    from custom_components.ev_charging_pilot.core.statistics import temperature_statistics

    monitor = Monitor(TZ)
    monitor.restore({"trips": [_short_trip("t1", 0.14, 86.43).as_dict(),
                               _short_trip("t2", 0.06, 138.33).as_dict()]})
    assert [t.consumption_kwh_100km for t in monitor.data.trips] == [None, None]
    stats = temperature_statistics(monitor.data.trips, loss_pct=None, price_eur_kwh=0.4)
    assert stats["bands"]["15-20"]["trips"] == 0


def test_a_trip_can_be_deleted():
    from custom_components.ev_charging_pilot.core.monitor import Monitor

    monitor = Monitor(TZ)
    monitor.add_trip(_short_trip("t1", 0.14, None))
    monitor.add_trip(_short_trip("t2", 15.3, 19.4))
    assert monitor.delete_trip("t1") is True
    assert monitor.delete_trip("t1") is False
    assert [t.trip_id for t in monitor.data.trips] == ["t2"]
