"""Data quality, arbiter priority and health rules."""

from datetime import UTC, datetime, timedelta

from custom_components.ev_charging_pilot.core.arbiter import arbitrate
from custom_components.ev_charging_pilot.core.health import HealthInputs, HealthStatus, evaluate
from custom_components.ev_charging_pilot.core.model import Desired, Quality, Reason, Value
from custom_components.ev_charging_pilot.core.quality import (
    QualityRule,
    charging_conflict,
    classify,
    soc_plausible,
)

NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
SOC_RULE = QualityRule(max_age_s=600, plausible=soc_plausible)


def soc(value, age_s=0):
    return Value(raw=str(value), normalized=value, source="ovms",
                 updated_at=NOW - timedelta(seconds=age_s))


def test_fresh_value_is_good():
    assert classify(soc(72), NOW, SOC_RULE).quality is Quality.GOOD


def test_old_value_of_sleeping_car_stays_last_known_valid():
    assert classify(soc(72, age_s=3600), NOW, SOC_RULE).quality is Quality.LAST_KNOWN_VALID


def test_old_value_after_activity_is_stale():
    activity = NOW - timedelta(minutes=10)
    result = classify(soc(72, age_s=3600), NOW, SOC_RULE, last_activity_at=activity)
    assert result.quality is Quality.STALE


def test_implausible_soc_is_invalid():
    assert classify(soc(140), NOW, SOC_RULE).quality is Quality.INVALID


def test_missing_value_is_unavailable():
    assert classify(Value.unavailable("ovms"), NOW, SOC_RULE).quality is Quality.UNAVAILABLE


def test_last_known_valid_is_for_planning_but_not_for_shutdown():
    assert Quality.LAST_KNOWN_VALID.usable_for_planning
    assert not Quality.LAST_KNOWN_VALID.usable_for_control


def test_conflict_needs_two_good_values():
    halo = Value(2200, 2200.0, "halo", NOW)
    not_charging = Value(False, False, "ovms", NOW)
    assert charging_conflict(halo, not_charging, 300)
    assert not charging_conflict(halo, not_charging.with_quality(Quality.STALE), 300)
    assert not charging_conflict(halo, Value(True, True, "ovms", NOW), 300)


def test_arbiter_priority_and_default():
    schedule = Desired(True, Reason.SCHEDULE, "plan")
    target = Desired(False, Reason.TARGET_SOC_REACHED)
    override = Desired(True, Reason.OVERRIDE)
    assert arbitrate([schedule, target]) is target
    assert arbitrate([schedule, target, override]) is override
    assert arbitrate([None, None]).reason is Reason.DEFAULT_OFF
    assert arbitrate([None]).charger_enabled is False


def test_safety_lock_freezes_instead_of_switching_off():
    locked = arbitrate([Desired(True, Reason.OVERRIDE)], safety_lock=True)
    assert locked.reason is Reason.SAFETY_LOCK
    assert locked.charger_enabled is None


def test_health_shelly_unavailable_is_error():
    health = evaluate(HealthInputs(halo_available=True, cp_configured=True,
                                   shelly_available=False, cp_relay_on=None))
    assert health.status is HealthStatus.ERROR
    assert "CP_STATE_UNKNOWN" in health.reasons


def test_health_cp_open_outside_pulse_is_error_but_ok_during_pulse():
    base = dict(halo_available=True, cp_configured=True, shelly_available=True, cp_relay_on=False)
    assert evaluate(HealthInputs(**base)).status is HealthStatus.ERROR
    assert evaluate(HealthInputs(**base, cp_pulse_running=True)).status is HealthStatus.HEALTHY


def test_health_degraded_and_charger_window():
    assert evaluate(HealthInputs(halo_available=True, halo_internal_schedule_on=True)).status \
        is HealthStatus.DEGRADED
    assert evaluate(HealthInputs(halo_available=False)).status is HealthStatus.DEGRADED
    assert evaluate(HealthInputs(halo_available=False, in_charge_window=True)).status \
        is HealthStatus.ERROR


def test_health_without_cp_and_ovms_is_healthy():
    assert evaluate(HealthInputs(halo_available=True)).status is HealthStatus.HEALTHY


def test_hv_contactor_vector_uses_consumed_cycles():
    from custom_components.ev_charging_pilot.core.inputs import Inp, RawState, to_value

    def parse(state):
        return to_value(Inp.OVMS_HV_CYCLES, RawState(state=state, last_updated=NOW)).normalized

    assert parse("[300000, 299000, 1000, 2, 0]") == 1000
    assert parse("300000,299000,1000,2,0") == 1000
    assert parse("1234") == 1234



def test_hv_monitor_counts_a_falling_remaining_counter():
    """Field 18.10.2026: the OVMS integration exposes cycles *remaining* (falling)."""
    from datetime import date

    from custom_components.ev_charging_pilot.core.model import Quality, Value
    from custom_components.ev_charging_pilot.core.source_policy import HvCycleMonitor

    def v(n):
        return Value(raw=str(n), normalized=n, unit=None, source="ovms",
                     updated_at=NOW, quality=Quality.GOOD)

    mon = HvCycleMonitor(warn_per_day=2)
    day = date(2026, 10, 18)
    assert mon.update(v(194784), day, active=False) == []
    assert mon.update(v(194783), day, active=True) == []
    assert mon.today == 1
    assert mon.update(v(194782), day, active=False) == ["HV_CYCLE_WITHOUT_ACTIVITY"]
    assert "HV_CYCLES_HIGH" in mon.update(v(194781), day, active=True)
    assert mon.today == 3

def test_ovms_plug_detects_the_cable_while_the_halo_is_disabled():
    from custom_components.ev_charging_pilot.core.source_policy import plugged_in

    halo_off = Value("off", False, "halo", NOW)
    plug = Value("yes", True, "ovms", NOW)
    home = Value("home", True, "ovms", NOW)
    away = Value("not_home", False, "ovms", NOW)
    none = Value.unavailable("none")
    assert plugged_in(halo_off, plug, home).normalized is True
    assert plugged_in(halo_off, plug, none).normalized is True
    # Plugged in at a public charger: not the wallbox cable.
    assert plugged_in(halo_off, plug, away).normalized is False
    assert plugged_in(halo_off, Value("no", False, "ovms", NOW), home) is halo_off
    # Without OVMS the Halo decides alone; a Halo "on" always wins.
    assert plugged_in(halo_off, none, home) is halo_off
    halo_on = Value("on", True, "halo", NOW)
    assert plugged_in(halo_on, Value("no", False, "ovms", NOW), away) is halo_on
    assert plugged_in(none, Value("no", False, "ovms", NOW), home).normalized is False
