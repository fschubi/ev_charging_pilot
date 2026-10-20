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


def run(rig, seconds, step=5):
    for _ in range(int(seconds / step)):
        rig.tick(step)


def test_lost_power_below_target_pauses_and_keeps_the_wallbox_on():
    """Frank, 20.10.2026: 60 % at a 90 % target is a pause (battery too warm/cold)."""
    rig = charging_rig()
    rig.sample(0)
    rig.tick(190)
    assert rig.state is ExecState.PAUSED
    assert "CHARGE_PAUSED" in rig.events
    run(rig, 14 * 60)
    assert rig.state is ExecState.PAUSED and "PAUSE_WAKE" not in rig.events
    run(rig, 3 * 60)  # 15 min over: one wakeup – none available here, so hold
    assert "PAUSE_WAKE" in rig.events and "PAUSE_HOLD" in rig.events
    assert rig.state is ExecState.PAUSED and rig.charger_on
    assert CommandKind.DISABLE_CHARGER not in rig.commands
    run(rig, 3600)  # and it stays like that
    assert rig.state is ExecState.PAUSED and rig.events.count("PAUSE_HOLD") == 1


def test_pause_ends_when_the_car_charges_again():
    rig = charging_rig()
    rig.sample(0)
    rig.tick(190)
    rig.sample(2300, after_s=300)
    rig.sample(2300, after_s=30)
    assert rig.state is ExecState.CHARGING
    assert "PAUSE_RESUMED" in rig.events and "CHARGE_RESUMED" in rig.events


def test_pause_wakes_once_with_ovms_then_cp_and_waits_five_minutes():
    rig = charging_rig(ovms_available=True, cp_available=True, cp_failsafe_verified=True)
    rig.sample(0)
    rig.tick(190)
    run(rig, 15 * 60 + 10)
    assert "PAUSE_WAKE" in rig.events
    run(rig, 120)
    assert CommandKind.OVMS_WAKEUP in rig.commands
    while CommandKind.CP_PULSE not in rig.commands:
        rig.tick(5)
    pulse_at = rig.now
    while "PAUSE_HOLD" not in rig.events:
        rig.tick(5)
    # 10 s pulse + 5 min waiting for the car, not the usual minute.
    assert (rig.now - pulse_at).total_seconds() >= 300
    assert rig.state is ExecState.PAUSED and rig.charger_on
    assert rig.commands.count(CommandKind.OVMS_WAKEUP) == 1
    assert rig.commands.count(CommandKind.CP_PULSE) == 1
