"""Planners: derive charging wishes from schedule, one-shot, override and target SOC (§5).

Every planner is a pure function of its configuration, ``now`` and the
current values. None of them knows about the others – the arbiter picks the
winner. All wall-clock times are interpreted in the configured local time
zone and converted to UTC before any arithmetic, so DST changes cannot shift
a window by an hour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from .model import Desired, Quality, Reason, Value

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ScheduleMode(StrEnum):
    DEPARTURE_BASED = "departure_based"
    FIXED_START = "fixed_start"


class OverrideMode(StrEnum):
    UNTIL_UNPLUGGED = "until_unplugged"
    DURATION = "duration"
    UNTIL_TIME = "until_time"
    UNTIL_SOC = "until_soc"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class VehicleParams:
    """Physical parameters for the feasibility estimate (§5.6).

    Defaults: smart EQ fortwo 453 with 17.6 kWh gross / ~16.7 kWh usable and
    the standard 4.6 kW on-board charger. ``grid_limit_kw`` models a §14a
    EnWG dimming (4.2 kW) when it is active.
    """

    usable_capacity_kwh: float = 16.7
    charge_efficiency: float = 0.9
    halo_limit_kw: float = 11.0
    vehicle_charger_kw: float = 4.6
    grid_limit_kw: float | None = None
    safety_reserve_min: int = 30

    @property
    def expected_power_kw(self) -> float:
        limits = [self.halo_limit_kw, self.vehicle_charger_kw]
        if self.grid_limit_kw is not None:
            limits.append(self.grid_limit_kw)
        return max(0.1, min(limits))


@dataclass(frozen=True, slots=True)
class WeeklySchedule:
    """A recurring plan (§5.1). ``weekdays`` are the days of *departure*."""

    id: str
    weekdays: frozenset[str] = frozenset(WEEKDAYS[:5])
    enabled: bool = True
    mode: ScheduleMode = ScheduleMode.DEPARTURE_BASED
    charge_start_time: time = time(3, 0)
    departure_time: time = time(5, 30)
    ready_buffer_min: int = 30
    minimum_departure_soc_pct: int = 80
    preferred_departure_soc_pct: int = 90


@dataclass(frozen=True, slots=True)
class OneShot:
    """"Charge tonight" – one concrete departure, deletes itself afterwards (§5.2)."""

    departure_at: datetime
    mode: ScheduleMode = ScheduleMode.DEPARTURE_BASED
    charge_start_time: time = time(3, 0)
    ready_buffer_min: int = 30
    minimum_departure_soc_pct: int = 80
    preferred_departure_soc_pct: int = 90
    id: str = "one-shot"

    def expired(self, now: datetime) -> bool:
        return now >= self.departure_at


@dataclass(frozen=True, slots=True)
class ManualOverride:
    """"Charge now" / "stop charging" (§5.3). Wins over every plan."""

    mode: OverrideMode
    started_at: datetime
    expires_at: datetime | None = None
    target_soc: int | None = None
    source: Reason = Reason.OVERRIDE

    @property
    def charger_enabled(self) -> bool:
        return self.mode is not OverrideMode.STOP

    def expired(self, now: datetime, cable_connected: bool, soc: Value | None) -> bool:
        if not cable_connected:
            # Every override ends with the cable – the next plug-in starts fresh.
            return True
        if self.expires_at is not None and now >= self.expires_at:
            return True
        if self.mode is OverrideMode.UNTIL_SOC and self.target_soc is not None and soc is not None:
            return soc.quality is Quality.GOOD and float(soc.normalized) >= self.target_soc
        return False


@dataclass(frozen=True, slots=True)
class Estimate:
    """Feasibility result, always shown as an estimate (§5.6)."""

    soc_pct: float | None
    needed_kwh: float | None
    duration: timedelta | None
    expected_soc_at_departure: float | None
    minimum_reachable: bool | None
    preferred_reachable: bool | None


@dataclass(frozen=True, slots=True)
class ChargeWindow:
    source_id: str
    reason: Reason
    start: datetime
    departure: datetime
    ready_at: datetime
    fallback_without_soc: bool
    minimum_soc_pct: int
    preferred_soc_pct: int
    estimate: Estimate = field(default_factory=lambda: Estimate(None, None, None, None, None, None))

    def contains(self, now: datetime) -> bool:
        return self.start <= now < self.departure


def _local(d: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz).astimezone(UTC)


def next_departure(schedule: WeeklySchedule, now: datetime, tz: ZoneInfo) -> datetime | None:
    """Earliest departure of ``schedule`` that is still ahead of ``now``."""
    if not schedule.enabled or not schedule.weekdays:
        return None
    today = now.astimezone(tz).date()
    for offset in range(8):
        day = today + timedelta(days=offset)
        if WEEKDAYS[day.weekday()] not in schedule.weekdays:
            continue
        departure = _local(day, schedule.departure_time, tz)
        if departure > now:
            return departure
    return None


def charge_duration(
    soc_pct: float, target_pct: float, params: VehicleParams
) -> tuple[float, timedelta]:
    """Grid energy and time needed to get from ``soc_pct`` to ``target_pct``."""
    missing = max(0.0, target_pct - soc_pct) / 100.0
    needed_kwh = missing * params.usable_capacity_kwh / params.charge_efficiency
    hours = needed_kwh / params.expected_power_kw
    return needed_kwh, timedelta(hours=hours)


def _estimate(
    soc: Value | None,
    charge_from: datetime,
    ready_at: datetime,
    minimum_pct: int,
    preferred_pct: int,
    params: VehicleParams,
) -> Estimate:
    if soc is None or not soc.quality.usable_for_planning:
        return Estimate(None, None, None, None, None, None)
    soc_pct = float(soc.normalized)
    needed_kwh, duration = charge_duration(soc_pct, preferred_pct, params)
    hours = max(0.0, (ready_at - charge_from).total_seconds() / 3600)
    gained_pct = hours * params.expected_power_kw * params.charge_efficiency \
        / params.usable_capacity_kwh * 100
    expected = min(100.0, soc_pct + gained_pct)
    return Estimate(
        soc_pct=soc_pct,
        needed_kwh=round(needed_kwh, 2),
        duration=duration,
        expected_soc_at_departure=round(expected, 1),
        minimum_reachable=expected >= minimum_pct,
        preferred_reachable=expected >= preferred_pct,
    )


def _window(
    *,
    source_id: str,
    reason: Reason,
    departure: datetime,
    mode: ScheduleMode,
    charge_start_time: time,
    ready_buffer_min: int,
    minimum_pct: int,
    preferred_pct: int,
    now: datetime,
    tz: ZoneInfo,
    soc: Value | None,
    params: VehicleParams,
) -> ChargeWindow:
    ready_at = departure - timedelta(minutes=ready_buffer_min)
    soc_usable = soc is not None and soc.quality.usable_for_planning
    fallback = mode is ScheduleMode.DEPARTURE_BASED and not soc_usable
    if mode is ScheduleMode.DEPARTURE_BASED and soc_usable:
        _, duration = charge_duration(float(soc.normalized), preferred_pct, params)
        start = ready_at - duration - timedelta(minutes=params.safety_reserve_min)
    else:
        local_departure = departure.astimezone(tz)
        start = _local(local_departure.date(), charge_start_time, tz)
        if start >= departure:
            start = _local(local_departure.date() - timedelta(days=1), charge_start_time, tz)
    estimate = _estimate(soc, max(now, start), ready_at, minimum_pct, preferred_pct, params)
    return ChargeWindow(
        source_id=source_id,
        reason=reason,
        start=start,
        departure=departure,
        ready_at=ready_at,
        fallback_without_soc=fallback,
        minimum_soc_pct=minimum_pct,
        preferred_soc_pct=preferred_pct,
        estimate=estimate,
    )


def schedule_window(
    schedule: WeeklySchedule,
    now: datetime,
    tz: ZoneInfo,
    soc: Value | None,
    params: VehicleParams,
) -> ChargeWindow | None:
    """The upcoming (or currently running) window of a weekly plan (§5.1, §5.6)."""
    departure = next_departure(schedule, now, tz)
    if departure is None:
        return None
    return _window(
        source_id=schedule.id,
        reason=Reason.SCHEDULE,
        departure=departure,
        mode=schedule.mode,
        charge_start_time=schedule.charge_start_time,
        ready_buffer_min=schedule.ready_buffer_min,
        minimum_pct=schedule.minimum_departure_soc_pct,
        preferred_pct=schedule.preferred_departure_soc_pct,
        now=now,
        tz=tz,
        soc=soc,
        params=params,
    )


def one_shot_window(
    one_shot: OneShot, now: datetime, tz: ZoneInfo, soc: Value | None, params: VehicleParams
) -> ChargeWindow | None:
    if one_shot.expired(now):
        return None
    return _window(
        source_id=one_shot.id,
        reason=Reason.ONE_SHOT,
        departure=one_shot.departure_at,
        mode=one_shot.mode,
        charge_start_time=one_shot.charge_start_time,
        ready_buffer_min=one_shot.ready_buffer_min,
        minimum_pct=one_shot.minimum_departure_soc_pct,
        preferred_pct=one_shot.preferred_departure_soc_pct,
        now=now,
        tz=tz,
        soc=soc,
        params=params,
    )


def window_wish(window: ChargeWindow | None, now: datetime) -> Desired | None:
    """A window only expresses a wish while it is running."""
    if window is None or not window.contains(now):
        return None
    return Desired(
        charger_enabled=True,
        reason=window.reason,
        source_id=window.source_id,
        valid_until=window.departure,
    )


def override_wish(override: ManualOverride | None) -> Desired | None:
    if override is None:
        return None
    return Desired(
        charger_enabled=override.charger_enabled,
        reason=override.source,
        source_id=f"{override.mode}@{override.started_at.isoformat()}",
        valid_until=override.expires_at,
    )


def target_soc_wish(
    soc: Value | None, target_pct: int | None, climate_topup_active: bool = False
) -> Desired | None:
    """Switch the Halo off once the target SOC is reached (§5.5).

    Only a GOOD SOC may cause a shutdown – an old value never does. While a
    pre-climatisation with policy ``allow_topup`` runs, the target is
    deliberately not enforced (§9.1).
    """
    if soc is None or target_pct is None or climate_topup_active:
        return None
    if soc.quality is not Quality.GOOD:
        return None
    if float(soc.normalized) < target_pct:
        return None
    return Desired(charger_enabled=False, reason=Reason.TARGET_SOC_REACHED,
                   source_id=f"soc>={target_pct}")
