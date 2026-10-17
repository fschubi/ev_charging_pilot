"""Home Assistant implementations of the core ports (§4.3).

Only the coordinator calls :meth:`HaPorts.execute`, and only in live mode;
dry-run and replay never reach this module.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .core.climate import homelink_level
from .core.ports import Command, CommandKind
from .core.settings import Settings

_LOGGER = logging.getLogger(__name__)

SHELLY_TIMEOUT_S = 5


OVMS_DOMAIN = "ovms"
OVMS_PATH_SERVICE = "ovms_service"
OVMS_PATH_MQTT = "mqtt"
OVMS_PATH_SCRIPT = "script"


def ovms_vehicle_id(hass: HomeAssistant, entity_id: str | None) -> str | None:
    """Vehicle ID of the OVMS integration – preferably the entry that owns ``entity_id``."""
    entries = hass.config_entries.async_entries(OVMS_DOMAIN)
    if not entries:
        return None
    entry = None
    if entity_id:
        registered = er.async_get(hass).async_get(entity_id)
        if registered and registered.config_entry_id:
            owner = hass.config_entries.async_get_entry(registered.config_entry_id)
            if owner and owner.domain == OVMS_DOMAIN:
                entry = owner
    entry = entry or entries[0]
    value = entry.data.get("vehicle_id") or entry.options.get("vehicle_id")
    return str(value) if value else None


class PortError(Exception):
    """A command could not be delivered."""


class HaPorts:
    """Halo switch, Shelly RPC and OVMS commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        charger_switch: str,
        cp_relay: str | None,
        shelly_host: str | None,
        ovms_topic: str | None,
        ovms_script: str | None,
        ovms_entity: str | None = None,
        max_current: str | None = None,
    ) -> None:
        self.hass = hass
        self.charger_switch = charger_switch
        self.max_current = max_current
        self.cp_relay = cp_relay
        self.shelly_host = shelly_host
        self.ovms_topic = ovms_topic
        self.ovms_script = ovms_script
        self.ovms_entity = ovms_entity

    @property
    def current_settable(self) -> bool:
        return bool(self.max_current and self.max_current.startswith("number."))

    @property
    def cp_pulse_available(self) -> bool:
        return bool(self.cp_relay and self.shelly_host)

    @property
    def ovms_path(self) -> str | None:
        """How commands reach the car – found automatically, no setup needed.

        1. the OVMS integration (HACS "OVMS") with its ``ovms.send_command`` service,
        2. an MQTT command topic or 3. a script – both only for special setups.
        """
        if self.hass.services.has_service(OVMS_DOMAIN, "send_command") and \
                ovms_vehicle_id(self.hass, self.ovms_entity):
            return OVMS_PATH_SERVICE
        if self.ovms_topic:
            return OVMS_PATH_MQTT
        if self.ovms_script:
            return OVMS_PATH_SCRIPT
        return None

    @property
    def smart_453(self) -> bool:
        """The smart ED/EQ 453 module publishes its own ``xsq.*`` metrics."""
        registry = er.async_get(self.hass)
        return any("xsq" in entry.entity_id or "xsq" in (entry.unique_id or "")
                   for entry in registry.entities.values() if entry.platform == OVMS_DOMAIN)

    def wakeup_command(self, configured: str) -> str:
        if configured and configured != "auto":
            return configured
        return "xsq wakeup" if self.smart_453 else "wakeup"

    @property
    def ovms_command_available(self) -> bool:
        return self.ovms_path is not None

    async def execute(self, command: Command, settings: Settings) -> None:
        match command.kind:
            case CommandKind.ENABLE_CHARGER:
                await self._switch(self.charger_switch, True)
            case CommandKind.DISABLE_CHARGER:
                await self._switch(self.charger_switch, False)
            case CommandKind.CP_PULSE:
                await self._cp_pulse(int(command.params["seconds"]))
            case CommandKind.CP_CLOSE:
                if self.cp_relay is None:
                    raise PortError("kein CP-Relais konfiguriert")
                await self._switch(self.cp_relay, True)
            case CommandKind.OVMS_WAKEUP:
                await self._ovms(self.wakeup_command(settings.ovms_wakeup_command))
            case CommandKind.CLIMATE_START:
                minutes = int(command.params.get("duration_min", 10))
                text = settings.ovms_climate_command.format(
                    level=homelink_level(minutes), minutes=minutes)
                await self._ovms(text)
            case CommandKind.CLIMATE_STOP:
                await self._ovms(settings.ovms_climate_stop_command)
            case CommandKind.SET_CURRENT:
                await self._set_current(float(command.params["amps"]))
        _LOGGER.info("Ausgeführt: %s", command.describe())

    async def _set_current(self, amps: float) -> None:
        if not self.current_settable:
            raise PortError("kein einstellbarer Ladestrom (number-Entität) konfiguriert")
        state = self.hass.states.get(self.max_current)
        if state is not None:
            # Stay inside what the wallbox accepts (Halo: 6–16 A).
            low, high = state.attributes.get("min"), state.attributes.get("max")
            if low is not None:
                amps = max(float(low), amps)
            if high is not None:
                amps = min(float(high), amps)
        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": self.max_current, "value": amps},
            blocking=True)

    async def _switch(self, entity_id: str, on: bool) -> None:
        await self.hass.services.async_call(
            "homeassistant", SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
            {"entity_id": entity_id}, blocking=True,
        )

    async def _cp_pulse(self, seconds: int) -> None:
        """One RPC call; the Shelly closes the contact again by itself (§3.1).

        ``toggle_after`` is the only place the pulse length is set, so HA
        crashing mid-pulse cannot leave the CP open.
        """
        if not self.shelly_host:
            raise PortError("kein Shelly-Host für den CP-Puls konfiguriert")
        url = f"http://{self.shelly_host}/rpc/Switch.Set"
        params = {"id": "0", "on": "false", "toggle_after": str(seconds)}
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=SHELLY_TIMEOUT_S)
        async with session.get(url, params=params, timeout=timeout) as response:
            if response.status != 200:
                raise PortError(f"Shelly antwortet HTTP {response.status}")

    async def _ovms(self, text: str) -> None:
        """Send an OVMS shell command along the detected path (§2.3, §16 #8)."""
        if not text:
            raise PortError("OVMS-Befehl ist nicht eingetragen")
        path = self.ovms_path
        if path == OVMS_PATH_SERVICE:
            data = {"vehicle_id": ovms_vehicle_id(self.hass, self.ovms_entity), "command": text}
            response = self.hass.services.supports_response(OVMS_DOMAIN, "send_command")
            await self.hass.services.async_call(
                OVMS_DOMAIN, "send_command", data, blocking=True,
                return_response=response is SupportsResponse.ONLY)
        elif path == OVMS_PATH_MQTT:
            await self.hass.services.async_call(
                "mqtt", "publish", {"topic": self.ovms_topic, "payload": text}, blocking=True)
        elif path == OVMS_PATH_SCRIPT:
            await self.hass.services.async_call(
                "script", "turn_on",
                {"entity_id": self.ovms_script, "variables": {"command": text}}, blocking=True)
        else:
            raise PortError("kein Befehlsweg zum Fahrzeug gefunden – OVMS-Integration einrichten")

    async def configure_shelly(self, pulse_s: int) -> dict[str, Any]:
        """Write the §3.1 failsafe settings via ``Switch.SetConfig`` (user action only)."""
        if not self.shelly_host:
            raise PortError("kein Shelly-Host konfiguriert")
        session = async_get_clientsession(self.hass)
        payload = {"id": 0, "method": "Switch.SetConfig",
                   "params": {"id": 0, "config": shelly_expected(pulse_s)}}
        timeout = aiohttp.ClientTimeout(total=SHELLY_TIMEOUT_S)
        async with session.post(f"http://{self.shelly_host}/rpc", json=payload,
                                timeout=timeout) as response:
            if response.status == 401:
                raise PortError("Shelly verlangt ein Passwort – bitte in der Shelly-App "
                                "einstellen: Einschaltzustand an, Auto-On nach "
                                f"{pulse_s} s")
            if response.status != 200:
                raise PortError(f"Shelly antwortet HTTP {response.status}")
            data = await response.json(content_type=None)
            if isinstance(data, dict) and data.get("error"):
                raise PortError(str(data["error"].get("message", data["error"])))
            return data.get("result", {}) if isinstance(data, dict) else {}

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


def shelly_expected(pulse_s: int) -> dict[str, Any]:
    """The failsafe configuration of §3.1: the Shelly closes the CP on its own."""
    return {"initial_state": "on", "auto_on": True, "auto_on_delay": float(pulse_s)}


def shelly_deviations(config: dict[str, Any], pulse_s: int) -> list[dict[str, Any]]:
    """Every setting that differs from §3.1, with actual and expected value."""
    out = []
    for key, expected in shelly_expected(pulse_s).items():
        actual = config.get(key)
        same = (float(actual) == expected) if key == "auto_on_delay" and \
            isinstance(actual, (int, float)) else actual == expected
        if not same:
            out.append({"key": key, "actual": actual, "expected": expected})
    return out


def shelly_config_ok(config: dict[str, Any], pulse_s: int) -> bool:
    """Auto-on and power-on default must back up the pulse (§3.1)."""
    return not shelly_deviations(config, pulse_s)
