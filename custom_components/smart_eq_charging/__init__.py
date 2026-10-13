"""Smart EQ 453 Charging Center – charging, wakeup and statistics for the smart EQ 453."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import ChargingCenter

type ChargingConfigEntry = ConfigEntry[ChargingCenter]


async def async_setup_entry(hass: HomeAssistant, entry: ChargingConfigEntry) -> bool:
    center = ChargingCenter(hass, entry)
    await center.async_setup()
    entry.runtime_data = center
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChargingConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ChargingConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
