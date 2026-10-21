"""Automatic detection of charges away from home (§10.5, formerly "später").

Two independent signals, both only from data that arrives anyway – the car is
never woken for this (§1.1 rule 6):

1. **Live:** OVMS reports "charging" – or a charge power, which it sends far more
   often – while the cable at home is not plugged in. The car's own "energy of
   this charge" gives the amount; without it the charge power is integrated.
   (Field 21.10.2026: OVMS sent "charging" once at 16:01 and then nothing for 26
   minutes – the value aged and the live detection never started.)
2. **SOC jump:** the next GOOD SOC after a gap is clearly higher than the last
   one, but the Halo counter explains only a small part of it.

Every detection is an ESTIMATED external charge; the user can complete the
cost and provider later (``add_external_charge`` with the same id).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
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


def _charge_battery_kwh(readings: tuple[float, float, float] | None) -> float | None:
    """Energy into the battery from OVMS "energy of this charge" (first, lowest, last).

    The counter restarts at 0 with each charge: once it dropped (or started near 0)
    the last value is the whole charge; otherwise only its rise belongs to it
    (field 21.10.2026: 8.34 from the night, then 0.36 … 4.35 kWh at Lidl).
    """
    if readings is None:
        return None
    first, lowest, last = readings
    if lowest < first or first < 0.5:
        return last if last > 0 else None
    return last - first if last > first else None


@dataclass(slots=True)
class _Live:
    started_at: datetime
    soc_start: float | None
    kwh_vehicle: float = 0.0
    last_power: tuple[datetime, float] | None = None
    not_charging_since: datetime | None = None
    soc_end: float | None = None
    # OVMS "energy of this charge": first, lowest and latest reading.
    charge_kwh: tuple[float, float, float] | None = None
    power_w: float | None = None


class ExternalChargeDetector:
    def __init__(self, *, capacity_kwh: float, efficiency: float, min_kwh: float,
                 soc_jump_pct: float, price_eur_kwh: float, threshold_w: float,
                 tz: tzinfo = UTC) -> None:
        self.tz = tz
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
        charge_energy: Value | None = None,
    ) -> list[ExternalCharge]:
        found: list[ExternalCharge] = []
        halo_w = _num(halo_power) or 0.0
        home_delivering = cable_connected is True and halo_w > self.threshold_w
        power_w = float(vehicle_power.normalized) if vehicle_power.quality is Quality.GOOD \
            and vehicle_power.normalized is not None else None
        charging = (vehicle_charging.quality is Quality.GOOD
                    and bool(vehicle_charging.normalized)) \
            or (power_w is not None and power_w > self.threshold_w)
        soc_now = soc.quality is Quality.GOOD and soc.normalized is not None

        # --- 1. live detection – only while the cable at home is known to be unplugged.
        # If the wallbox cloud is down (cable unknown, no power) a home charge would
        # otherwise look like an external one.
        away = cable_connected is False
        if charging and away:
            if self.live is None:
                self.live = _Live(started_at=now, soc_start=self.last_soc[1]
                                  if self.last_soc else _num(soc))
            self.live.not_charging_since = None
            self.live.power_w = power_w
            self._integrate(now, vehicle_power)
            kwh = _num(charge_energy)
            if kwh is not None:
                seen = self.live.charge_kwh or (kwh, kwh, kwh)
                self.live.charge_kwh = (seen[0], min(seen[1], kwh), kwh)
            if soc_now:
                self.live.soc_end = float(soc.normalized)
        elif self.live is not None:
            self.live.power_w = None
            if self.live.not_charging_since is None:
                self.live.not_charging_since = now
            if now - self.live.not_charging_since >= END_GRACE or home_delivering:
                charge = self._finish_live(now)
                if charge is not None:
                    found.append(charge)

        # --- 2. SOC jump detection
        home_kwh = _num(halo_total)
        # A car that still says "charging" (even an aged value) is no finished charge.
        still_charging = bool(vehicle_charging.normalized) \
            and vehicle_charging.quality.usable_for_planning
        if soc_now and self.live is None and not still_charging:
            current = float(soc.normalized)
            # Without the home counter at both ends the jump cannot be explained – skip it.
            # Plugged in at home: a jump is a home charge (perhaps with a lagging wallbox
            # counter), never an external one. The counter must be fresh (GOOD) to explain.
            if self.last_soc is not None and current - self.last_soc[1] >= self.soc_jump \
                    and not charging and cable_connected is not True \
                    and halo_total.quality is Quality.GOOD and home_kwh is not None \
                    and self.last_home_kwh is not None:
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
        grid = None
        battery = _charge_battery_kwh(live.charge_kwh)
        if battery is not None:
            grid = battery / self.efficiency
        elif live.kwh_vehicle > 0:
            grid = live.kwh_vehicle / self.efficiency
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
            date=end.astimezone(self.tz).date(),  # the local day, not the UTC one
            source="public",
            energy_kwh=kwh,
            price_eur_kwh=self.price,
            soc_before=soc_before,
            soc_after=soc_after,
            note=f"automatisch erkannt ({method}), "
                 f"{start.astimezone(self.tz):%H:%M}–{end.astimezone(self.tz):%H:%M}",
            detected=True,
            quality="ESTIMATED",
        )

    @property
    def status(self) -> dict[str, Any] | None:
        """The external charge running right now, for the cockpit."""
        live = self.live
        if live is None or live.not_charging_since is not None:
            return None
        battery = _charge_battery_kwh(live.charge_kwh) or live.kwh_vehicle or None
        return {"since": live.started_at.isoformat(), "power_w": live.power_w,
                "battery_kwh": round(battery, 2) if battery else None,
                "soc_start": live.soc_start, "soc": live.soc_end}

    def as_dict(self) -> dict[str, Any]:
        live = None
        if self.live is not None:
            live = {
                "started_at": self.live.started_at.isoformat(),
                "soc_start": self.live.soc_start,
                "kwh_vehicle": self.live.kwh_vehicle,
                "soc_end": self.live.soc_end,
                "charge_kwh": list(self.live.charge_kwh) if self.live.charge_kwh else None,
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
                              float(live.get("kwh_vehicle") or 0), soc_end=live.get("soc_end"),
                              charge_kwh=tuple(live["charge_kwh"]) if live.get("charge_kwh")
                              else None)
        if data.get("last_soc"):
            at, value = data["last_soc"]
            self.last_soc = (datetime.fromisoformat(at), float(value))
        self.last_home_kwh = data.get("last_home_kwh")
