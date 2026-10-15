"""Config flow (§13.1), reconfigure, options menu (§13.2), migration."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charging_pilot.const import DOMAIN

from .conftest import CABLE, CHARGER, ENERGY, POWER, RELAY

HALO = {"charger_enable": CHARGER, "cable_connected": CABLE, "charge_power": POWER,
        "total_energy": ENERGY}


async def test_user_flow_five_steps(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"vehicle_name": "Smarty", "dry_run": True})
    assert result["step_id"] == "halo"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], HALO)
    assert result["step_id"] == "shelly"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"shelly_host": "192.0.2.10"})
    assert result["errors"] == {"base": "host_without_relay"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cp_relay": RELAY, "shelly_host": "192.0.2.10"})
    assert result["step_id"] == "notify"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "ovms"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Smarty Charging Pilot"
    assert result["data"] == {**HALO, "cp_relay": RELAY,
                              "shelly_host": "192.0.2.10"}
    assert result["options"] == {"mode": "dry_run", "vehicle_name": "Smarty"}


async def test_options_menu_saves_and_price_history(hass, entry, halo):
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "monitor"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "odometer_source": "manual", "trip_merge_gap_min": 10, "event_retention_days": 90,
        "hv_cycles_warn_per_day": 10, "interval_min": 15, "price_eur_kwh": 0.31,
        "price_valid_from": "2026-11-01"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    history = entry.options["price_history"]
    assert [p["eur_per_kwh"] for p in history] == [0.29, 0.31]
    await hass.async_block_till_done()


async def test_reconfigure_removes_cleared_fields(hass, full_entry, halo):
    full_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    result = await full_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "halo"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], HALO)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_successful"
    assert "cp_relay" not in full_entry.data
    assert "ovms_soc" not in full_entry.data
    await hass.async_block_till_done()


async def test_migration_from_v1(hass, halo):
    old = MockConfigEntry(domain=DOMAIN, data=dict(HALO), options={"price_eur_kwh": 0.3},
                          version=1)
    old.add_to_hass(hass)
    assert await hass.config_entries.async_setup(old.entry_id)
    await hass.async_block_till_done()
    assert old.version == 2
    assert old.options["mode"] == "dry_run"
    assert old.data["name"]
