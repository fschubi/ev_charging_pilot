"""Data quality classification and source conflicts (§7.2–§7.4)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .model import Quality, Value


@dataclass(frozen=True, slots=True)
class QualityRule:
    """How old a value may be and what counts as plausible."""

    max_age_s: float
    plausible: Callable[[Any], bool] | None = None


def soc_plausible(value: Any) -> bool:
    return isinstance(value, (int, float)) and 0 <= value <= 100


def non_negative(value: Any) -> bool:
    return isinstance(value, (int, float)) and value >= 0


def classify(
    value: Value,
    now: datetime,
    rule: QualityRule,
    last_activity_at: datetime | None = None,
) -> Value:
    """Return ``value`` with its quality set according to §7.2.

    ``last_activity_at`` is the latest moment the vehicle drove, charged or
    was unplugged. A value older than ``max_age_s`` stays LAST_KNOWN_VALID as
    long as nothing happened since it was recorded – a sleeping car keeps its
    SOC, so it must not count as stale (and must never be woken just to
    refresh it, §7.3).
    """
    if value.quality in (Quality.UNAVAILABLE, Quality.INVALID, Quality.ESTIMATED):
        return value
    if value.normalized is None:
        return value.with_quality(Quality.UNAVAILABLE)
    if rule.plausible is not None and not rule.plausible(value.normalized):
        return value.with_quality(Quality.INVALID)
    age = value.age_s(now)
    if age is None:
        return value.with_quality(Quality.UNAVAILABLE)
    if age <= rule.max_age_s:
        return value.with_quality(Quality.GOOD)
    if last_activity_at is not None and value.updated_at is not None \
            and last_activity_at > value.updated_at:
        return value.with_quality(Quality.STALE)
    return value.with_quality(Quality.LAST_KNOWN_VALID)


def charging_conflict(
    halo_power_w: Value, vehicle_charging: Value, threshold_w: float
) -> bool:
    """Halo sees power but the vehicle says it is not charging, or vice versa (§7.4).

    Only GOOD values on both sides can contradict each other; anything less
    is simply not comparable.
    """
    if halo_power_w.quality is not Quality.GOOD or vehicle_charging.quality is not Quality.GOOD:
        return False
    halo_charging = float(halo_power_w.normalized) > threshold_w
    return halo_charging != bool(vehicle_charging.normalized)
