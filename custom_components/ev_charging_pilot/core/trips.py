"""Trips (§10.3).

A trip starts when OVMS reports "ready to drive" and ends once the car has
been off for longer than ``trip_merge_gap_min``; shorter stops are merged.
Locking the car after switching it off ends the trip at once – the driver left.
When OVMS data does not reach HA on the road, a trip is reconstructed from
the odometer difference at home and marked PARTIAL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .model import Quality, Value

MIN_RECONSTRUCT_KM = 0.5
# Drive curve for the trip detail view: speed changes fast, so one point per 15 s,
# at most six hours.
TRACE_STEP_S = 15
TRACE_MAX = 1440
# Below this distance (manoeuvring, moving the car) kWh/100 km means nothing.
MIN_CONSUMPTION_KM = 1.0


# Range estimate at the start: the highest value in the first minutes. While the
# pre-climatisation still runs the car shows less (21.10.2026: 101 instead of 112 km).
RANGE_START_WINDOW = timedelta(minutes=3)
# Version of the range rule; older trips are recomputed from the recorder.
RANGE_RULE = 2

# Driving style from the 15-s drive curve – the pilot's own measure, not the car's
# eco display (OVMS does not provide that one).
STYLE_MIN_SAMPLES = 20
STRONG_DRIVE_W = 25000      # drive power that counts as hard acceleration …
STRONG_SPEEDUP_KMH = 10     # … while the speed rises at least this much per sample
STEADY_MAX_DELTA_KMH = 5    # cruising: speed change per sample at most this
STEADY_MIN_KMH = 30
# Speed drop per sample that counts as hard braking. 15-s samples average a normal
# stop at a traffic light (70 → 20 km/h); only far more is really hard.
HARD_BRAKE_KMH = 40


def driving_style(trace: list[list[float | None]]) -> dict[str, float] | None:
    """Score 0–100 from [s, km/h, battery W (− drive), SOC] samples, or None.

    Three parts, each 0–100: gentle acceleration, steady cruising and anticipation
    (few hard brakings); the score is their mean.
    """
    points = [p for p in trace if p[1] is not None]
    if len(points) < STYLE_MIN_SAMPLES:
        return None
    moving = strong = cruising = steady = hard = 0
    for prev, cur in zip(points, points[1:], strict=False):
        speed, delta = cur[1], cur[1] - prev[1]
        if speed < 5 and prev[1] < 5:
            continue
        moving += 1
        drive_w = -cur[2] if cur[2] is not None else 0.0
        if drive_w > STRONG_DRIVE_W and delta >= STRONG_SPEEDUP_KMH:
            strong += 1
        if delta <= -HARD_BRAKE_KMH:
            hard += 1
        if speed >= STEADY_MIN_KMH and prev[1] >= STEADY_MIN_KMH:
            cruising += 1
            if abs(delta) <= STEADY_MAX_DELTA_KMH:
                steady += 1
    if moving < STYLE_MIN_SAMPLES:
        return None
    gentle = max(0.0, 100 - 400 * strong / moving)
    smooth = 100 * steady / cruising if cruising else 100.0
    anticipating = max(0.0, 100 - 400 * hard / moving)
    return {"score": round((gentle + smooth + anticipating) / 3),
            "gentle": round(gentle), "steady": round(smooth),
            "anticipating": round(anticipating)}


def net_energy(used: float | None, recovered: float | None) -> float | None:
    """What the battery really lost: OVMS counts drawn and recuperated energy separately."""
    if used is None:
        return None
    net = used - (recovered or 0.0)
    # Recuperated more than drawn = the counters do not belong together (reset mid-trip).
    return round(net, 4) if net >= 0 else None


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
    # [seconds since start, km/h, battery W as OVMS reports it (+ into the battery,
    # i.e. recuperation; − drive), SOC %].
    trace: list[list[float | None]] = field(default_factory=list)
    # The car's estimated range at start and end (OVMS): how far the estimate fits.
    range_start_km: float | None = None
    range_end_km: float | None = None
    range_rule: int = 0
    # driving_style(): score and its parts (gentle, steady, anticipating), 0–100.
    style: dict[str, float] | None = None

    @property
    def range_used_km(self) -> float | None:
        if self.range_start_km is None or self.range_end_km is None:
            return None
        return round(self.range_start_km - self.range_end_km, 1)

    @property
    def range_accuracy_pct(self) -> float | None:
        """Driven km per km the estimate dropped: 83 % = the car was too optimistic."""
        used = self.range_used_km
        if used is None or used < 1 or not self.distance_km \
                or self.distance_km < MIN_CONSUMPTION_KM:
            return None
        return round(self.distance_km / used * 100, 1)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["range_used_km"] = self.range_used_km
        data["range_accuracy_pct"] = self.range_accuracy_pct
        data["started_at"] = self.started_at.isoformat()
        data["ended_at"] = self.ended_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trip:
        values = {k: v for k, v in data.items()
                  if k not in ("range_used_km", "range_accuracy_pct")}
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


def _with_acc(trip: dict[str, Any], key: str) -> float | None:
    delta = _counter_delta(trip[f"{key}_start"], trip[f"{key}_end"])
    acc = trip.get(f"{key}_acc") or 0.0
    if delta is None:
        return round(acc, 4) if acc else None
    return round(delta + acc, 4)


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
        speed: Value | None = None,
        battery_power: Value | None = None,
        locked: Value | None = None,
        range_km: Value | None = None,
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
                self.open["unlocked_after_off"] = False
            self._sample(now, km, energy_used, energy_recd, aux, soc, outside_temp)
            self._trace(now, speed, battery_power, soc)
            reach = _num(range_km)
            if reach is not None:
                # Start: the highest value at the beginning; end: the last one while on
                # (after switching off the display jumps up – 98 instead of 88 km).
                if now - self.open["started_at"] <= RANGE_START_WINDOW:
                    self.open["range_start"] = max(reach, self.open.get("range_start") or reach)
                elif self.open.get("range_start") is None:
                    self.open["range_start"] = reach
                self.open["range_end"] = reach
        elif self.open is not None:
            if self.open["off_since"] is None:
                self.open["off_since"] = now
            if km is not None and (self.open["odometer_end"] is None
                                   or km > self.open["odometer_end"]):
                # The last metres after switching off – or everything driven while HA
                # was down during the trip – belong to this trip.
                self.open["odometer_end"] = km
                if self.open["odometer_start"] is None:
                    self.open["odometer_start"] = km
            lock = None if locked is None or not locked.available \
                or locked.normalized is None else bool(locked.normalized)
            # The smart locks itself while driving: only a lock that follows an
            # unlock after switching off means "parked and left".
            if lock is False:
                self.open["unlocked_after_off"] = True
            left = lock is True and self.open.get("unlocked_after_off")
            if left or now - self.open["off_since"] >= self.merge_gap:
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
            # Energy of earlier drives when OVMS resets its trip counters per drive.
            "used_acc": 0.0,
            "recd_acc": 0.0,
            "aux_acc": 0.0,
            "soc_start": _num(soc),
            "soc_end": _num(soc),
            "temp_sum": 0.0,
            "temp_n": 0,
        }

    def _trace(self, now, speed, battery_power, soc) -> None:
        trace = self.open.setdefault("trace", [])
        offset = round((now - self.open["started_at"]).total_seconds())
        if len(trace) >= TRACE_MAX or (trace and offset - trace[-1][0] < TRACE_STEP_S):
            return
        kmh, watts, pct = _num(speed), _num(battery_power), _num(soc)
        if kmh is None and watts is None and pct is None:
            return
        trace.append([offset, round(kmh, 1) if kmh is not None else None,
                      round(watts) if watts is not None else None,
                      round(pct, 1) if pct is not None else None])

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
                last = trip[f"{key}_end"]
                if last is not None and number < last and trip[f"{key}_start"] is not None:
                    # Counter reset (new drive inside a merged trip): keep what the
                    # previous drive used and count the new one from zero.
                    trip[f"{key}_acc"] = trip.get(f"{key}_acc", 0.0) + \
                        max(0.0, last - trip[f"{key}_start"])
                    trip[f"{key}_start"] = 0.0
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
        used = _with_acc(t, "used")
        recovered = _with_acc(t, "recd")
        net = net_energy(used, recovered)
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
            recovered_energy_kwh=recovered,
            auxiliary_energy_kwh=_with_acc(t, "aux"),
            consumption_kwh_100km=round(net / distance * 100, 2)
            if net is not None and distance and distance >= MIN_CONSUMPTION_KM else None,
            outside_temp_avg_c=round(t["temp_sum"] / t["temp_n"], 1) if t["temp_n"] else None,
            season=season_of(t["started_at"], self.tz),
            soc_start_pct=t["soc_start"],
            soc_end_pct=t["soc_end"],
            quality=quality,
            trace=t.get("trace") or [],
            range_start_km=t.get("range_start"),
            range_end_km=t.get("range_end"),
            range_rule=RANGE_RULE,
            style=driving_style(t.get("trace") or [])
            if distance and distance >= MIN_CONSUMPTION_KM else None,
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
