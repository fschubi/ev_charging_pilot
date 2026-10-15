"""Ports: the only way the core reaches hardware (§4.3).

The executor never calls a port itself – it returns :class:`Command` objects
and the caller dispatches them. That keeps every step of the executor a pure
function and lets dry-run and replay share the exact same code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class CommandKind(StrEnum):
    ENABLE_CHARGER = "enable_charger"
    DISABLE_CHARGER = "disable_charger"
    OVMS_WAKEUP = "ovms_wakeup"
    CP_PULSE = "cp_pulse"
    CP_CLOSE = "cp_close"
    CLIMATE_START = "climate_start"
    CLIMATE_STOP = "climate_stop"


@dataclass(frozen=True, slots=True)
class Command:
    kind: CommandKind
    params: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        args = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.kind.upper()}({args})" if args else self.kind.upper()


class ChargerPort(Protocol):
    async def set_enabled(self, enabled: bool) -> None: ...


class CpPort(Protocol):
    async def pulse(self, seconds: int) -> None:
        """Open the CP line; the Shelly closes it again by itself (toggle_after)."""

    async def close(self) -> None: ...


class VehiclePort(Protocol):
    async def wakeup(self) -> None: ...

    async def start_climate(self, duration_min: int) -> None: ...


@dataclass(slots=True)
class RecordedCommand:
    at: datetime
    command: Command
    executed: bool


@dataclass(slots=True)
class CommandRecorder:
    """Keeps the last commands for diagnostics; in dry-run it is all that happens."""

    limit: int = 200
    entries: list[RecordedCommand] = field(default_factory=list)

    def record(self, at: datetime, command: Command, executed: bool) -> None:
        self.entries.append(RecordedCommand(at, command, executed))
        del self.entries[: -self.limit]
