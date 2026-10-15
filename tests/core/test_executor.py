"""Executor scenarios: start, wakeup cascade, CP masking, failures, restart."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.ev_charging_pilot.core.executor import (
    ExecState,
    Executor,
    ExecutorConfig,
    Snapshot,
)
from custom_components.ev_charging_pilot.core.health import Health, HealthStatus
from custom_components.ev_charging_pilot.core.model import Desired, Reason, Value
from custom_components.ev_charging_pilot.core.ports import CommandKind

T0 = datetime(2026, 10, 14, 3, 0, tzinfo=UTC)
HEALTHY = Health(HealthStatus.HEALTHY)
ON = Desired(True, Reason.SCHEDULE, "plan", T0 + timedelta(hours=2))
OFF = Desired(False, Reason.DEFAULT_OFF)


class Rig:
    """A fake car + Halo + Shelly driven tick by tick."""

    def __init__(self, **config) -> None:
        self.ex = Executor(ExecutorConfig(**config))
        self.now = T0
        self.desired = ON
        self.health = HEALTHY
        self.cable = True
        self.charger_on = False
        self.power = 0.0
        self.power_at = T0
        self.status = "Available"
        self.cp_relay = True
        self.vehicle_finished = False
        self.commands: list[CommandKind] = []
        self.events: list[str] = []

    def snapshot(self) -> Snapshot:
        return Snapshot(
            now=self.now,
            desired=self.desired,
            health=self.health,
            cable_connected=Value(self.cable, self.cable, "halo", self.now),
            charger_on=Value(self.charger_on, self.charger_on, "halo", self.now),
            power_w=Value(self.power, self.power, "halo", self.power_at),
            charger_status=Value(self.status, self.status, "halo", self.now),
            cp_relay_on=Value(self.cp_relay, self.cp_relay, "shelly", self.now),
            vehicle_charge_finished=self.vehicle_finished,
        )

    def tick(self, seconds: float = 0) -> list[CommandKind]:
        self.now += timedelta(seconds=seconds)
        result = self.ex.step(self.snapshot())
        kinds = [c.kind for c in result.commands]
        self.commands += kinds
        self.events += [e.code for e in result.events]
        for kind in kinds:  # the Halo obeys immediately in this rig
            if kind is CommandKind.ENABLE_CHARGER:
                self.charger_on = True
            elif kind is CommandKind.DISABLE_CHARGER:
                self.charger_on = False
        return kinds

    def sample(self, watts: float, after_s: float = 10) -> list[CommandKind]:
        """A new Halo power reading arrives ``after_s`` seconds later."""
        self.now += timedelta(seconds=after_s)
        self.power = watts
        self.power_at = self.now
        return self.tick()

    @property
    def state(self) -> ExecState:
        return self.ex.state


def test_happy_path_enable_and_stable_charge():
    rig = Rig()
    assert rig.tick() == [CommandKind.ENABLE_CHARGER]
    assert rig.state is ExecState.ENABLING
    rig.tick(5)
    assert rig.state is ExecState.WAITING_FOR_CHARGE
    rig.sample(2300)
    assert rig.state is ExecState.CHARGE_STABILIZING
    rig.sample(2300, after_s=25)
    assert rig.state is ExecState.CHARGING
    assert "CHARGE_STABLE" in rig.events
    assert rig.ex.session_id is not None


def test_single_sample_is_not_yet_stable():
    rig = Rig(stable_samples=2, charging_stable_min_s=20)
    rig.tick()
    rig.tick(5)
    rig.sample(2300)
    rig.sample(2300, after_s=5)  # two samples, but only 5 s apart
    assert rig.state is ExecState.CHARGE_STABILIZING


def test_power_dip_during_stabilizing_returns_to_waiting():
    rig = Rig()
    rig.tick()
    rig.tick(5)
    rig.sample(2300)
    rig.sample(0)
    assert rig.state is ExecState.WAITING_FOR_CHARGE


def test_cascade_ovms_then_cp_then_failure():
    rig = Rig(ovms_available=True, cp_available=True, cp_failsafe_verified=True)
    rig.tick()
    rig.tick(5)
    assert rig.tick(60) == [CommandKind.OVMS_WAKEUP]
    assert rig.state is ExecState.WAKEUP_OVMS
    # ovms_wait (45 s) is over, but the gap between wakeups (120 s) is not.
    assert rig.tick(50) == []
    assert rig.state is ExecState.WAKEUP_OVMS
    assert rig.tick(75) == [CommandKind.CP_PULSE]
    assert rig.state is ExecState.WAKEUP_CP
    rig.tick(20)  # restore check passes, relay is on
    assert "CP_PULSE_DONE" in rig.events
    rig.tick(60)
    assert rig.state is ExecState.START_FAILED
    assert rig.ex.failure_code == "CHARGE_START_FAILED"
    # No second attempt in the same window.
    assert rig.tick(600) == []


def test_cp_wakeup_locked_without_verified_failsafe():
    rig = Rig(cp_available=True, cp_failsafe_verified=False)
    rig.tick()
    rig.tick(5)
    rig.tick(60)
    assert CommandKind.CP_PULSE not in rig.commands
    assert rig.state is ExecState.START_FAILED


def test_cp_wakeup_succeeds_and_unplug_is_masked():
    rig = Rig(cp_available=True, cp_failsafe_verified=True)
    rig.tick()
    rig.tick(5)
    assert rig.tick(60) == [CommandKind.CP_PULSE]
    rig.cp_relay = False
    rig.cable = False  # Halo sees state A while the pilot is open
    rig.tick(5)
    assert rig.state is ExecState.WAKEUP_CP
    rig.cp_relay = True
    rig.cable = True
    rig.sample(2300, after_s=10)
    rig.sample(2300, after_s=25)
    assert rig.state is ExecState.CHARGING
    assert "CABLE_DISCONNECTED" not in rig.events


def test_real_unplug_after_mask_is_detected():
    rig = Rig(cp_available=True, cp_failsafe_verified=True)
    rig.tick()
    rig.tick(5)
    rig.tick(60)
    rig.cable = False
    rig.tick(45)  # pulse 10 s + grace 30 s is over
    assert rig.state is ExecState.DISCONNECTED


def test_cp_not_restored_raises_and_closes():
    rig = Rig(cp_available=True, cp_failsafe_verified=True)
    rig.tick()
    rig.tick(5)
    rig.tick(60)
    rig.cp_relay = False
    kinds = rig.tick(16)
    assert CommandKind.CP_CLOSE in kinds
    assert rig.ex.cp_not_restored
    assert "CP_NOT_RESTORED" in rig.events


def test_health_error_freezes_switching_but_closes_cp():
    rig = Rig(cp_available=True)
    rig.health = Health(HealthStatus.ERROR, ("CP_OPEN",))
    rig.cp_relay = False
    assert rig.tick() == [CommandKind.CP_CLOSE]
    assert rig.tick(5) == []  # rate limited
    assert rig.tick(30) == [CommandKind.CP_CLOSE]
    assert CommandKind.ENABLE_CHARGER not in rig.commands


def test_switch_cooldown_defers_second_switch():
    rig = Rig(min_switch_interval_s=120)
    rig.tick()
    rig.tick(5)
    rig.desired = OFF
    assert rig.tick(10) == []
    assert "SWITCH_CYCLE_VIOLATION" in rig.events
    assert rig.tick(110) == [CommandKind.DISABLE_CHARGER]
    rig.tick(5)
    assert rig.state is ExecState.COOLDOWN


def charging_rig(**config) -> Rig:
    rig = Rig(**config)
    rig.tick()
    rig.tick(5)
    rig.sample(2300)
    rig.sample(2300, after_s=25)
    assert rig.state is ExecState.CHARGING
    return rig


def test_charge_end_reported_by_vehicle():
    rig = charging_rig()
    rig.vehicle_finished = True
    rig.sample(0)
    assert rig.state is ExecState.CHARGE_ENDED


def test_charge_end_reported_by_halo_status():
    rig = charging_rig(finished_statuses=("Finished",))
    rig.status = "Finished"
    rig.sample(0)
    assert rig.state is ExecState.CHARGE_ENDED


def test_interruption_gets_one_restart_then_fails():
    rig = charging_rig()
    rig.sample(0)
    rig.tick(190)
    assert rig.state is ExecState.INTERRUPTED
    rig.tick(1)
    assert rig.state is ExecState.WAITING_FOR_CHARGE
    rig.tick(61)
    assert rig.state is ExecState.START_FAILED
    assert rig.ex.failure_code == "CHARGE_INTERRUPTED"


def test_target_soc_switches_off_and_ends_session():
    rig = charging_rig()
    rig.desired = Desired(False, Reason.TARGET_SOC_REACHED)
    rig.tick(200)
    assert rig.commands[-1] is CommandKind.DISABLE_CHARGER
    assert "SESSION_END" in rig.events


def test_new_window_clears_start_failed():
    rig = Rig()
    rig.tick()
    rig.tick(5)
    rig.tick(60)
    assert rig.state is ExecState.START_FAILED
    rig.desired = Desired(True, Reason.SCHEDULE, "plan", T0 + timedelta(days=1))
    rig.tick(1)
    assert rig.state is ExecState.WAITING_FOR_CHARGE


def test_unplug_clears_failure():
    rig = Rig()
    rig.tick()
    rig.tick(5)
    rig.tick(60)
    rig.cable = False
    rig.tick(1)
    assert rig.state is ExecState.DISCONNECTED
    assert rig.ex.failure_code is None


def test_restart_derives_state_and_keeps_attempts():
    rig = Rig(ovms_available=True)
    rig.tick()
    rig.tick(5)
    rig.tick(60)
    assert rig.state is ExecState.WAKEUP_OVMS
    saved = rig.ex.as_dict()

    fresh = Rig(ovms_available=True)
    fresh.now = rig.now
    fresh.charger_on = True
    fresh.ex.restore(saved)
    fresh.tick()
    # The wakeup in flight is not resumed; it is re-evaluated from scratch.
    assert fresh.state is ExecState.WAITING_FOR_CHARGE
    fresh.tick(130)
    assert CommandKind.OVMS_WAKEUP not in fresh.commands
    assert fresh.state is ExecState.START_FAILED


def test_restart_while_charging():
    rig = Rig()
    rig.charger_on = True
    rig.power = 2300
    rig.tick()
    assert rig.state is ExecState.CHARGING


def test_disconnected_halo_left_on_is_switched_off():
    rig = Rig()
    rig.cable = False
    rig.charger_on = True
    rig.desired = OFF
    assert rig.tick() == [CommandKind.DISABLE_CHARGER]
    assert rig.state is ExecState.DISCONNECTED


def test_reset_clears_repeated_failures():
    rig = Rig()
    rig.tick()
    rig.tick(5)
    rig.tick(60)
    assert rig.ex.consecutive_start_failures == 1
    rig.ex.reset(rig.now)
    assert rig.ex.consecutive_start_failures == 0
    assert rig.state is ExecState.IDLE
