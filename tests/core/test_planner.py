"""Planner: windows, feasibility, DST, one-shot, override, target SOC."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from custom_components.ev_charging_pilot.core.model import Quality, Reason, Value
from custom_components.ev_charging_pilot.core.planner import (
    ManualOverride,
    OneShot,
    OverrideMode,
    ScheduleMode,
    VehicleParams,
    WeeklySchedule,
    charge_duration,
    next_departure,
    one_shot_window,
    override_wish,
    schedule_window,
    target_soc_wish,
    window_wish,
)

TZ = ZoneInfo("Europe/Berlin")
PARAMS = VehicleParams()
WORKDAYS = WeeklySchedule(id="plan-werktage")


def local(*args):
    return datetime(*args, tzinfo=TZ)


def soc(value, quality=Quality.GOOD):
    return Value(value, float(value), "ovms", local(2026, 10, 13, 18, 0), quality)


def test_next_departure_skips_weekend():
    friday_evening = local(2026, 10, 16, 20, 0)  # Fr
    assert next_departure(WORKDAYS, friday_evening, TZ) == local(2026, 10, 19, 5, 30)


def test_next_departure_same_morning_before_departure():
    assert next_departure(WORKDAYS, local(2026, 10, 14, 4, 0), TZ) == local(2026, 10, 14, 5, 30)


def test_disabled_schedule_has_no_departure():
    disabled = WeeklySchedule(id="x", enabled=False)
    assert next_departure(disabled, local(2026, 10, 14, 4, 0), TZ) is None


def test_fallback_without_soc_uses_fixed_start():
    window = schedule_window(WORKDAYS, local(2026, 10, 13, 22, 0), TZ, None, PARAMS)
    assert window.fallback_without_soc
    assert window.start == local(2026, 10, 14, 3, 0)
    assert window.departure == local(2026, 10, 14, 5, 30)


def test_fixed_start_after_departure_time_means_previous_evening():
    plan = WeeklySchedule(id="late", mode=ScheduleMode.FIXED_START,
                          charge_start_time=time(22, 0), departure_time=time(6, 0))
    window = schedule_window(plan, local(2026, 10, 13, 12, 0), TZ, None, PARAMS)
    assert window.start == local(2026, 10, 13, 22, 0)
    assert not window.fallback_without_soc


def test_departure_based_start_is_computed_backwards():
    needed_kwh, duration = charge_duration(50, 90, PARAMS)
    assert round(needed_kwh, 2) == round(0.4 * 16.7 / 0.88, 2)
    window = schedule_window(WORKDAYS, local(2026, 10, 13, 22, 0), TZ, soc(50), PARAMS)
    minutes = -(-duration.total_seconds() // 60)  # plans use whole minutes
    reserve = max(5, -(-minutes // 10))  # 10 % of the charging time, at least 5 min
    expected = local(2026, 10, 14, 5, 0) - timedelta(minutes=minutes + reserve)
    assert window.start == expected
    assert window.estimate.preferred_reachable
    assert window.estimate.expected_soc_at_departure >= 90


def test_grid_limit_of_14a_slows_charging():
    dimmed = VehicleParams(grid_limit_kw=4.2)
    assert dimmed.expected_power_kw == 4.2
    assert charge_duration(20, 90, dimmed)[1] > charge_duration(20, 90, PARAMS)[1]


def test_estimate_flags_unreachable_minimum():
    late = local(2026, 10, 14, 4, 30)
    window = schedule_window(WORKDAYS, late, TZ, soc(10), PARAMS)
    assert window.estimate.minimum_reachable is False


def test_stale_soc_falls_back():
    window = schedule_window(WORKDAYS, local(2026, 10, 13, 22, 0), TZ,
                             soc(50, Quality.STALE), PARAMS)
    assert window.fallback_without_soc
    assert window.estimate.soc_pct is None


def test_window_survives_dst_end():
    # 25.10.2026: Uhren 03:00 → 02:00. Fester Start Sonntag 01:30 (MESZ), Abfahrt 05:30 (MEZ).
    sunday = WeeklySchedule(id="so", weekdays=frozenset({"sun"}), mode=ScheduleMode.FIXED_START,
                            charge_start_time=time(1, 30), departure_time=time(5, 30))
    window = schedule_window(sunday, local(2026, 10, 24, 22, 0), TZ, None, PARAMS)
    assert window.departure.astimezone(TZ).hour == 5
    assert window.departure.astimezone(TZ).minute == 30
    # Zwischen 01:30 MESZ und 05:30 MEZ liegen fünf echte Stunden.
    assert window.departure - window.start == timedelta(hours=5)


def test_window_wish_only_while_running():
    window = schedule_window(WORKDAYS, local(2026, 10, 13, 22, 0), TZ, None, PARAMS)
    assert window_wish(window, local(2026, 10, 13, 22, 0)) is None
    wish = window_wish(window, local(2026, 10, 14, 3, 15))
    assert wish.charger_enabled is True
    assert wish.reason is Reason.SCHEDULE
    assert wish.valid_until == window.departure


def test_one_shot_expires_after_departure():
    shot = OneShot(departure_at=local(2026, 10, 14, 7, 0), mode=ScheduleMode.FIXED_START)
    assert one_shot_window(shot, local(2026, 10, 14, 3, 0), TZ, None, PARAMS).contains(
        local(2026, 10, 14, 3, 0))
    assert one_shot_window(shot, local(2026, 10, 14, 7, 0), TZ, None, PARAMS) is None


def test_override_ends_with_cable_time_or_soc():
    start = local(2026, 10, 14, 12, 0)
    until_unplugged = ManualOverride(OverrideMode.UNTIL_UNPLUGGED, start)
    assert not until_unplugged.expired(start, cable_connected=True, soc=None)
    assert until_unplugged.expired(start, cable_connected=False, soc=None)

    timed = ManualOverride(OverrideMode.DURATION, start, expires_at=start + timedelta(hours=1))
    assert timed.expired(start + timedelta(hours=1), True, None)

    to_soc = ManualOverride(OverrideMode.UNTIL_SOC, start, target_soc=80)
    assert not to_soc.expired(start, True, soc(80, Quality.LAST_KNOWN_VALID))
    assert to_soc.expired(start, True, soc(80))

    stop = override_wish(ManualOverride(OverrideMode.STOP, start))
    assert stop.charger_enabled is False


def test_target_soc_needs_good_quality_and_respects_climate_topup():
    assert target_soc_wish(soc(91), 90).charger_enabled is False
    assert target_soc_wish(soc(91, Quality.LAST_KNOWN_VALID), 90) is None
    assert target_soc_wish(soc(85), 90) is None
    assert target_soc_wish(soc(91), 90, climate_topup_active=True) is None


def test_utc_input_is_handled():
    now = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
    assert next_departure(WORKDAYS, now, TZ) == local(2026, 10, 14, 5, 30)
