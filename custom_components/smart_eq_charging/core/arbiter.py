"""Arbiter: pick the valid wish by fixed priority (§4.2)."""

from __future__ import annotations

from collections.abc import Iterable

from .model import Desired, Reason

# Highest first. RFID and a manual override share one rank – both are
# explicit user actions; whichever was set last replaces the other upstream.
PRIORITY: tuple[Reason, ...] = (
    Reason.SAFETY_LOCK,
    Reason.OVERRIDE,
    Reason.RFID,
    Reason.ONE_SHOT,
    Reason.TARGET_SOC_REACHED,
    Reason.CLIMATE,
    Reason.SCHEDULE,
    Reason.DEFAULT_OFF,
)

DEFAULT_OFF = Desired(charger_enabled=False, reason=Reason.DEFAULT_OFF)
SAFETY_LOCK = Desired(charger_enabled=None, reason=Reason.SAFETY_LOCK)


def arbitrate(wishes: Iterable[Desired | None], *, safety_lock: bool = False) -> Desired:
    """Return the winning wish; without any wish the Halo stays off.

    A safety lock (health ERROR) does not switch the Halo off – it freezes
    it: ``charger_enabled=None`` means the executor must not touch it.
    """
    if safety_lock:
        return SAFETY_LOCK
    candidates = [w for w in wishes if w is not None]
    if not candidates:
        return DEFAULT_OFF
    return min(candidates, key=lambda w: PRIORITY.index(w.reason))
