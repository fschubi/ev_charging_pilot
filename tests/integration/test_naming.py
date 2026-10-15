"""The vehicle name drives every visible title ("Smarty Charging Pilot")."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.ev_charging_pilot.const import DOMAIN, title_for

from .conftest import CABLE, DATA


def test_title_for():
    assert title_for("Smarty") == "Smarty Charging Pilot"
    assert title_for("  ") == "EV Charging Pilot"
    assert title_for(None) == "EV Charging Pilot"


async def test_vehicle_name_sets_titles_and_can_be_renamed(hass, halo, hass_ws_client):
    entry = MockConfigEntry(domain=DOMAIN, version=2, title="x",
                            data={**DATA, "notify_service": "notify.mobile_app_phone"},
                            options={"mode": "dry_run", "vehicle_name": "Smarty"})
    entry.add_to_hass(hass)
    pushes = async_mock_service(hass, "notify", "mobile_app_phone")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.title == "Smarty Charging Pilot"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.name == "Smarty Charging Pilot"

    # Push titles carry the vehicle name.
    hass.states.async_set(CABLE, "off")
    await hass.async_block_till_done()
    hass.states.async_set(CABLE, "on")
    await hass.async_block_till_done()
    assert pushes and pushes[-1].data["title"].startswith("Smarty: ")

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/set_settings",
                            "values": {"vehicle_name": "Flitzer"}})
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    assert entry.title == "Flitzer Charging Pilot"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.name == "Flitzer Charging Pilot"
    await client.send_json({"id": 2, "type": f"{DOMAIN}/state"})
    state = (await client.receive_json())["result"]
    assert state["name"] == "Flitzer Charging Pilot"
    assert state["vehicle_name"] == "Flitzer"
