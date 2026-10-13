"""Diagnostics download: executor state, last commands and events."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ChargingConfigEntry
from .const import CONF_NOTIFY_SERVICE, CONF_SHELLY_HOST

TO_REDACT = {CONF_SHELLY_HOST, CONF_NOTIFY_SERVICE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChargingConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "dry_run": c.dry_run,
        "executor": {
            "state": c.executor.state,
            "since": c.executor.state_since.isoformat() if c.executor.state_since else None,
            **c.executor.as_dict(),
        },
        "desired": repr(c.desired),
        "health": {"status": c.health.status, "reasons": list(c.health.reasons)},
        "soc": repr(c.soc),
        "commands": [
            {"at": r.at.isoformat(), "command": r.command.describe(), "executed": r.executed}
            for r in c.recorder.entries
        ],
        "events": list(c.events)[-200:],
    }
