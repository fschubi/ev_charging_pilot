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
