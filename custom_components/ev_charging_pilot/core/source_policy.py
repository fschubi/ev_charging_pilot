"""Source policy (§7.4): which source wins, when sources conflict, HV cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .model import Quality, Value


def mark_conflict(*values: Value) -> tuple[Value, ...]:
    """Both sides of a contradiction become CONFLICT – none is silently overwritten."""
    return tuple(v.with_quality(Quality.CONFLICT) for v in values)


def plugged_in(halo: Value, plug: Value, at_home: Value) -> Value:
    """Fuse the wallbox cable flag with the vehicle's own plug detection.

    The Halo reports the cable only while its connector is enabled – and the
    Charging Center keeps it disabled most of the time. OVMS sees the plug
    always; its location tells a home plug from one at a public charger.
    """
    if (halo.available and halo.normalized) or not plug.available:
        return halo
    home = bool(at_home.normalized) if at_home.available else None
    if plug.normalized and home is not False:
        return Value(plug.raw, True, plug.source, plug.updated_at, plug.quality)
    if halo.available:
        return halo
    return Value(plug.raw, False, plug.source, plug.updated_at, plug.quality)


def vehicle_charging(ovms: Value, halo_power: Value, threshold_w: float) -> Value:
    """OVMS first; without a GOOD OVMS value the Halo power is the fallback."""
    if ovms.quality is Quality.GOOD:
        return ovms
    if halo_power.quality is Quality.GOOD and halo_power.normalized is not None:
        return Value(halo_power.raw, float(halo_power.normalized) > threshold_w, "halo",
                     halo_power.updated_at, Quality.ESTIMATED)
    return ovms


def outside_temperature(vehicle: Value, ha_sensor: Value, weather: Value) -> Value:
    """Vehicle (only when GOOD) → HA sensor → weather entity (§7.4)."""
    for candidate in (vehicle, ha_sensor, weather):
        if candidate.quality is Quality.GOOD:
            return candidate
    for candidate in (ha_sensor, weather):
        if candidate.quality.usable_for_planning:
            return candidate
    return Value.unavailable("none")


@dataclass(slots=True)
class HvCycleMonitor:
    """Watches the HV contactor counter: every wakeup costs cycles (§1.1 rule 6).

    Warns once per day when the counter rose by more than ``warn_per_day``,
    and once per increase that happened while the car neither charged nor
    drove (a wakeup without reason).
    """

    warn_per_day: int = 10
    day: date | None = None
    day_start: float | None = None
    last: float | None = None
    warned_day: date | None = None

    def update(self, value: Value, local_day: date, active: bool) -> list[str]:
        if value.quality not in (Quality.GOOD, Quality.LAST_KNOWN_VALID):
            return []
        cycles = float(value.normalized)
        warnings: list[str] = []
        if self.day != local_day:
            self.day = local_day
            self.day_start = cycles
        if self.last is not None and cycles > self.last and not active:
            warnings.append("HV_CYCLE_WITHOUT_ACTIVITY")
        self.last = cycles
        if (
            self.day_start is not None
            and cycles - self.day_start > self.warn_per_day
            and self.warned_day != local_day
        ):
            self.warned_day = local_day
            warnings.append("HV_CYCLES_HIGH")
        return warnings

    @property
    def today(self) -> float | None:
        if self.last is None or self.day_start is None:
            return None
        return self.last - self.day_start

    def as_dict(self) -> dict:
        return {
            "day": self.day.isoformat() if self.day else None,
            "day_start": self.day_start,
            "last": self.last,
            "warned_day": self.warned_day.isoformat() if self.warned_day else None,
        }

    @classmethod
    def from_dict(cls, data: dict, warn_per_day: int) -> HvCycleMonitor:
        return cls(
            warn_per_day=warn_per_day,
            day=date.fromisoformat(data["day"]) if data.get("day") else None,
            day_start=data.get("day_start"),
            last=data.get("last"),
            warned_day=date.fromisoformat(data["warned_day"]) if data.get("warned_day") else None,
        )


def latest(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)
