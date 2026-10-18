"""Charge sessions (§10.4): grid energy in 15-min intervals, cost, wakeups used.

The tracker listens to executor events and the Halo energy counter. A CP
pulse never ends a session (the executor masks it, §3.4), so the tracker
only reacts to explicit session events.

The Halo counter arrives by cloud polling (~30 s, measured 18.10.2026), so it
lags behind the switching: energy flows before CHARGE_STABLE and the last
readings arrive after SESSION_END. The tracker therefore starts from the
counter reading at CHARGER_ENABLE and keeps a closed session open for
``TAIL_S`` to collect the late readings before handing it out.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .costs import EnergyInterval, FixedPriceHistory, IntervalAccumulator
from .model import Event, Quality, Reason, Severity, Value

FAILURE_CODES = ("CHARGE_START_FAILED", "CHARGER_NOT_CONFIRMED", "CHARGE_INTERRUPTED")
# Two Halo poll intervals: the field showed late counter readings 1 s and 31 s
# after the wallbox was switched off.
TAIL_S = 65
# Power curve for the session detail view: one sample per minute, at most a day.
TRACE_STEP_S = 60
TRACE_MAX = 1440


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
    # [seconds since start, Halo W, vehicle W, SOC %] – None where unknown.
    trace: list[list[float | None]] = field(default_factory=list)

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
        self._trace_at: datetime | None = None
        self._dynamic: Callable[[datetime], float | None] | None = None
        # Counter reading when the wallbox was enabled (session baseline).
        self._enable_kwh: tuple[datetime, float] | None = None
        # Session already ended, waiting for late counter readings:
        # (ended_at, success, failure_code).
        self._closing: tuple[datetime, bool, str | None] | None = None

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
        if self.open is not None and self._closing is not None:
            self._acc_energy(now, total_energy)
            if now - self._closing[0] >= timedelta(seconds=TAIL_S):
                closed.append(self._finish(total_energy, prices))
        elif self.open is not None:
            self._accumulate(now, total_energy, power, vehicle_power, soc)
        return closed

    def as_dict(self) -> dict[str, Any]:
        return {
            "open": self.open.as_dict() if self.open else None,
            "intervals": _intervals_to_dicts(self._acc.intervals),
            "last_kwh": self._acc.last_kwh,
            "pending_ovms": self._pending_ovms,
            "pending_cp": self._pending_cp,
            "enable_kwh": ([self._enable_kwh[0].isoformat(), self._enable_kwh[1]]
                           if self._enable_kwh else None),
            "closing": ([self._closing[0].isoformat(), self._closing[1], self._closing[2]]
                        if self._closing else None),
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.open = ChargeSession.from_dict(data["open"]) if data.get("open") else None
        self._acc = IntervalAccumulator(self.interval_min)
        self._acc.intervals = _intervals_from_dicts(data.get("intervals") or [])
        self._acc.last_kwh = data.get("last_kwh")
        self._pending_ovms = bool(data.get("pending_ovms"))
        self._pending_cp = bool(data.get("pending_cp"))
        enable = data.get("enable_kwh")
        self._enable_kwh = (datetime.fromisoformat(enable[0]), float(enable[1])) \
            if enable else None
        closing = data.get("closing")
        self._closing = (datetime.fromisoformat(closing[0]), bool(closing[1]), closing[2]) \
            if closing and self.open is not None else None

    @property
    def session_energy_kwh(self) -> float | None:
        return self._acc.total_kwh if self.open else None

    @property
    def closing(self) -> bool:
        """The session has ended and only waits for late counter readings."""
        return self._closing is not None

    # ------------------------------------------------------------- internal

    def _on_event(self, now, event, total_energy, soc, reason, prices) -> list[ChargeSession]:
        code = event.code
        closed: list[ChargeSession] = []
        if self._closing is not None and (
                code in ("CHARGE_STABLE", "CHARGE_RESUMED", "CHARGER_ENABLE")
                or code in FAILURE_CODES):
            # Something new begins: hand out the ending session as it is.
            closed.append(self._finish(total_energy, prices))
        return closed + self._handle(now, event, total_energy, soc, reason, prices)

    def _handle(self, now, event, total_energy, soc, reason, prices) -> list[ChargeSession]:
        code = event.code
        if code == "CHARGER_ENABLE":
            if self.open is None and total_energy.available \
                    and total_energy.normalized is not None:
                self._enable_kwh = (now, float(total_energy.normalized))
        elif code == "CHARGER_DISABLE":
            self._enable_kwh = None
        elif code == "OVMS_WAKEUP":
            self._pending_ovms = True
        elif code == "CP_PULSE_START":
            self._pending_cp = True
        elif code in ("CHARGE_STABLE", "CHARGE_RESUMED") and self.open is None:
            self._start(now, event.session_id, total_energy, soc, reason)
        elif code in ("SESSION_END", "CHARGE_ENDED") or (code == "CABLE_DISCONNECTED"
                                                          and self.open):
            if self.open is not None and self._closing is None:
                self._begin_close(now, total_energy, soc, True, None)
        elif code in FAILURE_CODES and event.severity is Severity.ERROR:
            self._enable_kwh = None
            if self.open is not None:
                self._begin_close(now, total_energy, soc, False, code)
                return []
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
        baseline = self._enable_kwh
        self._enable_kwh = None
        if baseline is not None and start_kwh is not None and baseline[1] <= start_kwh:
            # Energy already flowed between the enable and the stable start.
            start_kwh = baseline[1]
        else:
            baseline = None
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
            self._acc.add(baseline[0] if baseline else now, start_kwh)
        if baseline is not None:
            self._acc.add(now, float(total_energy.normalized))
        self._vehicle_last = None
        self._trace_at = None

    def _acc_energy(self, now, total_energy) -> None:
        session = self.open
        if total_energy.available and total_energy.normalized is not None:
            self._acc.add(now, float(total_energy.normalized))
            if session.start_total_energy_kwh is None:
                session.start_total_energy_kwh = float(total_energy.normalized)

    def _accumulate(self, now, total_energy, power, vehicle_power, soc) -> None:
        session = self.open
        self._acc_energy(now, total_energy)
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
        self._sample(now, power, vehicle_power, current)

    def _sample(self, now, power, vehicle_power, soc_pct) -> None:
        """Append one point of the power curve per ``TRACE_STEP_S``."""
        session = self.open
        if len(session.trace) >= TRACE_MAX or (
                self._trace_at is not None
                and (now - self._trace_at).total_seconds() < TRACE_STEP_S):
            return
        self._trace_at = now
        halo = round(float(power.normalized)) \
            if power.available and power.normalized is not None else None
        vehicle = round(float(vehicle_power.normalized)) \
            if vehicle_power.quality is Quality.GOOD and vehicle_power.normalized is not None \
            else None
        offset = max(0, round((now - session.started_at).total_seconds()))
        session.trace.append([offset, halo, vehicle,
                              round(soc_pct, 1) if soc_pct is not None else None])

    def _begin_close(self, now, total_energy, soc, success, failure) -> None:
        self._accumulate(now, total_energy, Value.unavailable("halo"), Value.unavailable("ovms"),
                         soc)
        self._closing = (now, success, failure)

    def _finish(self, total_energy, prices) -> ChargeSession:
        ended_at, success, failure = self._closing
        self._closing = None
        session = self.open
        session.ended_at = ended_at
        session.success = success
        session.failure_code = failure
        if self._acc.last_kwh is not None and session.start_total_energy_kwh is not None:
            session.end_total_energy_kwh = self._acc.last_kwh
        elif total_energy.available and total_energy.normalized is not None:
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
