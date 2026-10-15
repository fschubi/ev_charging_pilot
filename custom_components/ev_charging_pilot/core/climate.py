"""Pre-climatisation planner (§9).

Climate runs time-based through OVMS (5/10/15 min, ``homelink 1/2/3``). When
the car is plugged in, the Halo is enabled beforehand so grid power is
available. What happens after the target SOC is reached is decided by
``climate_after_target`` (§9.1).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .model import ClimateRequest, Desired, Quality, Reason, Value
from .settings import Settings

LEAD_MIN = 2
LEVEL_BY_MINUTES = {5: 1, 10: 2, 15: 3}


def homelink_level(duration_min: int) -> int:
    """Map a duration onto the nearest OVMS homelink slot."""
    return min(LEVEL_BY_MINUTES.items(), key=lambda kv: abs(kv[0] - duration_min))[1]


def planned_duration(mode: str, outside: Value, settings: Settings) -> int:
    """``mode`` is the plan's climate setting: off / auto / fixed minutes."""
    if mode == "off" or not settings.climate_enabled:
        return 0
    if mode == "auto":
        if not outside.quality.usable_for_planning or outside.normalized is None:
            return 0
        return settings.climate_profiles.duration_for(float(outside.normalized))
    try:
        return int(mode)
    except ValueError:
        return 0


def climate_request(departure: datetime, duration_min: int) -> ClimateRequest | None:
    if duration_min <= 0:
        return None
    start = departure - timedelta(minutes=duration_min + LEAD_MIN)
    return ClimateRequest(duration_min=duration_min, start_at=start, until=departure)


def climate_blocker(soc: Value | None, settings: Settings, degraded: bool) -> str | None:
    """Why a climate request must not run – or None if it may (§9.2 step 3)."""
    if not settings.climate_enabled:
        return "CLIMATE_DISABLED"
    if not settings.ovms_enabled:
        return "OVMS_DISABLED"
    if degraded:
        return "HEALTH_NOT_HEALTHY"
    if soc is None or soc.quality not in (Quality.GOOD, Quality.LAST_KNOWN_VALID):
        return "SOC_UNKNOWN"
    if float(soc.normalized) < settings.climate_min_soc_pct:
        return "SOC_TOO_LOW"
    return None


def climate_wish(request: ClimateRequest | None, now: datetime, plugged_in: bool,
                 source_id: str) -> Desired | None:
    """While the climate window runs: Halo on if plugged in, else leave it alone."""
    if request is None or not request.start_at <= now < request.until:
        return None
    return Desired(
        charger_enabled=True if plugged_in else None,
        reason=Reason.CLIMATE,
        source_id=source_id,
        valid_until=request.until,
        climate=request,
    )
