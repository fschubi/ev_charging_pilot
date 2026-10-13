"""Arbiter: pick the valid wish by fixed priority (§4.2)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

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
    Reason.AUTOMATION_OFF,
)

DEFAULT_OFF = Desired(charger_enabled=False, reason=Reason.DEFAULT_OFF)
SAFETY_LOCK = Desired(charger_enabled=None, reason=Reason.SAFETY_LOCK)
# Automation switched off: plans are ignored and the Halo is left alone.
HANDS_OFF = Desired(charger_enabled=None, reason=Reason.AUTOMATION_OFF)


def _rank(wish: Desired) -> int:
    return PRIORITY.index(wish.reason)


def arbitrate(
    wishes: Iterable[Desired | None], *, safety_lock: bool = False, default: Desired = DEFAULT_OFF
) -> Desired:
    """Return the winning wish; without any wish ``default`` applies.

    A safety lock (health ERROR) does not switch the Halo off – it freezes
    it: ``charger_enabled=None`` means the executor must not touch it.

    The charger decision and the climate request are arbitrated separately:
    a wish without an opinion on the Halo (``charger_enabled=None``) can still
    carry the climate request, so "battery only" climate works while the
    target SOC keeps the Halo off (§9.1).
    """
    if safety_lock:
        return SAFETY_LOCK
    candidates = sorted((w for w in wishes if w is not None), key=_rank)
    charger = next((w for w in candidates if w.charger_enabled is not None), default)
    climate = next((w.climate for w in candidates if w.climate is not None), None)
    if climate is not None and charger.climate is None:
        charger = replace(charger, climate=climate)
    return charger
