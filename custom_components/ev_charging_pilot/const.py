"""Constants of the Home Assistant side. Option keys live in core/settings.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from .core.inputs import Inp

DOMAIN: Final = "ev_charging_pilot"


def _manifest_version() -> str:
    """Integration version from manifest.json – the single source of truth."""
    try:
        data = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))
        return str(data.get("version") or "0.0.0").strip()
    except (OSError, ValueError):
        return "0.0.0"


# Read once at import (HA imports integrations in an executor thread).
VERSION: Final = _manifest_version()
NAME: Final = "EV Charging Pilot"
ENTITY_PREFIX: Final = "ev_pilot"

PLATFORMS: Final = ["sensor", "binary_sensor", "switch", "button", "select", "number", "time"]

STORAGE_VERSION: Final = 1
STORAGE_KEY_STATE: Final = f"{DOMAIN}.state"
STORAGE_KEY_EVENTS: Final = f"{DOMAIN}.events"
STORAGE_KEY_MONITOR: Final = f"{DOMAIN}.monitor"

TICK_SECONDS: Final = 5
STATISTICS_REFRESH_S: Final = 60
BUS_EVENT: Final = f"{DOMAIN}_event"
DATA_DIR: Final = DOMAIN  # below the HA config dir: replay datasets and exports

PANEL_URL: Final = "/ev_charging_pilot_panel"
PANEL_PATH: Final = "ev-pilot"
PANEL_TITLE: Final = NAME
PANEL_ICON: Final = "mdi:car-electric"
PANEL_COMPONENT: Final = "ev-pilot-panel"

# --- Config entry data (§13.1). Entities are always chosen via selector.
CONF_NAME: Final = "name"
# The vehicle's own name ("Smarty") – the UI then calls itself "Smarty Charging Pilot".
CONF_VEHICLE_NAME: Final = "vehicle_name"
DEFAULT_VEHICLE_NAME: Final = "Mein EV"


def title_for(vehicle_name: str | None) -> str:
    name = (vehicle_name or "").strip()
    return f"{name} Charging Pilot" if name else NAME
CONF_SHELLY_HOST: Final = "shelly_host"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_OVMS_COMMAND_TOPIC: Final = "ovms_command_topic"
CONF_OVMS_COMMAND_SCRIPT: Final = "ovms_command_script"

HALO_REQUIRED: Final = (Inp.CHARGER_ENABLE, Inp.CABLE_CONNECTED, Inp.CHARGE_POWER,
                        Inp.TOTAL_ENERGY)
HALO_OPTIONAL: Final = (Inp.CHARGER_STATUS, Inp.MAX_CURRENT, Inp.CABLE_LOCK,
                        Inp.INTERNAL_SCHEDULE)
OVMS_INPUTS: Final = (
    Inp.OVMS_SOC, Inp.OVMS_SOH, Inp.OVMS_RANGE, Inp.OVMS_ODOMETER, Inp.OVMS_CHARGING,
    Inp.OVMS_CHARGE_POWER, Inp.OVMS_BATTERY_TEMP, Inp.OVMS_HV_CYCLES, Inp.OVMS_VEHICLE_ON,
    Inp.OVMS_OUTSIDE_TEMP, Inp.OVMS_ENERGY_USED, Inp.OVMS_ENERGY_RECD,
    Inp.OVMS_AUX_CONSUMPTION, Inp.OVMS_12V,
)
INPUT_DOMAINS: Final = {
    Inp.CHARGER_ENABLE: "switch",
    Inp.CABLE_CONNECTED: "binary_sensor",
    Inp.CHARGE_POWER: "sensor",
    Inp.TOTAL_ENERGY: "sensor",
    Inp.CHARGER_STATUS: "sensor",
    Inp.MAX_CURRENT: ["number", "sensor"],
    Inp.CABLE_LOCK: ["lock", "binary_sensor", "sensor"],
    Inp.INTERNAL_SCHEDULE: "switch",
    Inp.CP_RELAY: "switch",
    Inp.OVMS_CHARGING: ["binary_sensor", "sensor"],
    Inp.OVMS_VEHICLE_ON: ["binary_sensor", "sensor"],
    Inp.OUTSIDE_TEMP: "sensor",
    Inp.WEATHER: "weather",
}

# Mobile-app notification actions of the plug-in question (§8.4).
ACTION_PLAN: Final = "SMART_EQ_PLAN"
ACTION_TONIGHT: Final = "SMART_EQ_TONIGHT"
ACTION_NOW: Final = "SMART_EQ_NOW"

# Events that also go into the HA logbook (§8.5).
LOGBOOK_SEVERITIES: Final = ("warning", "error", "critical")
LOGBOOK_CODES: Final = (
    "CHARGE_STABLE", "SESSION_END", "CHARGE_ENDED", "OVMS_WAKEUP", "CP_PULSE_START",
    "CP_PULSE_DONE", "CLIMATE_START", "OVERRIDE_SET", "ONE_SHOT_SET", "RESET",
)
