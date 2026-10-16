"""Settings tab API, vehicle photo upload/serve/delete."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from aiohttp import FormData

from custom_components.ev_charging_pilot.const import DOMAIN
from custom_components.ev_charging_pilot.settings_schema import GROUPS, apply_changes

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_apply_changes_validates_and_keeps_price_history():
    new = apply_changes({}, {"power_threshold_w": 400, "ovms_enabled": True,
                             "price_eur_kwh": 0.31, "price_valid_from": "2026-11-01"})
    assert new["power_threshold_w"] == 400
    assert [p["eur_per_kwh"] for p in new["price_history"]] == [0.29, 0.31]
    with pytest.raises(ValueError):
        apply_changes({}, {"power_threshold_w": 99999})
    with pytest.raises(ValueError):
        apply_changes({}, {"unknown": 1})
    with pytest.raises(ValueError):
        apply_changes({}, {"price_source": "entity"})


def test_every_option_group_matches_the_options_flow():
    keys = {f["key"] for g in GROUPS for f in g["fields"]}
    assert {"mode", "cp_pulse_s", "price_source", "external_detection",
            "ovms_wakeup_command", "plug_reminder_time"} <= keys


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_settings_ws_roundtrip(hass, entry, halo, hass_ws_client):
    await _setup(hass, entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/get_settings"})
    msg = await client.receive_json()
    assert msg["result"]["values"]["price_eur_kwh"] == 0.29
    assert msg["result"]["is_admin"] is True
    await client.send_json({"id": 2, "type": f"{DOMAIN}/set_settings",
                            "values": {"price_eur_kwh": 0.33, "price_valid_from": "2026-12-01",
                                       "loss_timeout_s": 240}})
    msg = await client.receive_json()
    assert msg["success"], msg
    await hass.async_block_till_done()
    assert entry.options["loss_timeout_s"] == 240
    assert entry.options["price_history"][-1] == {"valid_from": "2026-12-01",
                                                  "eur_per_kwh": 0.33}
    await client.send_json({"id": 3, "type": f"{DOMAIN}/set_settings",
                            "values": {"cp_pulse_s": 99}})
    msg = await client.receive_json()
    assert not msg["success"]
    assert "CP-Pulses" in msg["error"]["message"]


async def test_vehicle_photo_upload_serve_delete(hass, entry, halo, hass_client, tmp_path):
    await _setup(hass, entry)
    client = await hass_client()
    with patch("custom_components.ev_charging_pilot.vehicle_image.image_dir",
               return_value=tmp_path):
        bad = FormData()
        bad.add_field("file", io.BytesIO(b"GIF89a....."), filename="x.gif")
        response = await client.post("/api/ev_charging_pilot/vehicle_image", data=bad)
        assert response.status == 415

        form = FormData()
        form.add_field("file", io.BytesIO(PNG), filename="smart.png", content_type="image/png")
        response = await client.post("/api/ev_charging_pilot/vehicle_image", data=form)
        assert response.status == 200
        assert (tmp_path / "vehicle.png").exists()
        assert entry.runtime_data.vehicle_image_version is not None

        response = await client.get("/api/ev_charging_pilot/vehicle_image")
        assert response.status == 200
        assert (await response.read()).startswith(b"\x89PNG")

        response = await client.delete("/api/ev_charging_pilot/vehicle_image")
        assert response.status == 200
        assert not (tmp_path / "vehicle.png").exists()
        assert entry.runtime_data.vehicle_image_version is None


async def test_vehicle_photo_needs_login(hass, entry, halo, hass_client_no_auth):
    await _setup(hass, entry)
    client = await hass_client_no_auth()
    assert (await client.get("/api/ev_charging_pilot/vehicle_image")).status == 401


async def test_non_admin_can_plan_and_set_target_but_not_settings(
        hass, entry, halo, hass_ws_client, hass_read_only_access_token):
    await _setup(hass, entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/set_plans", "plans": [
        {"id": "a", "name": "Arbeit", "weekdays": ["mon"], "departure_time": "07:00"}]})
    assert (await client.receive_json())["success"]
    await client.send_json({"id": 2, "type": f"{DOMAIN}/set_manual_target", "value": 82})
    msg = await client.receive_json()
    assert msg["success"] and msg["result"]["value"] == 80
    await hass.async_block_till_done()
    assert entry.options["manual_target_soc"] == 80
    await client.send_json({"id": 3, "type": f"{DOMAIN}/set_settings",
                            "values": {"loss_timeout_s": 240}})
    assert not (await client.receive_json())["success"]
