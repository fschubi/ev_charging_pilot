"""Automatic detection of charges away from home (§10.5, formerly "später").

Two independent signals, both only from data that arrives anyway – the car is
never woken for this (§1.1 rule 6):

1. **Live:** OVMS reports "charging" while the Halo is not delivering
   (cable not plugged in at home or no Halo power). Vehicle-side power is
   integrated; grid energy is estimated with the charging efficiency.
2. **SOC jump:** the next GOOD SOC after a gap is clearly higher than the last
   one, but the Halo counter explains only a small part of it.

Every detection is an ESTIMATED external charge; the user can complete the
cost and provider later (``add_external_charge`` with the same id).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .model import Quality, Value
from .statistics import ExternalCharge

END_GRACE = timedelta(minutes=10)
HOME_SHARE_LIMIT = 0.5


def _num(value: Value | None) -> float | None:
    if value is None or value.normalized is None:
        return None
    if value.quality not in (Quality.GOOD, Quality.LAST_KNOWN_VALID):
        return None
    return float(value.normalized)


@dataclass(slots=True)
class _Live:
    started_at: datetime
    soc_start: float | None
    kwh_vehicle: float = 0.0
    last_power: tuple[datetime, float] | None = None
    not_charging_since: datetime | None = None
    soc_end: float | None = None


class ExternalChargeDetector:
    def __init__(self, *, capacity_kwh: float, efficiency: float, min_kwh: float,
                 soc_jump_pct: float, price_eur_kwh: float, threshold_w: float) -> None:
        self.capacity = capacity_kwh
        self.efficiency = efficiency
        self.min_kwh = min_kwh
        self.soc_jump = soc_jump_pct
        self.price = price_eur_kwh
        self.threshold_w = threshold_w
        self.live: _Live | None = None
        self.last_soc: tuple[datetime, float] | None = None
        self.last_home_kwh: float | None = None

    def update(
        self,
        now: datetime,
        *,
        vehicle_charging: Value,
        vehicle_power: Value,
        soc: Value,
        halo_power: Value,
        cable_connected: bool | None,
        halo_total: Value,
    ) -> list[ExternalCharge]:
        found: list[ExternalCharge] = []
        halo_w = _num(halo_power) or 0.0
        home_delivering = cable_connected is True and halo_w > self.threshold_w
        charging = vehicle_charging.quality is Quality.GOOD and bool(vehicle_charging.normalized)
        soc_now = soc.quality is Quality.GOOD and soc.normalized is not None

        # --- 1. live detection
        if charging and not home_delivering:
            if self.live is None:
                self.live = _Live(started_at=now, soc_start=self.last_soc[1]
                                  if self.last_soc else _num(soc))
            self.live.not_charging_since = None
            self._integrate(now, vehicle_power)
            if soc_now:
                self.live.soc_end = float(soc.normalized)
        elif self.live is not None:
            if self.live.not_charging_since is None:
                self.live.not_charging_since = now
            if now - self.live.not_charging_since >= END_GRACE or home_delivering:
                charge = self._finish_live(now)
                if charge is not None:
                    found.append(charge)

        # --- 2. SOC jump detection
        home_kwh = _num(halo_total)
        if soc_now and self.live is None:
            current = float(soc.normalized)
            if self.last_soc is not None and current - self.last_soc[1] >= self.soc_jump \
                    and not charging:
                explained = 0.0
                if home_kwh is not None and self.last_home_kwh is not None:
                    explained = max(0.0, home_kwh - self.last_home_kwh) * self.efficiency
                needed = (current - self.last_soc[1]) / 100 * self.capacity
                if explained < needed * HOME_SHARE_LIMIT:
                    grid = (needed - explained) / self.efficiency
                    if grid >= self.min_kwh:
                        found.append(self._charge(self.last_soc[0], now, grid,
                                                  self.last_soc[1], current, "soc_jump"))
            self.last_soc = (now, current)
            if home_kwh is not None:
                self.last_home_kwh = home_kwh
        elif self.last_home_kwh is None and home_kwh is not None:
            self.last_home_kwh = home_kwh
        return found

    def _integrate(self, now: datetime, power: Value) -> None:
        watts = _num(power) if power.quality is Quality.GOOD else None
        if watts is None:
            return
        stamp = power.updated_at or now
        last = self.live.last_power
        if last is not None and stamp > last[0]:
            hours = (stamp - last[0]).total_seconds() / 3600
            self.live.kwh_vehicle += (watts + last[1]) / 2 / 1000 * hours
        if last is None or stamp > last[0]:
            self.live.last_power = (stamp, watts)

    def _finish_live(self, now: datetime) -> ExternalCharge | None:
        live, self.live = self.live, None
        grid = live.kwh_vehicle / self.efficiency if live.kwh_vehicle > 0 else None
        if grid is None and live.soc_start is not None and live.soc_end is not None:
            grid = max(0.0, live.soc_end - live.soc_start) / 100 * self.capacity / self.efficiency
        if live.soc_end is not None:
            self.last_soc = (now, live.soc_end)
        if grid is None or grid < self.min_kwh:
            return None
        return self._charge(live.started_at, live.not_charging_since or now, grid,
                            live.soc_start, live.soc_end, "ovms_live")

    def _charge(self, start: datetime, end: datetime, grid_kwh: float, soc_before: float | None,
                soc_after: float | None, method: str) -> ExternalCharge:
        kwh = round(grid_kwh, 2)
        return ExternalCharge(
            id=f"auto-{start.strftime('%Y%m%d%H%M')}",
            date=end.date(),
            source="public",
            energy_kwh=kwh,
            price_eur_kwh=self.price,
            soc_before=soc_before,
            soc_after=soc_after,
            note=f"automatisch erkannt ({method}), {start:%H:%M}–{end:%H:%M} UTC",
            detected=True,
            quality="ESTIMATED",
        )

    def as_dict(self) -> dict[str, Any]:
        live = None
        if self.live is not None:
            live = {
                "started_at": self.live.started_at.isoformat(),
                "soc_start": self.live.soc_start,
                "kwh_vehicle": self.live.kwh_vehicle,
                "soc_end": self.live.soc_end,
            }
        return {
            "live": live,
            "last_soc": [self.last_soc[0].isoformat(), self.last_soc[1]] if self.last_soc else None,
            "last_home_kwh": self.last_home_kwh,
        }

    def restore(self, data: dict[str, Any]) -> None:
        live = data.get("live")
        if live:
            self.live = _Live(datetime.fromisoformat(live["started_at"]), live.get("soc_start"),
                              float(live.get("kwh_vehicle") or 0), soc_end=live.get("soc_end"))
        if data.get("last_soc"):
            at, value = data["last_soc"]
            self.last_soc = (datetime.fromisoformat(at), float(value))
        self.last_home_kwh = data.get("last_home_kwh")
