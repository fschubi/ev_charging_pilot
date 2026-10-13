"""Smart EQ 453 Charging Center – charging, wakeup, climate and statistics for the smart EQ 453."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_PATH,
    PANEL_TITLE,
    PANEL_URL,
    PLATFORMS,
)
from .coordinator import ChargingCenter
from .core.settings import OPT_MODE
from .reports import ReportView
from .services import async_register_services, async_unregister_services
from .websocket_api import async_register as async_register_ws

_LOGGER = logging.getLogger(__name__)
PANEL_FILE = Path(__file__).parent / "frontend" / "smart-eq-panel.js"
PANEL_VERSION = "0.6.3"

type ChargingConfigEntry = ConfigEntry[ChargingCenter]


async def async_setup_entry(hass: HomeAssistant, entry: ChargingConfigEntry) -> None | bool:
    center = ChargingCenter(hass, entry)
    await center.async_setup()
    entry.runtime_data = center
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = dict(entry.options)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)
    async_register_ws(hass)
    if not hass.data.get(f"{DOMAIN}_views_registered"):
        hass.data[f"{DOMAIN}_views_registered"] = True
        hass.http.register_view(ReportView())
    await _async_register_panel(hass)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 (0.1.x) → v2: entity keys are unchanged, name and run mode are new."""
    if entry.version == 1:
        from .const import CONF_NAME, NAME

        data = {CONF_NAME: NAME, **entry.data}
        options = {OPT_MODE: "dry_run", **{k: v for k, v in entry.options.items()
                                           if k != "dry_run"}}
        hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChargingConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.config_entries.async_loaded_entries(DOMAIN):
            async_unregister_services(hass)
            if hass.data.pop(f"{DOMAIN}_panel_registered", False):
                async_remove_panel(hass, PANEL_PATH)
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: ChargingConfigEntry) -> None:
    """A mode switch only swaps the settings; every other change reloads (§13.2)."""
    previous = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    current = dict(entry.options)
    hass.data[DOMAIN][entry.entry_id] = current

    def without_mode(options: dict) -> dict:
        return {k: v for k, v in options.items() if k != OPT_MODE}

    if without_mode(previous) == without_mode(current):
        entry.runtime_data.apply_options(current)
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Sidebar panel (§12.5). No control logic inside – every action calls a service."""
    key = f"{DOMAIN}_panel_registered"
    if hass.data.get(key) or "frontend" not in hass.config.components:
        return
    hass.data[key] = True
    # Static routes cannot be removed again – register them once per HA run.
    if not hass.data.get(f"{DOMAIN}_static_registered"):
        hass.data[f"{DOMAIN}_static_registered"] = True
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_URL, str(PANEL_FILE), cache_headers=False)])
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_PATH,
        require_admin=False,
        config={
            "_panel_custom": {
                "name": PANEL_COMPONENT,
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{PANEL_URL}?v={PANEL_VERSION}",
            },
        },
    )
