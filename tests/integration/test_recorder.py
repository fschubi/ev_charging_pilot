"""Replay datasets straight from the recorder history (Phase-0 nights)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.ev_charging_pilot.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The recorder must be set up before hass – override the shared autouse fixture."""
    yield


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()



async def test_create_replay_dataset_from_recorder(hass, entry, halo, tmp_path):
    from unittest.mock import patch

    from homeassistant.components.recorder import get_instance

    from .conftest import POWER

    start = dt_util.utcnow() - timedelta(minutes=1)
    await _setup(hass, entry)
    hass.states.async_set(POWER, "2300", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await get_instance(hass).async_block_till_done()
    center = entry.runtime_data
    with patch.object(type(center), "data_dir", new=tmp_path):
        result = await hass.services.async_call(
            DOMAIN, "create_replay_dataset",
            {"start": start, "end": dt_util.utcnow() + timedelta(seconds=1), "name": "night",
             "poll_interval_s": 30},
            blocking=True, return_response=True)
        assert result["file"] == "night.json"
        assert result["inputs"]["charge_power"] >= 2
        replay = await hass.services.async_call(
            DOMAIN, "start_replay", {"file": "night.json"}, blocking=True, return_response=True)
    assert replay["name"] == "night"
    assert replay["ticks"] > 0


async def test_cockpit_chart_is_filled_from_the_recorder(hass, entry, halo, freezer):
    from homeassistant.components.recorder import get_instance

    from .conftest import POWER

    hass.states.async_set(POWER, "2.3", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    await get_instance(hass).async_block_till_done()
    freezer.tick(timedelta(minutes=10))  # the chart covers completed minutes
    await _setup(hass, entry)
    center = entry.runtime_data
    center.history.clear()
    await center._async_backfill_history()  # also runs in the background on setup
    history = list(center.history)
    assert len(history) >= 1000  # a full day of minutes
    assert any(power == 2300 for _, power, _ in history)


async def test_session_detail_takes_the_curve_from_the_recorder(hass, entry, halo, freezer,
                                                               hass_ws_client):
    from homeassistant.components.recorder import get_instance

    from custom_components.ev_charging_pilot.core.sessions import ChargeSession

    from .conftest import POWER

    start = dt_util.utcnow()
    hass.states.async_set(POWER, "9.2", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    await get_instance(hass).async_block_till_done()
    freezer.tick(timedelta(minutes=20))
    await _setup(hass, entry)
    center = entry.runtime_data
    # A session from before v0.20.0: no curve of its own.
    center.monitor.add_session(ChargeSession(
        session_id="old", started_at=start, ended_at=start + timedelta(minutes=10),
        reason="one_shot", grid_energy_kwh=1.5))
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/get_session_detail", "session_id": "old"})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert msg["result"]["trace_source"] == "recorder"
    assert len(msg["result"]["trace"]) >= 10
    assert msg["result"]["trace"][0][0] == 0
    assert any(p[1] == 9200 for p in msg["result"]["trace"])


async def test_older_sessions_get_their_battery_energy_from_the_recorder(hass, halo, freezer):
    """v0.25.0: sessions stored with the grid-side charge power get OVMS charge_energy."""
    from homeassistant.components.recorder import get_instance
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_charging_pilot.core.sessions import ChargeSession

    from .conftest import DATA, SOC

    kwh = "sensor.car_charge_energy"
    start = dt_util.utcnow()
    hass.states.async_set(kwh, "7.92", {"unit_of_measurement": "kWh"})  # previous charge
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=2))
    hass.states.async_set(kwh, "0.1", {"unit_of_measurement": "kWh"})  # new charge starts
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=60))
    hass.states.async_set(kwh, "7.68", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    await get_instance(hass).async_block_till_done()
    freezer.tick(timedelta(minutes=30))
    entry = MockConfigEntry(domain=DOMAIN, data={**DATA, "ovms_soc": SOC, "ovms_charge_energy": kwh,
                                                 "charge_energy_discovery_done": True},
                            options={"mode": "dry_run"}, version=2, minor_version=2)
    await _setup(hass, entry)
    center = entry.runtime_data
    center.monitor.data.sessions = [ChargeSession(
        session_id="s1", started_at=start + timedelta(minutes=1),
        ended_at=start + timedelta(minutes=63), reason="schedule", grid_energy_kwh=8.99,
        vehicle_charge_energy_kwh=8.97)]
    assert await center.async_backfill_charge_energy() == 1
    session = center.monitor.data.sessions[0]
    assert session.vehicle_charge_energy_kwh == 7.68
    assert session.vehicle_energy_source == "ovms_charge_energy"
    assert await center.async_backfill_charge_energy() == 0  # only once


async def test_older_trips_get_their_range_from_the_recorder(hass, halo, freezer):
    from homeassistant.components.recorder import get_instance
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_charging_pilot.core.trips import Trip

    from .conftest import DATA, SOC

    reach = "sensor.car_estimated_range"
    start = dt_util.utcnow()
    hass.states.async_set(reach, "80", {"unit_of_measurement": "km"})
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=10))
    hass.states.async_set(reach, "65", {"unit_of_measurement": "km"})
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=10))
    hass.states.async_set(reach, "50", {"unit_of_measurement": "km"})
    await hass.async_block_till_done()
    await get_instance(hass).async_block_till_done()
    freezer.tick(timedelta(minutes=5))
    entry = MockConfigEntry(domain=DOMAIN, data={**DATA, "ovms_soc": SOC, "ovms_range": reach},
                            options={"mode": "dry_run"}, version=2, minor_version=2)
    await _setup(hass, entry)
    center = entry.runtime_data
    center.monitor.data.trips = [Trip(
        trip_id="t1", started_at=start + timedelta(seconds=30),
        ended_at=start + timedelta(minutes=20, seconds=30), odometer_start_km=9300,
        odometer_end_km=9325, distance_km=25.0, duration_min=20, average_speed_kmh=75,
        vehicle_energy_used_kwh=4.0, recovered_energy_kwh=0.3, auxiliary_energy_kwh=0.1,
        consumption_kwh_100km=14.8, outside_temp_avg_c=9.0, season="autumn",
        soc_start_pct=54, soc_end_pct=33)]
    assert await center.async_backfill_trip_range() == 1
    trip = center.monitor.data.trips[0]
    assert (trip.range_start_km, trip.range_end_km) == (80, 50)
    assert await center.async_backfill_trip_range() == 0


async def test_older_trips_get_their_driving_style_from_the_recorder(hass, halo, freezer):
    from homeassistant.components.recorder import get_instance
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_charging_pilot.core.trips import Trip

    from .conftest import DATA, SOC

    speed = "sensor.car_vehicle_speed"
    start = dt_util.utcnow()
    for value in [0, 30, 50, 60] + [70, 72, 70, 71] * 8 + [40, 0]:
        hass.states.async_set(speed, str(value), {"unit_of_measurement": "km/h"})
        await hass.async_block_till_done()
        freezer.tick(timedelta(seconds=15))
    await get_instance(hass).async_block_till_done()
    freezer.tick(timedelta(minutes=2))
    entry = MockConfigEntry(domain=DOMAIN, data={**DATA, "ovms_soc": SOC, "ovms_speed": speed},
                            options={"mode": "dry_run"}, version=2, minor_version=2)
    await _setup(hass, entry)
    center = entry.runtime_data
    center.monitor.data.trips = [Trip(
        trip_id="t1", started_at=start, ended_at=start + timedelta(minutes=9),
        odometer_start_km=9300, odometer_end_km=9310, distance_km=10.0, duration_min=9,
        average_speed_kmh=66, vehicle_energy_used_kwh=1.6, recovered_energy_kwh=0.1,
        auxiliary_energy_kwh=0.05, consumption_kwh_100km=15.0, outside_temp_avg_c=9.0,
        season="autumn", soc_start_pct=54, soc_end_pct=46)]
    assert await center.async_backfill_trip_style() == 1
    assert center.monitor.data.trips[0].style["score"] >= 80
