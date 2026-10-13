"""Trips (§10.3).

A trip starts when OVMS reports "ready to drive" and ends once the car has
been off for longer than ``trip_merge_gap_min``; shorter stops are merged.
When OVMS data does not reach HA on the road, a trip is reconstructed from
the odometer difference at home and marked PARTIAL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .model import Quality, Value

MIN_RECONSTRUCT_KM = 0.5


def season_of(moment: datetime, tz: ZoneInfo) -> str:
    month = moment.astimezone(tz).month
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


@dataclass(slots=True)
class Trip:
    trip_id: str
    started_at: datetime
    ended_at: datetime
    odometer_start_km: float | None
    odometer_end_km: float | None
    distance_km: float | None
    duration_min: float
    average_speed_kmh: float | None
    vehicle_energy_used_kwh: float | None
    recovered_energy_kwh: float | None
    auxiliary_energy_kwh: float | None
    consumption_kwh_100km: float | None
    outside_temp_avg_c: float | None
    season: str
    soc_start_pct: float | None
    soc_end_pct: float | None
    quality: str = "GOOD"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["ended_at"] = self.ended_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trip:
        values = dict(data)
        values["started_at"] = datetime.fromisoformat(values["started_at"])
        values["ended_at"] = datetime.fromisoformat(values["ended_at"])
        return cls(**values)


def _num(value: Value | None) -> float | None:
    if value is None or value.normalized is None:
        return None
    if value.quality not in (Quality.GOOD, Quality.LAST_KNOWN_VALID):
        return None
    return float(value.normalized)


def _counter_delta(start: float | None, end: float | None) -> float | None:
    """OVMS trip counters may reset at trip start – then the end value is the delta."""
    if start is None or end is None:
        return None
    return round(end - start if end >= start else end, 4)


class TripTracker:
    def __init__(self, merge_gap_min: int, tz: ZoneInfo) -> None:
        self.merge_gap = timedelta(minutes=merge_gap_min)
        self.tz = tz
        self.open: dict[str, Any] | None = None
        self.last_odometer: float | None = None
        self.last_odometer_at: datetime | None = None

    def update(
        self,
        now: datetime,
        *,
        vehicle_on: Value,
        odometer: Value,
        energy_used: Value,
        energy_recd: Value,
        aux: Value,
        soc: Value | None,
        outside_temp: Value,
    ) -> list[Trip]:
        closed: list[Trip] = []
        known = vehicle_on.quality is Quality.GOOD
        on = known and bool(vehicle_on.normalized)
        km = _num(odometer)

        if on:
            if self.open is None:
                self._start(now, km, energy_used, energy_recd, aux, soc)
            else:
                self.open["off_since"] = None
            self._sample(now, km, energy_used, energy_recd, aux, soc, outside_temp)
        elif self.open is not None:
            if self.open["off_since"] is None:
                self.open["off_since"] = now
            if now - self.open["off_since"] >= self.merge_gap:
                closed.append(self._close(partial=not known))
        elif km is not None and self.last_odometer is not None \
                and km - self.last_odometer >= MIN_RECONSTRUCT_KM:
            closed.append(self._reconstruct(now, km, soc))

        if km is not None and self.open is None:
            self.last_odometer = km if self.last_odometer is None else max(self.last_odometer, km)
            self.last_odometer_at = now
        return closed

    # ------------------------------------------------------------- internal

    def _start(self, now, km, used, recd, aux, soc) -> None:
        self.open = {
            "started_at": now,
            "last_on_at": now,
            "off_since": None,
            "odometer_start": km,
            "odometer_end": km,
            "used_start": _num(used),
            "recd_start": _num(recd),
            "aux_start": _num(aux),
            "used_end": None,
            "recd_end": None,
            "aux_end": None,
            "soc_start": _num(soc),
            "soc_end": _num(soc),
            "temp_sum": 0.0,
            "temp_n": 0,
        }

    def _sample(self, now, km, used, recd, aux, soc, temp) -> None:
        trip = self.open
        trip["last_on_at"] = now
        if km is not None:
            trip["odometer_end"] = km
            if trip["odometer_start"] is None:
                trip["odometer_start"] = km
        for key, value in (("used", used), ("recd", recd), ("aux", aux)):
            number = _num(value)
            if number is not None:
                trip[f"{key}_end"] = number
                if trip[f"{key}_start"] is None:
                    trip[f"{key}_start"] = number
        current_soc = _num(soc)
        if current_soc is not None:
            trip["soc_end"] = current_soc
            if trip["soc_start"] is None:
                trip["soc_start"] = current_soc
        temperature = _num(temp)
        if temperature is not None:
            trip["temp_sum"] += temperature
            trip["temp_n"] += 1

    def _close(self, partial: bool) -> Trip:
        t = self.open
        self.open = None
        ended = t["off_since"] or t["last_on_at"]
        distance = None
        if t["odometer_start"] is not None and t["odometer_end"] is not None:
            distance = round(t["odometer_end"] - t["odometer_start"], 2)
            self.last_odometer = t["odometer_end"]
            self.last_odometer_at = ended
        used = _counter_delta(t["used_start"], t["used_end"])
        duration_min = round((ended - t["started_at"]).total_seconds() / 60, 1)
        quality = "GOOD"
        if partial or distance is None:
            quality = "PARTIAL"
        elif used is None:
            quality = "ESTIMATED"
        return Trip(
            trip_id=f"t-{t['started_at'].strftime('%Y%m%d-%H%M%S')}",
            started_at=t["started_at"],
            ended_at=ended,
            odometer_start_km=t["odometer_start"],
            odometer_end_km=t["odometer_end"],
            distance_km=distance,
            duration_min=duration_min,
            average_speed_kmh=round(distance / (duration_min / 60), 1)
            if distance and duration_min > 0 else None,
            vehicle_energy_used_kwh=used,
            recovered_energy_kwh=_counter_delta(t["recd_start"], t["recd_end"]),
            auxiliary_energy_kwh=_counter_delta(t["aux_start"], t["aux_end"]),
            consumption_kwh_100km=round(used / distance * 100, 2)
            if used is not None and distance else None,
            outside_temp_avg_c=round(t["temp_sum"] / t["temp_n"], 1) if t["temp_n"] else None,
            season=season_of(t["started_at"], self.tz),
            soc_start_pct=t["soc_start"],
            soc_end_pct=t["soc_end"],
            quality=quality,
        )

    def _reconstruct(self, now: datetime, km: float, soc: Value | None) -> Trip:
        start = self.last_odometer_at or now
        distance = round(km - self.last_odometer, 2)
        trip = Trip(
            trip_id=f"p-{now.strftime('%Y%m%d-%H%M%S')}",
            started_at=start,
            ended_at=now,
            odometer_start_km=self.last_odometer,
            odometer_end_km=km,
            distance_km=distance,
            duration_min=round((now - start).total_seconds() / 60, 1),
            average_speed_kmh=None,
            vehicle_energy_used_kwh=None,
            recovered_energy_kwh=None,
            auxiliary_energy_kwh=None,
            consumption_kwh_100km=None,
            outside_temp_avg_c=None,
            season=season_of(start, self.tz),
            soc_start_pct=None,
            soc_end_pct=_num(soc),
            quality="PARTIAL",
        )
        return trip

    def as_dict(self) -> dict[str, Any]:
        open_trip = None
        if self.open is not None:
            open_trip = {
                k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in self.open.items()
            }
        return {
            "open": open_trip,
            "last_odometer": self.last_odometer,
            "last_odometer_at": self.last_odometer_at.isoformat()
            if self.last_odometer_at else None,
        }

    def restore(self, data: dict[str, Any]) -> None:
        raw = data.get("open")
        if raw:
            self.open = {
                k: (datetime.fromisoformat(v) if k in ("started_at", "last_on_at", "off_since")
                    and v else v)
                for k, v in raw.items()
            }
        self.last_odometer = data.get("last_odometer")
        at = data.get("last_odometer_at")
        self.last_odometer_at = datetime.fromisoformat(at) if at else None
