"""Dynamic prices (Tibber & co.) and the "cheapest intervals" planner.

The cost model was interval-based from the start (§11), so a dynamic tariff
is just another price source. Every common HA price format is understood:

* Tibber service ``tibber.get_prices`` → ``{"prices": {home: [{start_time, price}]}}``
* Nordpool-style attributes ``raw_today`` / ``raw_tomorrow`` → ``[{start, end, value}]``
* EPEX-Spot-style attribute ``data`` → ``[{start_time, end_time, price_per_kwh}]``
* ENTSO-e-style attributes ``prices_today`` / ``prices_tomorrow`` / ``prices``
  → ``[{time, price}]``
* Pairs ``[[timestamp, price], …]`` in any list attribute (e.g. ``daten``), with
  epoch seconds/milliseconds or ISO times
* Generic attributes ``prices`` / ``today`` + ``tomorrow`` (dicts or plain numbers)
* Anything else: the first list attribute that yields prices

Prices are always € per kWh. Values above 5 are taken as ct/kWh and divided by 100;
a unit in €/MWh is divided by 1000.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

CENT_THRESHOLD = 5.0


def parse_price_input(text: str | None) -> float | None:
    """€/kWh from a typed answer: "0,59", "0.59 €", "59 ct", "59" (cents)."""
    if not text:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if match is None:
        return None
    value = float(match.group().replace(",", "."))
    if value > 5:  # cents
        value /= 100
    return round(value, 4) if 0 < value < 3 else None


def parse_price_list(text: str | None) -> tuple[float, ...]:
    """Quick-pick prices from a setting like "0,39; 0,49; 0,59" (at most four)."""
    prices = [parse_price_input(part) for part in re.split(r"[;\s/|]+", text or "")]
    return tuple(dict.fromkeys(p for p in prices if p is not None))[:4]


@dataclass(frozen=True, slots=True)
class PriceSlot:
    start: datetime
    end: datetime
    eur_per_kwh: float

    def as_dict(self) -> dict[str, Any]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(),
                "eur_per_kwh": round(self.eur_per_kwh, 5)}


def _eur(value: Any, mwh: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if mwh:
        return number / 1000
    return number / 100 if number > CENT_THRESHOLD else number


def _time(value: Any, tz: ZoneInfo) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        # Epoch seconds or milliseconds (JavaScript-style charts).
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, tz)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=tz)


def _close(slots: list[tuple[datetime, datetime | None, float]]) -> list[PriceSlot]:
    """Fill missing slot ends from the next start (or the typical slot length)."""
    slots.sort(key=lambda s: s[0])
    out: list[PriceSlot] = []
    for index, (start, end, price) in enumerate(slots):
        if end is None:
            if index + 1 < len(slots):
                end = slots[index + 1][0]
            elif out:
                end = start + (out[-1].end - out[-1].start)
            else:
                end = start + timedelta(hours=1)
        if end > start:
            out.append(PriceSlot(start, end, price))
    return out


START_KEYS = ("start", "start_time", "startsAt", "time", "datetime", "from", "timestamp")
END_KEYS = ("end", "end_time", "endsAt", "till", "to")
PRICE_KEYS = ("value", "price", "total", "price_per_kwh", "price_eur_kwh", "price_ct_per_kwh",
              "marketprice")


def _from_dicts(items: Iterable[Any], tz: ZoneInfo, mwh: bool = False) -> list[tuple]:
    found = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            # [timestamp, price] pairs.
            start, price = _time(item[0], tz), _eur(item[1], mwh)
            if start is not None and price is not None:
                found.append((start, None, price))
            continue
        if not isinstance(item, dict):
            continue
        start = _time(next((item[k] for k in START_KEYS if item.get(k) is not None), None), tz)
        end_raw = next((item[k] for k in END_KEYS if item.get(k)), None)
        end = _time(end_raw, tz) if end_raw else None
        price = None
        for key in PRICE_KEYS:
            if key in item:
                price = _eur(item[key], mwh)
                break
        if start is not None and price is not None:
            found.append((start, end, price))
    return found


def _from_numbers(values: Sequence[Any], day: date, tz: ZoneInfo,
                  mwh: bool = False) -> list[tuple]:
    """A plain list of prices for one day: 24 (hourly), 96 (15 min) or with DST 23/25."""
    numbers = [_eur(v, mwh) for v in values]
    if not numbers or any(n is None for n in numbers):
        return []
    slots_per_hour = 4 if len(numbers) >= 92 else 1
    step = timedelta(minutes=60 // slots_per_hour)
    start = datetime.combine(day, time(0), tzinfo=tz).astimezone(ZoneInfo("UTC"))
    return [(start + i * step, start + (i + 1) * step, n) for i, n in enumerate(numbers)]


KNOWN_LISTS = ("raw_today", "raw_tomorrow", "data", "prices", "forecast", "prices_today",
               "prices_tomorrow")


def parse_price_attributes(attributes: dict[str, Any], tz: ZoneInfo,
                           today: date) -> list[PriceSlot]:
    unit = str(attributes.get("unit_of_measurement") or attributes.get("unit") or "")
    mwh = "MWh" in unit
    found: list[tuple] = []
    for key in KNOWN_LISTS:
        value = attributes.get(key)
        if isinstance(value, list):
            found += _from_dicts(value, tz, mwh)
    if not found:
        for key, day in (("today", today), ("tomorrow", today + timedelta(days=1))):
            value = attributes.get(key)
            if isinstance(value, list) and value:
                if isinstance(value[0], (dict, list, tuple)):
                    found += _from_dicts(value, tz, mwh)
                else:
                    found += _from_numbers(value, day, tz, mwh)
    if not found:
        # Unknown attribute name (e.g. "daten"): the first list that yields prices.
        for key, value in attributes.items():
            if key not in KNOWN_LISTS and isinstance(value, list) and len(value) >= 4:
                found = _from_dicts(value, tz, mwh)
                if found:
                    break
    return _close(_dedupe(found))


def describe_prices(slots: Sequence[PriceSlot], tz: ZoneInfo) -> dict[str, Any]:
    """Short summary for the settings check: count, range, cheapest slot."""
    if not slots:
        return {"slots": 0}
    cheapest = min(slots, key=lambda s: s.eur_per_kwh)
    return {
        "slots": len(slots),
        "from": slots[0].start.astimezone(tz).isoformat(),
        "until": slots[-1].end.astimezone(tz).isoformat(),
        "minutes": round((slots[0].end - slots[0].start).total_seconds() / 60),
        "min_eur_kwh": round(min(s.eur_per_kwh for s in slots), 4),
        "max_eur_kwh": round(max(s.eur_per_kwh for s in slots), 4),
        "cheapest_at": cheapest.start.astimezone(tz).isoformat(),
    }


def parse_tibber_response(response: dict[str, Any], tz: ZoneInfo) -> list[PriceSlot]:
    homes = (response or {}).get("prices") or {}
    first = next(iter(homes.values()), []) if isinstance(homes, dict) else homes
    return _close(_dedupe(_from_dicts(first, tz)))


def _dedupe(slots: list[tuple]) -> list[tuple]:
    seen: dict[datetime, tuple] = {}
    for slot in slots:
        seen[slot[0]] = slot
    return list(seen.values())


class PriceSchedule:
    """Known price slots; outside of them the caller falls back to the fixed price."""

    def __init__(self, slots: Iterable[PriceSlot]) -> None:
        self.slots = sorted(slots, key=lambda s: s.start)
        self._starts = [s.start for s in self.slots]

    def __bool__(self) -> bool:
        return bool(self.slots)

    def slot_at(self, moment: datetime) -> PriceSlot | None:
        index = bisect_right(self._starts, moment) - 1
        if index >= 0 and self.slots[index].start <= moment < self.slots[index].end:
            return self.slots[index]
        return None

    def price_at(self, moment: datetime) -> float | None:
        slot = self.slot_at(moment)
        return slot.eur_per_kwh if slot else None

    def covers(self, start: datetime, end: datetime) -> bool:
        """Is every moment of [start, end) priced (no gaps)?"""
        moment = start
        while moment < end:
            slot = self.slot_at(moment)
            if slot is None:
                return False
            moment = slot.end
        return True

    @property
    def last_end(self) -> datetime | None:
        return self.slots[-1].end if self.slots else None

    def average(self, start: datetime, end: datetime) -> float | None:
        cost = self.energy_cost(start, end, 1.0)
        hours = (end - start).total_seconds() / 3600
        return cost / hours if cost is not None and hours > 0 else None

    def energy_cost(self, start: datetime, end: datetime, kw: float) -> float | None:
        """€ for drawing ``kw`` from start to end (None if not fully priced)."""
        if not self.covers(start, end):
            return None
        total, moment = 0.0, start
        while moment < end:
            slot = self.slot_at(moment)
            until = min(slot.end, end)
            total += slot.eur_per_kwh * kw * (until - moment).total_seconds() / 3600
            moment = until
        return total


Block = tuple[datetime, datetime]


def cheapest_blocks(schedule: PriceSchedule, earliest: datetime, latest: datetime,
                    duration: timedelta, kw: float, max_blocks: int = 1
                    ) -> tuple[list[Block], float] | None:
    """Cheapest way to fit ``duration`` of charging into [earliest, latest).

    The result has at most ``max_blocks`` contiguous blocks – every extra block
    can mean another wakeup of a sleeping car (HV contactor cycles, §1.1), so
    the default is one block. Returns None when the prices do not cover the
    range or the time is too short.
    """
    if duration <= timedelta(0):
        return [], 0.0
    if latest - earliest < duration or not schedule.covers(earliest, latest):
        return None
    candidates = sorted({earliest, latest - duration,
                         *(s.start for s in schedule.slots if earliest <= s.start <= latest),
                         *(s.end - duration for s in schedule.slots
                           if earliest <= s.end - duration <= latest - duration)})
    candidates = [c for c in candidates if earliest <= c <= latest - duration]

    best: tuple[list[Block], float] | None = None
    for start in candidates:
        cost = schedule.energy_cost(start, start + duration, kw)
        if cost is not None and (best is None or cost < best[1] - 1e-9):
            best = ([(start, start + duration)], cost)

    if max_blocks >= 2:
        step = min((s.end - s.start for s in schedule.slots), default=timedelta(hours=1))
        first_len = step
        while first_len < duration:
            second_len = duration - first_len
            for a in candidates:
                a_end = a + first_len
                if a_end > latest:
                    continue
                cost_a = schedule.energy_cost(a, a_end, kw)
                if cost_a is None:
                    continue
                for b in (c for c in candidates if c >= a_end + step):
                    if b + second_len > latest:
                        continue
                    cost_b = schedule.energy_cost(b, b + second_len, kw)
                    if cost_b is None:
                        continue
                    total = cost_a + cost_b
                    if best is None or total < best[1] - 1e-6:
                        best = ([(a, a_end), (b, b + second_len)], total)
            first_len += step
    return best
