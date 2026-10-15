"""Interval cost model."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.ev_charging_pilot.core.costs import (
    EnergyInterval,
    FixedPriceHistory,
    IntervalAccumulator,
    PricePoint,
    interval_start,
    session_cost,
)

TZ = ZoneInfo("Europe/Berlin")


def local(*args):
    return datetime(*args, tzinfo=TZ)


PRICES = FixedPriceHistory(
    [PricePoint(date(2026, 10, 1), 0.29), PricePoint(date(2026, 11, 1), 0.31)], TZ
)


def test_price_change_does_not_rewrite_old_months():
    assert PRICES.price_at(local(2026, 10, 31, 23, 59)) == 0.29
    assert PRICES.price_at(local(2026, 11, 1, 0, 0)) == 0.31
    assert PRICES.price_at(local(2026, 1, 1, 0, 0)) == 0.29  # before first entry


def test_session_cost_sums_intervals_across_price_change():
    intervals = [
        EnergyInterval(local(2026, 10, 31, 23, 45), local(2026, 11, 1, 0, 0), 1.0),
        EnergyInterval(local(2026, 11, 1, 0, 0), local(2026, 11, 1, 0, 15), 2.0),
    ]
    assert session_cost(intervals, PRICES) == pytest.approx(0.29 + 0.62)


def test_interval_grid():
    assert interval_start(local(2026, 10, 14, 3, 37, 12)) == local(2026, 10, 14, 3, 30)


def test_accumulator_builds_intervals_and_ignores_counter_reset():
    acc = IntervalAccumulator()
    acc.add(local(2026, 10, 14, 3, 0), 1000.0)  # baseline
    acc.add(local(2026, 10, 14, 3, 5), 1000.5)
    acc.add(local(2026, 10, 14, 3, 14), 1001.0)
    acc.add(local(2026, 10, 14, 3, 16), 1001.6)
    acc.add(local(2026, 10, 14, 3, 20), 5.0)  # reset: new baseline, no negative energy
    acc.add(local(2026, 10, 14, 3, 25), 5.4)
    assert [round(i.kwh, 3) for i in acc.intervals] == [1.0, 1.0]
    assert acc.total_kwh == pytest.approx(2.0)


def test_empty_price_history_is_rejected():
    with pytest.raises(ValueError):
        FixedPriceHistory([], TZ)
