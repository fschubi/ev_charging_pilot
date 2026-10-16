"""Vehicle access: read only vs. read & write, automatic OVMS command path, charge now."""

from __future__ import annotations

from homeassistant.core import SupportsResponse
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charging_pilot.const import DOMAIN
from custom_components.ev_charging_pilot.core.planner import OverrideMode
from custom_components.ev_charging_pilot.core.ports import Command, CommandKind
from custom_components.ev_charging_pilot.ha_ports import OVMS_PATH_SERVICE

from .conftest import DATA, SOC


def _ovms(hass, calls):
    """The HACS OVMS integration: config entry with vehicle_id and send_command."""
    ovms = MockConfigEntry(domain="ovms", data={"vehicle_id": "SMARTY"})
    ovms.add_to_hass(hass)
    er.async_get(hass).async_get_or_create("sensor", "ovms", "smarty_soc",
                                           suggested_object_id="ovms_soc", config_entry=ovms)

    async def send_command(call):
        calls.append(dict(call.data))
        return {"success": True}

    hass.services.async_register("ovms", "send_command", send_command,
                                 supports_response=SupportsResponse.OPTIONAL)


async def _setup(hass, **options):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={**DATA, "ovms_soc": SOC},
                            options={"mode": "live", **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_command_path_found_automatically_but_read_only_by_default(hass, halo):
    calls: list = []
    _ovms(hass, calls)
    entry = await _setup(hass)
    center = entry.runtime_data
    assert center.ports.ovms_path == OVMS_PATH_SERVICE
    # read only: the executor may not wake the car
    assert center.engine.executor.config.ovms_available is False


async def test_read_write_sends_ready_made_commands(hass, halo):
    calls: list = []
    _ovms(hass, calls)
    entry = await _setup(hass, ovms_enabled=True, climate_enabled=True)
    center = entry.runtime_data
    await center.async_tick()
    assert center.engine.executor.config.ovms_available is True
    assert center.engine.executor.config.climate_available is True
    await center.ports.execute(Command(CommandKind.OVMS_WAKEUP), center.settings)
    await center.ports.execute(Command(CommandKind.CLIMATE_START, {"duration_min": 10}),
                               center.settings)
    assert calls == [{"vehicle_id": "SMARTY", "command": "wakeup"},
                     {"vehicle_id": "SMARTY", "command": "homelink 2"}]


async def test_charge_now_uses_manual_target_and_target_applies_live(hass, halo):
    entry = await _setup(hass, mode="dry_run", manual_target_soc=80)
    center = entry.runtime_data
    await hass.services.async_call(DOMAIN, "start_charging", {}, blocking=True)
    assert center.engine.override.mode is OverrideMode.UNTIL_SOC
    assert center.engine.override.target_soc == 80

    # Changing the manual target does not reload the integration.
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.ev_pilot_manual_target_soc", "value": 90},
        blocking=True)
    await hass.async_block_till_done()
    assert entry.runtime_data is center
    assert center.settings.manual_target_soc == 90


async def test_charge_now_without_vehicle_data_charges_until_unplugged(hass, halo):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data=dict(DATA),
                            options={"mode": "dry_run", "manual_target_soc": 80})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "start_charging", {}, blocking=True)
    assert entry.runtime_data.engine.override.mode is OverrideMode.UNTIL_UNPLUGGED


async def test_smart_453_gets_xsq_wakeup(hass, halo):
    calls: list = []
    _ovms(hass, calls)
    er.async_get(hass).async_get_or_create("sensor", "ovms", "smarty_xsq_bms_soh",
                                           suggested_object_id="ovms_xsq_bms_soh")
    entry = await _setup(hass, ovms_enabled=True)
    center = entry.runtime_data
    assert center.ports.wakeup_command("auto") == "xsq wakeup"
    assert center.ports.wakeup_command("wakeup") == "wakeup"
    await center.ports.execute(Command(CommandKind.OVMS_WAKEUP), center.settings)
    assert calls[-1]["command"] == "xsq wakeup"
