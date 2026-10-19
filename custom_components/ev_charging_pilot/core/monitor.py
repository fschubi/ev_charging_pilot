"""Monitor: the persistent record of sessions, trips, external charges (§10.8).

~1,000 entries per year, kept as JSON. Aggregates are always recomputed
from these records, never stored.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .costs import FixedPriceHistory
from .sessions import ChargeSession
from .settings import OdometerSource, Settings
from .statistics import (
    ExternalCharge,
    MonitorData,
    Reading,
    month_summary,
    temperature_statistics,
    year_summary,
)
from .trips import MIN_CONSUMPTION_KM, Trip

SOC_LOG_MIN_GAP = timedelta(hours=1)
KEEP_DAYS = 800


class Monitor:
    def __init__(self, tz: ZoneInfo) -> None:
        self.tz = tz
        self.data = MonitorData([], [], [], [], [], set())
        # Set by the engine: an OVMS odometer is mapped (odometer source "auto").
        self.ovms_odometer = False

    # ------------------------------------------------------------- records

    def add_session(self, session: ChargeSession) -> None:
        self.data.sessions.append(session)

    def add_trip(self, trip: Trip) -> None:
        self.data.trips.append(trip)

    def delete_trip(self, trip_id: str) -> bool:
        before = len(self.data.trips)
        self.data.trips = [t for t in self.data.trips if t.trip_id != trip_id]
        return len(self.data.trips) != before

    def add_external(self, charge: ExternalCharge) -> None:
        self.data.external = [e for e in self.data.external if e.id != charge.id]
        self.data.external.append(charge)
        self.data.external.sort(key=lambda e: e.date)

    def delete_external(self, charge_id: str) -> bool:
        before = len(self.data.external)
        self.data.external = [e for e in self.data.external if e.id != charge_id]
        return len(self.data.external) != before

    def add_odometer(self, at: datetime, km: float) -> None:
        self.data.odometer_readings.append(Reading(at, km))
        self.data.odometer_readings.sort(key=lambda r: r.at)

    def record_soc(self, at: datetime, soc: float) -> bool:
        log = self.data.soc_log
        if log and at - log[-1].at < SOC_LOG_MIN_GAP and \
                at.astimezone(self.tz).date() == log[-1].at.astimezone(self.tz).date():
            log[-1] = Reading(at, soc)
            return False
        log.append(Reading(at, soc))
        return True

    def record_day(self, day: date) -> bool:
        if day in self.data.days_seen:
            return False
        self.data.days_seen.add(day)
        return True

    def last_session(self) -> ChargeSession | None:
        return self.data.sessions[-1] if self.data.sessions else None

    def prune(self, today: date) -> None:
        cutoff = today - timedelta(days=KEEP_DAYS)
        self.data.soc_log = [r for r in self.data.soc_log
                             if r.at.astimezone(self.tz).date() >= cutoff]
        self.data.days_seen = {d for d in self.data.days_seen if d >= cutoff}

    # --------------------------------------------------------- statistics

    def _kwargs(self, settings: Settings, today: date | None) -> dict[str, Any]:
        return {
            "prices": FixedPriceHistory(settings.price_history, self.tz),
            "capacity_kwh": settings.usable_capacity_kwh,
            "efficiency": settings.charge_efficiency,
            "odometer_source": "ovms" if self.odometer_from_ovms(settings) else "manual",
            "today": today,
        }

    def odometer_from_ovms(self, settings: Settings) -> bool:
        source = settings.odometer_source
        return source is OdometerSource.OVMS or (
            source is OdometerSource.AUTO and self.ovms_odometer)

    def month(self, year: int, month: int, settings: Settings,
              today: date | None = None) -> dict[str, Any]:
        return month_summary(self.data, year, month, self.tz, **self._kwargs(settings, today))

    def year(self, year: int, settings: Settings, today: date | None = None) -> dict[str, Any]:
        return year_summary(self.data, year, self.tz, **self._kwargs(settings, today))

    def week(self, now: datetime) -> dict[str, Any]:
        """The last seven days for the Sunday push."""
        since = now - timedelta(days=7)
        sessions = [s for s in self.data.sessions if s.started_at >= since]
        # Energy counts whether the session ended well or was interrupted (as in the month).
        home = [s for s in sessions if s.grid_energy_kwh]
        trips = [t for t in self.data.trips if t.started_at >= since and t.distance_km]
        external = [e for e in self.data.external
                    if e.date >= since.astimezone(self.tz).date()]
        return {
            "home_kwh": round(sum(s.grid_energy_kwh for s in home), 1),
            "cost_eur": round(sum(s.cost_eur for s in home), 2),
            "charges": sum(1 for s in sessions if s.success),
            "failed": sum(1 for s in sessions if not s.success),
            "wakeups": sum(int(s.ovms_wakeup_used) + int(s.cp_wakeup_used) for s in sessions),
            "external_kwh": round(sum(e.energy_kwh for e in external), 1),
            "km": round(sum(t.distance_km for t in trips)) if trips else None,
        }

    def temperatures(self, settings: Settings, year: int | None = None) -> dict[str, Any]:
        trips = [t for t in self.data.trips
                 if year is None or t.started_at.astimezone(self.tz).year == year]
        measured = [s for s in self.data.sessions if s.success and s.vehicle_charge_energy_kwh]
        grid = sum(s.grid_energy_kwh for s in measured)
        loss_pct = (grid - sum(s.vehicle_charge_energy_kwh for s in measured)) / grid * 100 \
            if grid else None
        if loss_pct is not None and not 0 <= loss_pct <= 40:
            loss_pct = None  # measuring artefact (see statistics.MAX_PLAUSIBLE_LOSS_PCT)
        return temperature_statistics(trips, loss_pct=loss_pct,
                                      price_eur_kwh=self.home_price(settings))

    def home_price(self, settings: Settings) -> float:
        """What home charging really cost (dynamic tariff included); fixed price otherwise."""
        home = [s for s in self.data.sessions if s.success and s.grid_energy_kwh]
        home_kwh = sum(s.grid_energy_kwh for s in home)
        return sum(s.cost_eur for s in home) / home_kwh if home_kwh >= 1 \
            else settings.price_history[-1].eur_per_kwh

    # -------------------------------------------------------------- storage

    def as_dict(self) -> dict[str, Any]:
        d = self.data
        return {
            "sessions": [s.as_dict() for s in d.sessions],
            "trips": [t.as_dict() for t in d.trips],
            "external": [e.as_dict() for e in d.external],
            "odometer_readings": [[r.at.isoformat(), r.value] for r in d.odometer_readings],
            "soc_log": [[r.at.isoformat(), r.value] for r in d.soc_log],
            "days_seen": sorted(day.isoformat() for day in d.days_seen),
        }

    def restore(self, raw: dict[str, Any]) -> None:
        def readings(items):
            return [Reading(datetime.fromisoformat(a), float(v)) for a, v in items or []]

        self.data = MonitorData(
            sessions=[ChargeSession.from_dict(s) for s in raw.get("sessions") or []],
            trips=[Trip.from_dict(t) for t in raw.get("trips") or []],
            external=[ExternalCharge.from_dict(e) for e in raw.get("external") or []],
            odometer_readings=readings(raw.get("odometer_readings")),
            soc_log=readings(raw.get("soc_log")),
            days_seen={date.fromisoformat(d) for d in raw.get("days_seen") or []},
        )
        _repair_sessions(self.data.sessions)
        _repair_trips(self.data.trips)


def _repair_sessions(sessions: list[ChargeSession]) -> None:
    """Fix records of v0.22.3 and older (field 19.10.2026).

    A session started after another one ended reused its ID, and the climate
    share came from the Halo power, which overstates single-phase loads. IDs
    must be unique for the detail view; the climate can never exceed the grid.
    """
    seen: set[str] = set()
    for session in sessions:
        if session.session_id in seen:
            session.session_id = f"{session.session_id}-{session.started_at:%H%M%S}"
        seen.add(session.session_id)
        if session.climate_energy_kwh is not None \
                and session.climate_energy_kwh > session.grid_energy_kwh:
            ratio = session.grid_energy_kwh / session.climate_energy_kwh \
                if session.climate_energy_kwh else 0.0
            session.climate_energy_kwh = round(session.grid_energy_kwh, 4)
            if session.climate_cost_eur is not None:
                session.climate_cost_eur = round(session.climate_cost_eur * ratio, 4)


def _repair_trips(trips: list[Trip]) -> None:
    """Trips stored before the 1-km rule kept absurd kWh/100 km (138 for 60 m)."""
    for trip in trips:
        if trip.consumption_kwh_100km is not None and trip.distance_km is not None \
                and trip.distance_km < MIN_CONSUMPTION_KM:
            trip.consumption_kwh_100km = None
