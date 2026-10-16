"""Learn the real charging behaviour from the car's own sessions (review stage 3).

The planner starts with nominal values (capacity, efficiency, the smaller of
wallbox and on-board charger). Real nights differ: the grid energy per SOC
percent includes losses, and the charging power is often a little lower than
the nameplate. Both are measured on every finished home session and replace
the nominal values once enough sessions agree. The car is never woken for this –
only data that arrives anyway is used.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median
from typing import Any

from .sessions import ChargeSession

MIN_SESSIONS = 3
LAST_SESSIONS = 15
MIN_SOC_DELTA_PCT = 10
# A learned value outside this band around the nominal one is a measurement
# error (e.g. a wrong SOC jump), not a property of the car.
PLAUSIBLE_BAND = (0.6, 1.5)
# The power is bounded physically instead: the on-board charger may be bigger than
# configured (smart 453 with 22 kW), but nothing charges faster than the wallbox.
MIN_POWER_KW = 1.0
INTERVAL_H = 0.25


@dataclass(frozen=True, slots=True)
class LearnedCharging:
    grid_kwh_per_pct: float | None = None
    power_kw: float | None = None
    sessions: int = 0

    @property
    def active(self) -> bool:
        return self.sessions >= MIN_SESSIONS

    def as_dict(self) -> dict[str, Any]:
        return {"grid_kwh_per_pct": self.grid_kwh_per_pct, "power_kw": self.power_kw,
                "sessions": self.sessions, "active": self.active}


def _session_power_kw(session: ChargeSession) -> float | None:
    """Typical power of the full 15-min intervals (the first and last are partial)."""
    items = session.energy_intervals[1:-1]
    powers = [float(i["kwh"]) / INTERVAL_H for i in items if float(i.get("kwh", 0)) > 0]
    if not powers:
        return None
    top = [p for p in powers if p >= max(powers) * 0.5]
    return median(top)


def learn(sessions: Iterable[ChargeSession], *, nominal_kwh_per_pct: float,
          max_power_kw: float) -> LearnedCharging:
    per_pct: list[float] = []
    power: list[float] = []
    used = 0
    for session in list(sessions)[-LAST_SESSIONS:]:
        if not session.success or session.source != "home_halo":
            continue
        counted = False
        start, end = session.start_soc_pct, session.end_soc_pct
        if start is not None and end is not None and end - start >= MIN_SOC_DELTA_PCT \
                and session.grid_energy_kwh > 0:
            value = session.grid_energy_kwh / (end - start)
            if PLAUSIBLE_BAND[0] <= value / nominal_kwh_per_pct <= PLAUSIBLE_BAND[1]:
                per_pct.append(value)
                counted = True
        kw = _session_power_kw(session)
        if kw is not None and MIN_POWER_KW <= kw <= max_power_kw * 1.1:
            power.append(kw)
            counted = True
        used += counted
    return LearnedCharging(
        grid_kwh_per_pct=round(median(per_pct), 4) if len(per_pct) >= MIN_SESSIONS else None,
        power_kw=round(median(power), 2) if len(power) >= MIN_SESSIONS else None,
        sessions=used,
    )
