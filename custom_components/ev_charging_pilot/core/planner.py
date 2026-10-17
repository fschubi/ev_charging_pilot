"""Planners: derive charging wishes from schedule, one-shot, override and target SOC (§5).

Every planner is a pure function of its configuration, ``now`` and the
current values. None of them knows about the others – the arbiter picks the
winner. All wall-clock times are interpreted in the configured local time
zone and converted to UTC before any arithmetic, so DST changes cannot shift
a window by an hour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from .model import Desired, Quality, Reason, Value
from .prices import PriceSchedule, cheapest_blocks

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
    the standard 4.6 kW on-board charger; the rest follows masterplan §13.2.
    ``grid_limit_kw`` models a §14a EnWG dimming (4.2 kW) when it is active.
    """

    usable_capacity_kwh: float = 16.7
    charge_efficiency: float = 0.88
    halo_limit_kw: float = 11.0
    vehicle_charger_kw: float = 4.6
    grid_limit_kw: float | None = None
    # The estimate is never exact (temperature, slower charging near full): the
    # start moves this share of the charging time earlier. The visible buffer is
    # the plan's "ready before departure".
    reserve_share: float = 0.1
    reserve_min_minutes: int = 5
    # Measured on the car's own sessions (core.learning); None = nominal values.
    learned_kwh_per_pct: float | None = None
    learned_power_kw: float | None = None
    # Near full the battery accepts less power. Above this SOC the planner
    # assumes ``taper_factor`` of the normal power (conservative: starts earlier).
    taper_from_pct: float = 80.0
    taper_factor: float = 0.6
    # A target above ``full_soc_pct`` must not be reached earlier than
    # ``full_hold_max_h`` before "ready" – cheap prices do not justify a battery
    # standing full for hours. 0 switches the limit off.
    full_soc_pct: float = 90.0
    full_hold_max_h: float = 2.0

    @property
    def wallbox_limit_kw(self) -> float:
        """What the wallbox (and a §14a dimming) can deliver at most."""
        limits = [self.halo_limit_kw]
        if self.grid_limit_kw is not None:
            limits.append(self.grid_limit_kw)
        return min(limits)

    @property
    def expected_power_kw(self) -> float:
        # A measured power replaces the nominal on-board charger value – the car
        # may have the bigger charger (smart 453: 22 kW option).
        car = self.learned_power_kw if self.learned_power_kw is not None \
            else self.vehicle_charger_kw
        return max(0.1, min(self.wallbox_limit_kw, car))

    @property
    def kwh_per_pct(self) -> float:
        """Grid energy for one SOC percent, losses included."""
        if self.learned_kwh_per_pct is not None:
            return self.learned_kwh_per_pct
        return self.usable_capacity_kwh / self.charge_efficiency / 100


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
    climate: str = "auto"
    name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id,
            "enabled": self.enabled,
            "weekdays": [d for d in WEEKDAYS if d in self.weekdays],
            "mode": str(self.mode),
            "charge_start_time": self.charge_start_time.strftime("%H:%M"),
            "departure_time": self.departure_time.strftime("%H:%M"),
            "ready_buffer_min": self.ready_buffer_min,
            "minimum_departure_soc_pct": self.minimum_departure_soc_pct,
            "preferred_departure_soc_pct": self.preferred_departure_soc_pct,
            "climate": self.climate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeeklySchedule:
        minimum = int(data.get("minimum_departure_soc_pct", 80))
        preferred = max(minimum, int(data.get("preferred_departure_soc_pct", 90)))
        days = frozenset(d for d in data.get("weekdays", WEEKDAYS[:5]) if d in WEEKDAYS)
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data["id"]),
            enabled=bool(data.get("enabled", True)),
            weekdays=days,
            mode=ScheduleMode(data.get("mode", ScheduleMode.DEPARTURE_BASED)),
            charge_start_time=time.fromisoformat(str(data.get("charge_start_time", "03:00"))),
            departure_time=time.fromisoformat(str(data.get("departure_time", "05:30"))),
            ready_buffer_min=int(data.get("ready_buffer_min", 30)),
            minimum_departure_soc_pct=minimum,
            preferred_departure_soc_pct=preferred,
            climate=str(data.get("climate", "auto")),
        )


DEFAULT_PLAN = WeeklySchedule(id="plan-werktage", name="Werktage")


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
    climate: str = "auto"

    def expired(self, now: datetime) -> bool:
        return now >= self.departure_at

    def as_dict(self) -> dict[str, Any]:
        return {
            "departure_at": self.departure_at.isoformat(),
            "mode": str(self.mode),
            "charge_start_time": self.charge_start_time.isoformat(),
            "ready_buffer_min": self.ready_buffer_min,
            "minimum_departure_soc_pct": self.minimum_departure_soc_pct,
            "preferred_departure_soc_pct": self.preferred_departure_soc_pct,
            "climate": self.climate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OneShot:
        return cls(
            departure_at=datetime.fromisoformat(data["departure_at"]),
            mode=ScheduleMode(data["mode"]),
            charge_start_time=time.fromisoformat(data["charge_start_time"]),
            ready_buffer_min=int(data["ready_buffer_min"]),
            minimum_departure_soc_pct=int(data["minimum_departure_soc_pct"]),
            preferred_departure_soc_pct=int(data["preferred_departure_soc_pct"]),
            climate=str(data.get("climate", "auto")),
        )

    @classmethod
    def for_next(cls, plan: WeeklySchedule, now: datetime, tz: ZoneInfo,
                 departure_time: time | None = None, *, departure_at: datetime | None = None,
                 target_soc: int | None = None) -> OneShot:
        """"Charge tonight": the next occurrence of the plan's departure time, any weekday.

        ``departure_at`` sets a concrete date instead (e.g. Friday 07:00, holiday);
        ``target_soc`` replaces the plan's target for this one departure.
        """
        if departure_at is not None:
            departure = (departure_at if departure_at.tzinfo else
                         departure_at.replace(tzinfo=tz)).astimezone(UTC)
            if departure <= now or departure - now > timedelta(days=14):
                raise ValueError("Die Abfahrt muss in den nächsten 14 Tagen liegen")
        else:
            local = now.astimezone(tz)
            at = departure_time or plan.departure_time
            departure = _local(local.date(), at, tz)
            if departure <= now:
                departure = _local(local.date() + timedelta(days=1), at, tz)
        preferred = target_soc or plan.preferred_departure_soc_pct
        return cls(
            departure_at=departure,
            mode=plan.mode,
            charge_start_time=plan.charge_start_time,
            ready_buffer_min=plan.ready_buffer_min,
            minimum_departure_soc_pct=min(plan.minimum_departure_soc_pct, preferred),
            preferred_departure_soc_pct=preferred,
            climate=plan.climate,
        )


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

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": str(self.mode),
            "started_at": self.started_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "target_soc": self.target_soc,
            "source": str(self.source),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManualOverride:
        return cls(
            mode=OverrideMode(data["mode"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at")
            else None,
            target_soc=data.get("target_soc"),
            source=Reason(data.get("source", Reason.OVERRIDE)),
        )


@dataclass(frozen=True, slots=True)
class Estimate:
    """Feasibility result, always shown as an estimate (§5.6)."""

    soc_pct: float | None
    needed_kwh: float | None
    duration: timedelta | None
    expected_soc_at_departure: float | None
    minimum_reachable: bool | None
    preferred_reachable: bool | None
    finish_at: datetime | None = None
    cost_eur: float | None = None


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
    climate: str = "auto"
    name: str = ""
    # Price-optimised charging: only these blocks charge (§11 "günstigste Intervalle").
    blocks: tuple[tuple[datetime, datetime], ...] = ()

    @property
    def key(self) -> str:
        return f"{self.source_id}@{self.departure.isoformat()}"

    @property
    def price_optimized(self) -> bool:
        return bool(self.blocks)

    def contains(self, now: datetime) -> bool:
        if self.blocks:
            return any(start <= now < end for start, end in self.blocks)
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
    taper = params.taper_from_pct
    below = max(0.0, min(target_pct, taper) - soc_pct)
    above = max(0.0, target_pct - max(soc_pct, taper))
    needed_kwh = (below + above) * params.kwh_per_pct
    power = params.expected_power_kw
    hours = (below + above / params.taper_factor) * params.kwh_per_pct / power
    return needed_kwh, timedelta(hours=hours)


def soc_after(soc_pct: float, hours: float, params: VehicleParams) -> float:
    """SOC after charging ``hours`` from ``soc_pct`` (inverse of :func:`charge_duration`)."""
    pct_per_hour = params.expected_power_kw / params.kwh_per_pct
    taper = params.taper_from_pct
    if soc_pct < taper:
        to_taper = (taper - soc_pct) / pct_per_hour
        if hours <= to_taper:
            return soc_pct + hours * pct_per_hour
        hours -= to_taper
        soc_pct = taper
    return min(100.0, soc_pct + hours * pct_per_hour * params.taper_factor)


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
    # The target-SOC shutdown stops charging at the preferred SOC.
    expected = min(soc_after(soc_pct, hours, params), max(soc_pct, float(preferred_pct)))
    return Estimate(
        soc_pct=soc_pct,
        needed_kwh=round(needed_kwh, 2),
        duration=duration,
        expected_soc_at_departure=round(expected, 1),
        minimum_reachable=expected >= minimum_pct,
        preferred_reachable=expected >= preferred_pct,
        finish_at=charge_from + duration,
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
    climate: str = "auto",
    name: str = "",
    prices: PriceSchedule | None = None,
    price_blocks: int = 1,
) -> ChargeWindow:
    ready_at = departure - timedelta(minutes=ready_buffer_min)
    soc_usable = soc is not None and soc.quality.usable_for_planning
    fallback = mode is ScheduleMode.DEPARTURE_BASED and not soc_usable
    blocks: tuple[tuple[datetime, datetime], ...] = ()
    cost: float | None = None
    if mode is ScheduleMode.DEPARTURE_BASED and soc_usable:
        _, duration = charge_duration(float(soc.normalized), preferred_pct, params)
        # Whole minutes keep plans and push texts readable.
        duration = timedelta(minutes=math.ceil(duration.total_seconds() / 60))
        reserve = max(params.reserve_min_minutes,
                      math.ceil(duration.total_seconds() / 60 * params.reserve_share))
        needed = duration + timedelta(minutes=reserve)
        start = ready_at - needed
        if prices and price_blocks > 0 and duration > timedelta(0):
            # Without full price coverage (tomorrow's prices come around 13:00)
            # the plan simply stays "as late as possible".
            earliest = max(now, ready_at - timedelta(hours=24))
            if preferred_pct > params.full_soc_pct and params.full_hold_max_h > 0:
                earliest = max(earliest, ready_at - needed
                               - timedelta(hours=params.full_hold_max_h))
            best = cheapest_blocks(prices, earliest, ready_at,
                                   needed, params.expected_power_kw, price_blocks)
            if best is not None and best[0]:
                blocks = tuple(best[0])
                start = blocks[0][0]
                cost = best[1]
        if cost is None and prices:
            cost = prices.energy_cost(start, start + needed, params.expected_power_kw)
        if cost is not None:
            # The search prices full power over the whole block including the reserve;
            # the estimate only pays the energy the car actually needs, at the block's
            # average price.
            drawn = params.expected_power_kw * needed.total_seconds() / 3600
            needed_kwh, _ = charge_duration(float(soc.normalized), preferred_pct, params)
            cost = round(cost / drawn * needed_kwh, 2) if drawn > 0 else None
    else:
        local_departure = departure.astimezone(tz)
        start = _local(local_departure.date(), charge_start_time, tz)
        if start >= departure:
            start = _local(local_departure.date() - timedelta(days=1), charge_start_time, tz)
    estimate = _estimate(soc, max(now, start), ready_at, minimum_pct, preferred_pct, params)
    if blocks:
        # Charging only runs inside the blocks: estimate on the charging time left
        # and finish when the needed charging time is used up within the blocks.
        left = sum(((min(e, ready_at) - max(b, now)) for b, e in blocks if e > now),
                   timedelta(0))
        estimate = _estimate(soc, ready_at - left, ready_at, minimum_pct, preferred_pct, params)
        remaining, finish = estimate.duration or timedelta(0), None
        for begin, end in blocks:
            begin = max(begin, now)
            if end <= begin:
                continue
            if begin + remaining <= end:
                finish = begin + remaining
                break
            remaining -= end - begin
        estimate = replace(estimate, finish_at=finish or blocks[-1][1])
    if cost is not None:
        estimate = replace(estimate, cost_eur=cost)
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
        climate=climate,
        name=name or source_id,
        blocks=blocks,
    )


def schedule_window(
    schedule: WeeklySchedule,
    now: datetime,
    tz: ZoneInfo,
    soc: Value | None,
    params: VehicleParams,
    prices: PriceSchedule | None = None,
    price_blocks: int = 1,
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
        climate=schedule.climate,
        name=schedule.name,
        prices=prices,
        price_blocks=price_blocks,
    )


def one_shot_window(
    one_shot: OneShot, now: datetime, tz: ZoneInfo, soc: Value | None, params: VehicleParams,
    prices: PriceSchedule | None = None, price_blocks: int = 1,
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
        climate=one_shot.climate,
        name="Einmalige Abfahrt",
        prices=prices,
        price_blocks=price_blocks,
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
