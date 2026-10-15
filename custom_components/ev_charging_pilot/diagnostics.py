"""Diagnostics download: state, settings, last commands and events (redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ChargingConfigEntry
from .const import CONF_NOTIFY_SERVICE, CONF_OVMS_COMMAND_TOPIC, CONF_SHELLY_HOST
from .websocket_api import snapshot

# The Halo API key lives in the Chargeamps integration, never here – but host
# names, push targets and MQTT topics identify the installation.
TO_REDACT = {CONF_SHELLY_HOST, CONF_NOTIFY_SERVICE, CONF_OVMS_COMMAND_TOPIC, "api_key",
             "password", "token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChargingConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "settings": asdict(c.settings),
        "state": async_redact_data(snapshot(c), TO_REDACT),
        "engine": c.engine.as_dict(),
        "commands": [
            {"at": r.at.isoformat(), "command": r.command.describe(), "executed": r.executed}
            for r in c.recorder.entries
        ],
        "events": list(c.events)[-300:],
        "monitor_counts": {
            "sessions": len(c.monitor.data.sessions),
            "trips": len(c.monitor.data.trips),
            "external": len(c.monitor.data.external),
        },
    }
