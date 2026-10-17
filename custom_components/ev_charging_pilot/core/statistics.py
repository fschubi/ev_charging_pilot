"""Drive & Energy statistics (§10.5–§10.7).

Everything is recomputed from the stored sessions, trips, external charges,
odometer readings and SOC log – aggregates are never the source of truth
(§10.8). Values that rest on a missing ΔSOC are flagged ESTIMATED.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .costs import FixedPriceHistory
from .sessions import ChargeSession
from .trips import Trip, net_energy

TEMPERATURE_BANDS: tuple[tuple[str, float | None, float | None], ...] = (
    ("<0", None, 0.0),
    ("0-5", 0.0, 5.0),
    ("5-10", 5.0, 10.0),
    ("10-15", 10.0, 15.0),
    ("15-20", 15.0, 20.0),
    (">=20", 20.0, None),
)
SEASONS = ("winter", "spring", "summer", "autumn")


@dataclass(slots=True)
class ExternalCharge:
    """A charge away from home – always entered manually (§10.5)."""

    id: str
    date: date
    source: str
    energy_kwh: float
    cost_eur: float | None = None
    price_eur_kwh: float | None = None
    odometer_km: float | None = None
    soc_before: float | None = None
    soc_after: float | None = None
    provider: str | None = None
    note: str | None = None
    # Automatically detected (§10.5 "später"): energy is an estimate until edited.
    detected: bool = False
    quality: str = "GOOD"

    @property
    def total_cost(self) -> float:
        if self.cost_eur is not None:
            return self.cost_eur
        if self.price_eur_kwh is not None:
            return round(self.energy_kwh * self.price_eur_kwh, 2)
        return 0.0

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExternalCharge:
        values = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        values["date"] = date.fromisoformat(str(values["date"]))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class Reading:
    at: datetime
    value: float


@dataclass(slots=True)
class MonitorData:
    sessions: list[ChargeSession]
    trips: list[Trip]
    external: list[ExternalCharge]
    odometer_readings: list[Reading]
    soc_log: list[Reading]
    days_seen: set[date]


def _month_bounds(year: int, month: int, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(date(year, month, 1), time(0), tzinfo=tz)
    last = calendar.monthrange(year, month)[1]
    end = datetime.combine(date(year, month, last) + timedelta(days=1), time(0), tzinfo=tz)
    return start, end


def _value_at(readings: Sequence[Reading], moment: datetime) -> float | None:
    """Last reading at or before ``moment``."""
    best = None
    for reading in readings:
        if reading.at <= moment and (best is None or reading.at >= best.at):
            best = reading
    return best.value if best else None


def _home_energy(sessions: Iterable[ChargeSession], start: datetime, end: datetime,
                 prices: FixedPriceHistory) -> tuple[float, float]:
    """Home kWh and cost inside [start, end), split exactly by energy interval."""
    kwh = cost = 0.0
    for session in sessions:
        for interval in session.energy_intervals:
            moment = datetime.fromisoformat(interval["start"])
            if start <= moment < end:
                kwh += float(interval["kwh"])
                # A dynamic tariff stores the real price with each interval.
                price = interval.get("eur_per_kwh")
                cost += float(interval["kwh"]) * (
                    float(price) if price is not None else prices.price_at(moment))
        if not session.energy_intervals and session.grid_energy_kwh and start <= \
                session.started_at < end:
            kwh += session.grid_energy_kwh
            cost += session.cost_eur
    return round(kwh, 3), round(cost, 2)


def _distance(data: MonitorData, trips: list[Trip], start: datetime, end: datetime,
              odometer_source: str) -> tuple[float | None, bool]:
    """Distance in the period and whether it is exact (not estimated)."""
    if odometer_source == "ovms" and trips:
        return round(sum(t.distance_km or 0 for t in trips), 1), all(
            t.quality == "GOOD" for t in trips)
    readings = sorted(data.odometer_readings, key=lambda r: r.at)
    at_start = _value_at(readings, start)
    at_end = _value_at(readings, end)
    inside = [r for r in readings if start <= r.at < end]
    if at_end is None:
        return None, False
    if at_start is None:
        if not inside:
            return None, False
        return round(at_end - inside[0].value, 1), False
    return round(at_end - at_start, 1), True


def period_summary(
    data: MonitorData,
    start: datetime,
    end: datetime,
    *,
    prices: FixedPriceHistory,
    capacity_kwh: float,
    efficiency: float,
    odometer_source: str,
    today: date | None = None,
) -> dict[str, Any]:
    """Balance of one period with SOC correction (§10.6)."""
    home_kwh, home_cost = _home_energy(data.sessions, start, end, prices)
    external = [e for e in data.external if start.date() <= e.date < end.date()]
    external_kwh = round(sum(e.energy_kwh for e in external), 3)
    external_cost = round(sum(e.total_cost for e in external), 2)
    trips = [t for t in data.trips if start <= t.started_at < end]
    sessions = [s for s in data.sessions if start <= s.started_at < end]
    successful = [s for s in sessions if s.success]
    distance, distance_exact = _distance(data, trips, start, end, odometer_source)

    used = sum(t.vehicle_energy_used_kwh or 0 for t in trips) if trips else None
    recd = sum(t.recovered_energy_kwh or 0 for t in trips) if trips else None
    aux = sum(t.auxiliary_energy_kwh or 0 for t in trips) if trips else None

    soc_start = _value_at(data.soc_log, start)
    soc_end = _value_at(data.soc_log, end)
    delta_soc = (soc_end - soc_start) / 100 if soc_start is not None and soc_end is not None \
        else None

    measured = [s for s in successful if s.vehicle_charge_energy_kwh]
    vehicle_charged = round(sum(s.vehicle_charge_energy_kwh for s in measured), 3) \
        if measured else None
    grid_of_measured = sum(s.grid_energy_kwh for s in measured)
    loss_kwh = round(grid_of_measured - vehicle_charged, 3) if measured else None
    loss_pct = round(loss_kwh / grid_of_measured * 100, 1) \
        if measured and grid_of_measured > 0 else None

    grid_documented = round(home_kwh + external_kwh, 3)
    soc_term = (delta_soc or 0.0) * capacity_kwh
    battery_net = round(vehicle_charged - soc_term, 3) if vehicle_charged is not None else None
    grid_per_100 = None
    if distance:
        grid_per_100 = round((grid_documented - soc_term / efficiency) / distance * 100, 2)
    cost_total = round(home_cost + external_cost, 2)

    weighted = [(t.outside_temp_avg_c, t.distance_km or 0) for t in trips
                if t.outside_temp_avg_c is not None]
    total_weight = sum(w for _, w in weighted)
    avg_temp = round(sum(c * w for c, w in weighted) / total_weight, 1) if total_weight else (
        round(sum(c for c, _ in weighted) / len(weighted), 1) if weighted else None)

    first_day = start.date()
    last_day = min((end - timedelta(seconds=1)).date(), today or end.date())
    days = [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]
    complete = bool(days) and all(d in data.days_seen for d in days)

    estimated = delta_soc is None or not distance_exact
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "distance_km": distance,
        "home_energy_kwh": home_kwh,
        "external_energy_kwh": external_kwh,
        "documented_grid_energy_kwh": grid_documented,
        "vehicle_energy_used_kwh": round(used, 3) if used is not None else None,
        "recovered_energy_kwh": round(recd, 3) if recd is not None else None,
        "auxiliary_energy_kwh": round(aux, 3) if aux is not None else None,
        "vehicle_charged_kwh": vehicle_charged,
        "battery_net_kwh": battery_net,
        "delta_soc_pct": round(delta_soc * 100, 1) if delta_soc is not None else None,
        "charging_loss_kwh": loss_kwh,
        "charging_loss_pct": loss_pct,
        "grid_consumption_kwh_100km": grid_per_100,
        "home_cost_eur": home_cost,
        "external_cost_eur": external_cost,
        "cost_eur": cost_total,
        "cost_per_100km_eur": round(cost_total / distance * 100, 2) if distance else None,
        "sessions": len(successful),
        "failed_sessions": len(sessions) - len(successful),
        "trips": len(trips),
        "outside_temp_avg_c": avg_temp,
        "complete": complete,
        "quality": "ESTIMATED" if estimated else "GOOD",
    }


def month_summary(data: MonitorData, year: int, month: int, tz: ZoneInfo,
                  **kwargs: Any) -> dict[str, Any]:
    start, end = _month_bounds(year, month, tz)
    return {"year": year, "month": month, **period_summary(data, start, end, **kwargs)}


def year_summary(data: MonitorData, year: int, tz: ZoneInfo, **kwargs: Any) -> dict[str, Any]:
    start = datetime.combine(date(year, 1, 1), time(0), tzinfo=tz)
    end = datetime.combine(date(year + 1, 1, 1), time(0), tzinfo=tz)
    months = [month_summary(data, year, m, tz, **kwargs) for m in range(1, 13)]
    return {"year": year, **period_summary(data, start, end, **kwargs), "months": months}


def _band(temp: float) -> str:
    for name, low, high in TEMPERATURE_BANDS:
        if (low is None or temp >= low) and (high is None or temp < high):
            return name
    return TEMPERATURE_BANDS[-1][0]


def temperature_statistics(
    trips: Iterable[Trip], *, loss_pct: float | None, price_eur_kwh: float
) -> dict[str, Any]:
    """Per temperature band and season: km, consumption, recuperation, cost (§10.7).

    Grid energy per group is derived from vehicle energy and the measured
    charging loss, so it is always ESTIMATED.
    """
    loss = (loss_pct or 0.0) / 100

    def empty() -> dict[str, float]:
        return {"distance_km": 0.0, "vehicle_kwh": 0.0, "used_kwh": 0.0, "recovered_kwh": 0.0,
                "auxiliary_kwh": 0.0, "trips": 0}

    bands = {name: empty() for name, _, _ in TEMPERATURE_BANDS}
    seasons = {name: empty() for name in SEASONS}
    for trip in trips:
        net = net_energy(trip.vehicle_energy_used_kwh, trip.recovered_energy_kwh)
        if net is None or not trip.distance_km:
            # Without energy or distance a trip only distorts kWh/100 km.
            continue
        groups = [seasons[trip.season]]
        if trip.outside_temp_avg_c is not None:
            groups.append(bands[_band(trip.outside_temp_avg_c)])
        for group in groups:
            group["distance_km"] += trip.distance_km
            # Consumption is net: drawn minus recuperated energy.
            group["vehicle_kwh"] += net
            group["used_kwh"] += trip.vehicle_energy_used_kwh or 0
            group["recovered_kwh"] += trip.recovered_energy_kwh or 0
            group["auxiliary_kwh"] += trip.auxiliary_energy_kwh or 0
            group["trips"] += 1

    def finish(group: dict[str, float]) -> dict[str, Any]:
        km = group["distance_km"]
        vehicle = group["vehicle_kwh"]
        grid = vehicle / (1 - loss) if loss < 1 else vehicle
        return {
            **{k: round(v, 3) for k, v in group.items()},
            "vehicle_kwh_100km": round(vehicle / km * 100, 2) if km else None,
            "grid_kwh_100km": round(grid / km * 100, 2) if km else None,
            "grid_kwh_estimated": round(grid, 3),
            # Recuperation share relative to the energy drawn from the battery.
            "recuperation_share_pct": round(group["recovered_kwh"] / group["used_kwh"] * 100, 1)
            if group["used_kwh"] else None,
            "cost_eur": round(grid * price_eur_kwh, 2),
            "quality": "ESTIMATED",
        }

    return {
        "bands": {name: finish(g) for name, g in bands.items()},
        "seasons": {name: finish(g) for name, g in seasons.items()},
    }
