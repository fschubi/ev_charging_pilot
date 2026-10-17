"""Function test of the whole start chain: Halo on, wakeup cascade, stable charge, Halo off.

The test runs as a short "charge now" override, so it uses exactly the code
path of a real night: confirmation of the wallbox, waiting for power, OVMS
wakeup, CP pulse as last resort. It only records what happened and ends the
override once the charge is stable (or the cascade gave up).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .model import Event

# Upper bound for the whole cascade (confirm 90 s, wait 60 s, OVMS 45 s, gap to the
# CP pulse 120 s, pulse 10 s + 60 s) with some headroom.
TEST_DURATION = timedelta(minutes=8)
# How long the stable charge keeps running before the test switches off again.
HOLD_AFTER_STABLE = timedelta(seconds=60)
# Waiting for the wallbox to confirm "off" at the end.
STOP_TIMEOUT = timedelta(minutes=3)

STEP_TEXTS = {
    "CHARGER_ENABLE": "Wallbox freigegeben",
    "CHARGER_CONFIRMED": "Wallbox hat die Freigabe bestätigt",
    "WAIT_FOR_CHARGE": "Warte auf Ladeleistung",
    "OVMS_WAKEUP": "Auto per OVMS geweckt",
    "CP_PULSE_START": "CP-Puls über den Shelly",
    "CP_PULSE_DONE": "CP-Leitung wieder geschlossen",
    "POWER_DETECTED": "Ladeleistung erkannt",
    "CHARGE_STABLE": "Ladung stabil",
    "CHARGER_DISABLE": "Wallbox wird gesperrt",
}
def _kw(watts: float) -> str:
    return f"{watts / 1000:.1f} kW".replace(".", ",")


FAIL_CODES = {"CHARGE_START_FAILED", "CHARGER_NOT_CONFIRMED", "CP_NOT_RESTORED"}


@dataclass
class ChargeTest:
    started_at: datetime
    deadline: datetime
    steps: list[dict[str, Any]] = field(default_factory=list)
    woke_by: str | None = None
    stable_at: datetime | None = None
    power_w: float | None = None
    # running → stopping → done
    phase: str = "running"
    ok: bool | None = None
    summary: str | None = None
    finished_at: datetime | None = None
    _stop_since: datetime | None = None

    @classmethod
    def start(cls, now: datetime) -> ChargeTest:
        return cls(started_at=now, deadline=now + TEST_DURATION)

    @property
    def running(self) -> bool:
        return self.phase != "done"

    def _step(self, now: datetime, text: str) -> None:
        self.steps.append({"at": now.isoformat(),
                           "after_s": round((now - self.started_at).total_seconds()),
                           "text": text})

    def observe(self, now: datetime, events: list[Event], power_w: float | None) -> None:
        """Record the executor's events of one tick."""
        for event in events:
            text = STEP_TEXTS.get(event.code)
            if event.code == "POWER_DETECTED" and power_w is not None:
                text = f"Ladeleistung erkannt ({_kw(power_w)})"
            if text:
                self._step(event.timestamp, text)
            if event.code == "OVMS_WAKEUP":
                self.woke_by = "OVMS"
            elif event.code == "CP_PULSE_START":
                self.woke_by = "CP-Puls"
            elif event.code == "CHARGE_STABLE" and self.stable_at is None:
                self.stable_at = event.timestamp
                self.power_w = power_w
            elif event.code in FAIL_CODES and self.phase == "running":
                self.stop(now, False, event.message)

    def due(self, now: datetime) -> tuple[bool, str] | None:
        """(ok, reason) once the running test should end, else None."""
        if self.phase != "running":
            return None
        if self.stable_at is not None and now - self.stable_at >= HOLD_AFTER_STABLE:
            how = f"nach Wecken per {self.woke_by}" if self.woke_by else "ohne Wecken"
            kw = f" mit {_kw(self.power_w)}" if self.power_w else ""
            return True, f"Ladung startete {how}{kw}"
        if now >= self.deadline:
            return False, "Keine stabile Ladung innerhalb der Testzeit"
        return None

    def stop(self, now: datetime, ok: bool, summary: str) -> None:
        self.ok = ok
        self.summary = summary
        self.phase = "stopping"
        self._stop_since = now

    def stopped(self, now: datetime, charger_on: bool | None, kept_on: bool = False) -> bool:
        """True when the wallbox is off again (or we gave up waiting for it).

        ``kept_on``: a plan wants to charge right now – the wallbox rightly stays on.
        """
        if self.phase != "stopping":
            return False
        if kept_on:
            self._step(now, "Wallbox bleibt an – ein Ladeplan ist gerade aktiv")
        elif charger_on is False:
            self._step(now, "Wallbox wieder gesperrt")
        elif now - self._stop_since < STOP_TIMEOUT:
            return False
        else:
            self._step(now, "Wallbox meldet weiterhin „an“")
            self.ok = False
            self.summary = f"{self.summary}; Wallbox ließ sich nicht sperren"
        self.phase = "done"
        self.finished_at = now
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "phase": self.phase,
            "ok": self.ok,
            "summary": self.summary,
            "woke_by": self.woke_by,
            "power_w": self.power_w,
            "steps": self.steps,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
