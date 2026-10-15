"""Charge sessions (§10.4): grid energy in 15-min intervals, cost, wakeups used.

The tracker listens to executor events and the Halo energy counter. A CP
pulse never ends a session (the executor masks it, §3.4), so the tracker
only reacts to explicit session events.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .costs import EnergyInterval, FixedPriceHistory, IntervalAccumulator
from .model import Event, Quality, Reason, Severity, Value

FAILURE_CODES = ("CHARGE_START_FAILED", "CHARGER_NOT_CONFIRMED", "CHARGE_INTERRUPTED")


@dataclass(slots=True)
class ChargeSession:
    session_id: str
    started_at: datetime
    reason: str
    source: str = "home_halo"
    ended_at: datetime | None = None
    start_total_energy_kwh: float | None = None
    end_total_energy_kwh: float | None = None
    grid_energy_kwh: float = 0.0
    start_soc_pct: float | None = None
    end_soc_pct: float | None = None
    vehicle_charge_energy_kwh: float | None = None
    max_power_w: float = 0.0
    average_power_w: float | None = None
    ovms_wakeup_used: bool = False
    cp_wakeup_used: bool = False
    cost_eur: float = 0.0
    success: bool = True
    failure_code: str | None = None
    energy_intervals: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChargeSession:
        values = dict(data)
        values["started_at"] = datetime.fromisoformat(values["started_at"])
        values["ended_at"] = (
            datetime.fromisoformat(values["ended_at"]) if values.get("ended_at") else None
        )
        return cls(**values)


def _intervals_to_dicts(intervals: list[EnergyInterval]) -> list[dict[str, Any]]:
    return [
        {"start": i.start.isoformat(), "end": i.end.isoformat(), "kwh": round(i.kwh, 4)}
        for i in intervals
    ]


def _intervals_from_dicts(items: list[dict[str, Any]]) -> list[EnergyInterval]:
    return [
        EnergyInterval(datetime.fromisoformat(i["start"]), datetime.fromisoformat(i["end"]),
                       float(i["kwh"]))
        for i in items
    ]


class SessionTracker:
    def __init__(self, interval_min: int = 15) -> None:
        self.interval_min = interval_min
        self.open: ChargeSession | None = None
        self._acc = IntervalAccumulator(interval_min)
        self._pending_ovms = False
        self._pending_cp = False
        self._vehicle_last: tuple[datetime, float] | None = None
        self._dynamic: Callable[[datetime], float | None] | None = None

    # ----------------------------------------------------------------- API

    def update(
        self,
        now: datetime,
        events: list[Event],
        *,
        total_energy: Value,
        power: Value,
        vehicle_power: Value,
        soc: Value | None,
        reason: Reason | str | None,
        prices: FixedPriceHistory,
        dynamic_price: Callable[[datetime], float | None] | None = None,
    ) -> list[ChargeSession]:
        self._dynamic = dynamic_price
        closed: list[ChargeSession] = []
        for event in events:
            closed += self._on_event(now, event, total_energy, soc, reason, prices)
        if self.open is not None:
            self._accumulate(now, total_energy, power, vehicle_power, soc)
        return closed

    def as_dict(self) -> dict[str, Any]:
        return {
            "open": self.open.as_dict() if self.open else None,
            "intervals": _intervals_to_dicts(self._acc.intervals),
            "last_kwh": self._acc.last_kwh,
            "pending_ovms": self._pending_ovms,
            "pending_cp": self._pending_cp,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.open = ChargeSession.from_dict(data["open"]) if data.get("open") else None
        self._acc = IntervalAccumulator(self.interval_min)
        self._acc.intervals = _intervals_from_dicts(data.get("intervals") or [])
        self._acc.last_kwh = data.get("last_kwh")
        self._pending_ovms = bool(data.get("pending_ovms"))
        self._pending_cp = bool(data.get("pending_cp"))

    @property
    def session_energy_kwh(self) -> float | None:
        return self._acc.total_kwh if self.open else None

    # ------------------------------------------------------------- internal

    def _on_event(self, now, event, total_energy, soc, reason, prices) -> list[ChargeSession]:
        code = event.code
        if code == "OVMS_WAKEUP":
            self._pending_ovms = True
        elif code == "CP_PULSE_START":
            self._pending_cp = True
        elif code in ("CHARGE_STABLE", "CHARGE_RESUMED") and self.open is None:
            self._start(now, event.session_id, total_energy, soc, reason)
        elif code == "SESSION_END" or (code == "CABLE_DISCONNECTED" and self.open):
            if self.open is not None:
                return [self._close(now, total_energy, soc, prices, True, None)]
        elif code in FAILURE_CODES and event.severity is Severity.ERROR:
            if self.open is not None:
                return [self._close(now, total_energy, soc, prices, False, code)]
            failed = ChargeSession(
                session_id=f"f-{now.strftime('%Y%m%d-%H%M%S')}",
                started_at=now, ended_at=now, reason=str(reason or ""),
                ovms_wakeup_used=self._pending_ovms, cp_wakeup_used=self._pending_cp,
                success=False, failure_code=code,
            )
            self._pending_ovms = self._pending_cp = False
            return [failed]
        return []

    def _start(self, now, session_id, total_energy, soc, reason) -> None:
        start_kwh = float(total_energy.normalized) if total_energy.available else None
        self.open = ChargeSession(
            session_id=session_id or f"s-{now.strftime('%Y%m%d-%H%M%S')}",
            started_at=now,
            reason=str(reason or ""),
            start_total_energy_kwh=start_kwh,
            start_soc_pct=_soc(soc),
            ovms_wakeup_used=self._pending_ovms,
            cp_wakeup_used=self._pending_cp,
        )
        self._pending_ovms = self._pending_cp = False
        self._acc = IntervalAccumulator(self.interval_min)
        if start_kwh is not None:
            self._acc.add(now, start_kwh)
        self._vehicle_last = None

    def _accumulate(self, now, total_energy, power, vehicle_power, soc) -> None:
        session = self.open
        if total_energy.available and total_energy.normalized is not None:
            self._acc.add(now, float(total_energy.normalized))
            if session.start_total_energy_kwh is None:
                session.start_total_energy_kwh = float(total_energy.normalized)
        if power.available and power.normalized is not None:
            session.max_power_w = max(session.max_power_w, float(power.normalized))
        if vehicle_power.quality is Quality.GOOD and vehicle_power.normalized is not None:
            watts = float(vehicle_power.normalized)
            stamp = vehicle_power.updated_at or now
            if self._vehicle_last is not None and stamp > self._vehicle_last[0]:
                hours = (stamp - self._vehicle_last[0]).total_seconds() / 3600
                kwh = (watts + self._vehicle_last[1]) / 2 / 1000 * hours
                session.vehicle_charge_energy_kwh = round(
                    (session.vehicle_charge_energy_kwh or 0.0) + kwh, 4)
            if self._vehicle_last is None or stamp > self._vehicle_last[0]:
                self._vehicle_last = (stamp, watts)
        current = _soc(soc)
        if current is not None:
            session.end_soc_pct = current
            if session.start_soc_pct is None:
                session.start_soc_pct = current

    def _close(self, now, total_energy, soc, prices, success, failure) -> ChargeSession:
        self._accumulate(now, total_energy, Value.unavailable("halo"), Value.unavailable("ovms"),
                         soc)
        session = self.open
        session.ended_at = now
        session.success = success
        session.failure_code = failure
        if total_energy.available and total_energy.normalized is not None:
            session.end_total_energy_kwh = float(total_energy.normalized)
        if session.start_total_energy_kwh is not None and session.end_total_energy_kwh is not None:
            session.grid_energy_kwh = round(
                max(0.0, session.end_total_energy_kwh - session.start_total_energy_kwh), 4)
        else:
            session.grid_energy_kwh = self._acc.total_kwh
        hours = (session.ended_at - session.started_at).total_seconds() / 3600
        if hours > 0:
            session.average_power_w = round(session.grid_energy_kwh / hours * 1000, 1)
        # Each interval keeps the price it was charged at: a dynamic tariff
        # (Tibber) is exact, a fixed price comes from the validity history.
        items = _intervals_to_dicts(self._acc.intervals)
        for item, interval in zip(items, self._acc.intervals, strict=True):
            price = self._dynamic(interval.start) if self._dynamic else None
            item["eur_per_kwh"] = round(price if price is not None
                                        else prices.price_at(interval.start), 5)
        session.energy_intervals = items
        session.cost_eur = round(sum(i["kwh"] * i["eur_per_kwh"] for i in items), 4)
        self.open = None
        self._acc = IntervalAccumulator(self.interval_min)
        return session


def _soc(soc: Value | None) -> float | None:
    if soc is None or not soc.quality.usable_for_planning or soc.normalized is None:
        return None
    return float(soc.normalized)
