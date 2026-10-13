"""Setup, dry-run safety and user actions of the integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from .conftest import CHARGER


async def _setup(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_creates_entities_and_starts_in_dry_run(hass, entry, halo):
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("switch.smart_eq_charging_center_dry_run").state == "on"
    assert hass.states.get("sensor.smart_eq_charging_center_charging_state").state == "idle"
    assert hass.states.get("sensor.smart_eq_charging_center_system_health").state == "healthy"


async def test_charge_now_in_dry_run_only_logs(hass, entry, halo):
    calls = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.smart_eq_charging_center_charge_now"},
        blocking=True)
    await hass.async_block_till_done()
    assert calls == []
    center = entry.runtime_data
    assert any(e["code"] == "DRY_RUN" for e in center.events)
    assert hass.states.get("binary_sensor.smart_eq_charging_center_override_active").state == "on"


async def test_charge_now_without_dry_run_switches_halo(hass, entry, halo):
    calls = async_mock_service(hass, "homeassistant", "turn_on")
    await _setup(hass, entry)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.smart_eq_charging_center_dry_run"},
        blocking=True)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.smart_eq_charging_center_charge_now"},
        blocking=True)
    await hass.async_block_till_done()
    assert [c.data["entity_id"] for c in calls] == [CHARGER]


async def test_unload(hass, entry, halo):
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
