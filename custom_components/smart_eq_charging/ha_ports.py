"""Home Assistant implementations of the core ports (§4.3).

Every port checks ``dry_run`` itself: in dry-run the command is only logged
("WOULD ENABLE CHARGER") – the executor above runs exactly the same way.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import aiohttp
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .core.ports import Command, CommandKind

_LOGGER = logging.getLogger(__name__)

SHELLY_TIMEOUT_S = 5


class PortError(Exception):
    """A command could not be delivered."""


class HaPorts:
    """Dispatches executor commands to the Halo switch and the Shelly."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        charger_switch: str,
        cp_relay: str | None,
        shelly_host: str | None,
        dry_run: Callable[[], bool],
    ) -> None:
        self.hass = hass
        self.charger_switch = charger_switch
        self.cp_relay = cp_relay
        self.shelly_host = shelly_host
        self._dry_run = dry_run

    async def dispatch(self, command: Command) -> bool:
        """Execute ``command``. Returns False when only logged (dry-run)."""
        if self._dry_run():
            _LOGGER.info("Dry-Run: WOULD %s", command.describe())
            return False
        match command.kind:
            case CommandKind.ENABLE_CHARGER:
                await self._switch(self.charger_switch, True)
            case CommandKind.DISABLE_CHARGER:
                await self._switch(self.charger_switch, False)
            case CommandKind.CP_PULSE:
                await self._cp_pulse(int(command.params["seconds"]))
            case CommandKind.CP_CLOSE:
                if self.cp_relay is None:
                    raise PortError("no CP relay configured")
                await self._switch(self.cp_relay, True)
            case CommandKind.OVMS_WAKEUP | CommandKind.CLIMATE_START:
                # OVMS mapping follows after the real-vehicle test (§2.3, §16).
                raise PortError(f"{command.kind} not available yet")
        _LOGGER.info("Executed %s", command.describe())
        return True

    async def _switch(self, entity_id: str, on: bool) -> None:
        await self.hass.services.async_call(
            "homeassistant",
            SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
            {"entity_id": entity_id},
            blocking=True,
        )

    async def _cp_pulse(self, seconds: int) -> None:
        """One RPC call; the Shelly closes the contact again by itself (§3.1).

        ``toggle_after`` is the only place the pulse length is set, so HA
        crashing mid-pulse cannot leave the CP open.
        """
        if not self.shelly_host:
            raise PortError("no Shelly host configured for the CP pulse")
        url = f"http://{self.shelly_host}/rpc/Switch.Set"
        params = {"id": "0", "on": "false", "toggle_after": str(seconds)}
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=SHELLY_TIMEOUT_S)
        async with session.get(url, params=params, timeout=timeout) as response:
            if response.status != 200:
                raise PortError(f"Shelly answered HTTP {response.status}")

    async def shelly_switch_config(self) -> dict[str, Any] | None:
        """Read ``Switch.GetConfig`` for the config-drift check (§7.5)."""
        if not self.shelly_host:
            return None
        url = f"http://{self.shelly_host}/rpc/Switch.GetConfig"
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, params={"id": "0"},
                                   timeout=aiohttp.ClientTimeout(total=SHELLY_TIMEOUT_S)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError):
            return None


def shelly_config_ok(config: dict[str, Any], pulse_s: int) -> bool:
    """Auto-on and power-on default must back up the pulse (§3.1)."""
    return (
        config.get("initial_state") == "on"
        and config.get("auto_on") is True
        and float(config.get("auto_on_delay", -1)) == float(pulse_s)
    )
