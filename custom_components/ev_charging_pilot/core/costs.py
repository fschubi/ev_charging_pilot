"""Interval-based cost model (§11).

v1 uses a fixed price with a validity history, but every cost is already a
sum over energy intervals – a dynamic tariff later is just another price
source, not a rewrite.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class PricePoint:
    valid_from: date
    eur_per_kwh: float


@dataclass(frozen=True, slots=True)
class EnergyInterval:
    start: datetime
    end: datetime
    kwh: float


class FixedPriceHistory:
    """Price per kWh with "valid from" dates, so a change never rewrites old months."""

    def __init__(self, points: Iterable[PricePoint], tz: ZoneInfo) -> None:
        self._points = sorted(points, key=lambda p: p.valid_from)
        if not self._points:
            raise ValueError("price history needs at least one entry")
        self._dates = [p.valid_from for p in self._points]
        self._tz = tz

    def price_at(self, moment: datetime) -> float:
        day = moment.astimezone(self._tz).date()
        index = bisect_right(self._dates, day) - 1
        # Energy before the first entry is billed at the oldest known price.
        return self._points[max(index, 0)].eur_per_kwh


def session_cost(intervals: Sequence[EnergyInterval], prices: FixedPriceHistory) -> float:
    """Kosten = Σ E_i · p_i, priced at the start of each interval."""
    return round(sum(i.kwh * prices.price_at(i.start) for i in intervals), 4)


def interval_start(moment: datetime, interval_min: int = 15) -> datetime:
    """Floor ``moment`` to the interval grid (aligned to the full hour)."""
    floored = moment.replace(second=0, microsecond=0)
    return floored - timedelta(minutes=floored.minute % interval_min)


# Above any home wallbox (Halo: 11 kW), plus a margin for cloud polls that arrive
# late and in bursts – far below the meter reading a glitch jumps back to.
MAX_PLAUSIBLE_KW = 25.0
PLAUSIBLE_SLACK_KWH = 1.0


def plausible_rise(delta_kwh: float, since: datetime | None, until: datetime) -> bool:
    """Can a counter rise by ``delta_kwh`` between two readings? Unknown time: yes."""
    if since is None:
        return True
    hours = max(0.0, (until - since).total_seconds() / 3600)
    return delta_kwh <= MAX_PLAUSIBLE_KW * hours + PLAUSIBLE_SLACK_KWH


class IntervalAccumulator:
    """Turns a monotonically rising energy counter into 15-min intervals.

    Feed it every reading of the Halo total-energy counter; it attributes
    each delta to the interval in which the reading arrived. A falling
    counter (meter reset, replaced device) starts a new baseline instead of
    producing negative energy. A rise faster than any wallbox can deliver is a
    glitch, too: after a single 0 reading the true counter returns, and that
    jump back must not count as the whole meter reading (review 24.10.2026).
    """

    def __init__(self, interval_min: int = 15) -> None:
        self.interval_min = interval_min
        self.intervals: list[EnergyInterval] = []
        self.last_kwh: float | None = None
        # When the counter last changed: a cloud counter repeats its value between
        # polls, so the time for a rise counts from the previous change.
        self.last_at: datetime | None = None

    def add(self, moment: datetime, total_kwh: float) -> None:
        last, last_at = self.last_kwh, self.last_at
        if total_kwh == last:
            return
        self.last_kwh, self.last_at = total_kwh, moment
        if last is None or total_kwh < last:
            return
        delta = total_kwh - last
        if delta <= 0 or not plausible_rise(delta, last_at, moment):
            return
        start = interval_start(moment, self.interval_min)
        if self.intervals and self.intervals[-1].start == start:
            last = self.intervals[-1]
            self.intervals[-1] = EnergyInterval(last.start, last.end, round(last.kwh + delta, 6))
        else:
            end = start + timedelta(minutes=self.interval_min)
            self.intervals.append(EnergyInterval(start, end, round(delta, 6)))

    @property
    def total_kwh(self) -> float:
        return round(sum(i.kwh for i in self.intervals), 6)
