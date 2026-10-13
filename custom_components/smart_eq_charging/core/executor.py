"""Executor: reconcile the desired state with reality, incl. wakeup cascade (§6).

``Executor.step`` takes one immutable :class:`Snapshot` and returns the
commands to dispatch plus the events to log. It never performs I/O. Because
all timing comes from ``snapshot.now``, a replay of recorded snapshots runs
the identical logic at test speed.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from .health import Health, HealthStatus
from .model import Category, Desired, Event, Quality, Severity, Value
from .ports import Command, CommandKind


class ExecState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    IDLE = "IDLE"
    ENABLING = "ENABLING"
    WAITING_FOR_CHARGE = "WAITING_FOR_CHARGE"
    CHARGE_STABILIZING = "CHARGE_STABILIZING"
    WAKEUP_OVMS = "WAKEUP_OVMS"
    WAKEUP_CP = "WAKEUP_CP"
    CHARGING = "CHARGING"
    CHARGE_ENDED = "CHARGE_ENDED"
    INTERRUPTED = "INTERRUPTED"
    DISABLING = "DISABLING"
    COOLDOWN = "COOLDOWN"
    START_FAILED = "START_FAILED"


# States in which the executor is still trying to get energy flowing.
_STARTING = (ExecState.WAITING_FOR_CHARGE, ExecState.WAKEUP_OVMS, ExecState.WAKEUP_CP)

# How often a "close the CP" command is repeated while the relay stays open.
CP_CLOSE_RETRY_S = 30.0


@dataclass(frozen=True, slots=True)
class ExecutorConfig:
    """Timing and limits (§6.2, §6.4). Provisional until Phase 0 measured them."""

    power_threshold_w: float = 300.0
    stable_samples: int = 2
    charging_stable_min_s: float = 20.0
    charging_loss_timeout_s: float = 120.0
    start_detection_wait_s: float = 60.0
    ovms_wait_s: float = 45.0
    post_cp_wait_s: float = 60.0
    max_ovms_attempts_per_window: int = 1
    max_cp_attempts_per_window: int = 1
    min_gap_between_wakeups_s: float = 120.0
    min_switch_interval_s: float = 120.0
    confirm_timeout_s: float = 90.0
    max_confirm_attempts: int = 3
    cp_pulse_s: int = 10
    cp_mask_grace_s: float = 30.0
    cp_restore_check_extra_s: float = 5.0
    ovms_available: bool = False
    cp_available: bool = False
    cp_failsafe_verified: bool = False
    finished_statuses: Collection[str] = ()


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything the executor may look at for one step."""

    now: datetime
    desired: Desired
    health: Health
    cable_connected: Value
    charger_on: Value
    power_w: Value
    charger_status: Value | None = None
    cp_relay_on: Value | None = None
    vehicle_charging: Value | None = None
    vehicle_charge_finished: bool = False


@dataclass(slots=True)
class StepResult:
    commands: list[Command] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


@dataclass(slots=True)
class WindowAttempts:
    ovms: int = 0
    cp: int = 0
    restart_used: bool = False


def _flag(value: Value | None) -> bool | None:
    if value is None or not value.available or value.normalized is None:
        return None
    return bool(value.normalized)


class Executor:
    def __init__(self, config: ExecutorConfig) -> None:
        self.config = config
        self.state: ExecState | None = None
        self.state_since: datetime | None = None
        self.failure_code: str | None = None
        self.cp_not_restored = False
        self.consecutive_start_failures = 0
        self.session_id: str | None = None
        self._attempts: dict[str, WindowAttempts] = {}
        self._failed_window: str | None = None
        self._last_switch_at: datetime | None = None
        self._last_wakeup_at: datetime | None = None
        self._mask_until: datetime | None = None
        self._pulse_check_at: datetime | None = None
        self._confirm_attempts = 0
        self._resume: tuple[ExecState, datetime] | None = None
        self._below_since: datetime | None = None
        self._last_sample_at: datetime | None = None
        self._run_count = 0
        self._run_start: datetime | None = None
        self._last_sample_w: float | None = None
        self._violation_reported_for: str | None = None
        self._last_cp_close_at: datetime | None = None
        self._result = StepResult()

    # ------------------------------------------------------------------ API

    def step(self, snap: Snapshot) -> StepResult:
        self._result = StepResult()
        now = snap.now
        self._ingest_power(snap.power_w)
        self._check_cp_restored(snap)

        if self.state is None:
            self._initial_state(snap)

        cable = _flag(snap.cable_connected)
        if cable is False and not self.cp_masked(now):
            if self.state is not ExecState.DISCONNECTED:
                self._on_unplugged(now)
        elif cable is True and self.state is ExecState.DISCONNECTED:
            self._go(ExecState.IDLE, now, "CABLE_CONNECTED", "Kabel gesteckt", Category.CHARGING)

        if snap.desired.charger_enabled is None or snap.health.status is HealthStatus.ERROR:
            self._safety_hold(snap)
            return self._result

        handler = getattr(self, f"_in_{self.state.lower()}")
        handler(snap)
        return self._result

    @property
    def starting(self) -> bool:
        """Is the executor currently trying to get energy flowing?"""
        return self.state in _STARTING

    def cp_masked(self, now: datetime) -> bool:
        """During a CP pulse the Halo briefly sees "no vehicle" – ignore that (§3.4)."""
        return self._mask_until is not None and now < self._mask_until

    def stable(self, snap: Snapshot) -> bool:
        """Charging counts as started only once it is stable (§6.2)."""
        cfg = self.config
        if self._run_count == 0 or self._run_start is None:
            return False
        if _flag(snap.vehicle_charging) is True and snap.vehicle_charging.quality is Quality.GOOD:
            return True
        return (
            self._run_count >= cfg.stable_samples
            and (snap.now - self._run_start).total_seconds() >= cfg.charging_stable_min_s
        )

    def reset(self, now: datetime) -> None:
        """Manual reset button: clear failures, forget the failed window."""
        self.failure_code = None
        self.consecutive_start_failures = 0
        self._failed_window = None
        self._attempts.clear()
        self.cp_not_restored = False
        if self.state is ExecState.START_FAILED:
            self.state = ExecState.IDLE
            self.state_since = now

    def attempts_for(self, desired: Desired) -> WindowAttempts:
        return self._attempts.setdefault(desired.window_key, WindowAttempts())

    def as_dict(self) -> dict[str, Any]:
        """What must survive a restart (§6.5). The state itself is re-derived."""
        return {
            "attempts": {
                k: {"ovms": a.ovms, "cp": a.cp, "restart_used": a.restart_used}
                for k, a in self._attempts.items()
            },
            "failed_window": self._failed_window,
            "failure_code": self.failure_code,
            "consecutive_start_failures": self.consecutive_start_failures,
            "cp_not_restored": self.cp_not_restored,
            "last_switch_at": self._last_switch_at.isoformat() if self._last_switch_at else None,
            "last_wakeup_at": self._last_wakeup_at.isoformat() if self._last_wakeup_at else None,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self._attempts = {
            k: WindowAttempts(v.get("ovms", 0), v.get("cp", 0), v.get("restart_used", False))
            for k, v in (data.get("attempts") or {}).items()
        }
        self._failed_window = data.get("failed_window")
        self.failure_code = data.get("failure_code")
        self.consecutive_start_failures = int(data.get("consecutive_start_failures", 0))
        self.cp_not_restored = bool(data.get("cp_not_restored", False))
        switch_at, wakeup_at = data.get("last_switch_at"), data.get("last_wakeup_at")
        self._last_switch_at = datetime.fromisoformat(switch_at) if switch_at else None
        self._last_wakeup_at = datetime.fromisoformat(wakeup_at) if wakeup_at else None

    def prune_attempts(self, keep: Collection[str]) -> None:
        """Drop counters of windows that are over – keeps the store small."""
        self._attempts = {k: v for k, v in self._attempts.items() if k in keep}

    # -------------------------------------------------------------- helpers

    def _event(self, now: datetime, category: Category, severity: Severity,
               code: str, message: str, **data: Any) -> None:
        self._result.events.append(
            Event(now, category, severity, code, message, self.session_id, dict(data))
        )

    def _command(self, kind: CommandKind, **params: Any) -> None:
        self._result.commands.append(Command(kind, dict(params)))

    def _go(self, state: ExecState, now: datetime, code: str | None = None,
            message: str | None = None, category: Category = Category.CHARGING,
            severity: Severity = Severity.INFO) -> None:
        previous = self.state
        self.state = state
        self.state_since = now
        if code:
            self._event(now, category, severity, code, message or code,
                        previous=str(previous) if previous else None, state=str(state))

    def _elapsed(self, now: datetime) -> float:
        return (now - self.state_since).total_seconds() if self.state_since else 0.0

    def _ingest_power(self, power: Value) -> None:
        """Count consecutive Halo samples above the threshold.

        Stability is measured in samples, not seconds, because the Halo is
        polled from the cloud (§6.2). A sample is identified by its timestamp.
        """
        if not power.available or power.updated_at is None:
            self._run_count = 0
            self._run_start = None
            return
        if power.updated_at == self._last_sample_at:
            return
        self._last_sample_at = power.updated_at
        watts = float(power.normalized)
        self._last_sample_w = watts
        if watts > self.config.power_threshold_w:
            if self._run_count == 0:
                self._run_start = power.updated_at
            self._run_count += 1
        else:
            self._run_count = 0
            self._run_start = None

    def _power_flowing(self) -> bool:
        return self._run_count > 0

    def _initial_state(self, snap: Snapshot) -> None:
        """After a restart: derive the state from reality, never replay commands (§6.5)."""
        now = snap.now
        cable = _flag(snap.cable_connected)
        on = _flag(snap.charger_on)
        if cable is False:
            state = ExecState.DISCONNECTED
        elif on and self._power_flowing():
            state = ExecState.CHARGING
        elif on:
            state = ExecState.WAITING_FOR_CHARGE
        else:
            state = ExecState.IDLE
        self._go(state, now, "EXECUTOR_STARTED", f"Executor gestartet in {state}",
                 Category.CONFIG)

    def _on_unplugged(self, now: datetime) -> None:
        if self.state in (ExecState.CHARGING, ExecState.CHARGE_ENDED):
            self._event(now, Category.CHARGING, Severity.INFO, "SESSION_END",
                        "Ladesession beendet (Kabel gezogen)")
        self.session_id = None
        self.failure_code = None
        self._failed_window = None
        self._resume = None
        self._below_since = None
        self._go(ExecState.DISCONNECTED, now, "CABLE_DISCONNECTED", "Kabel gezogen")

    def _switch(self, snap: Snapshot, enabled: bool, *, retry: bool = False) -> bool:
        """Send a Halo switch command unless the cooldown forbids it (§6.4)."""
        now = snap.now
        if not retry and self._last_switch_at is not None:
            since = (now - self._last_switch_at).total_seconds()
            if since < self.config.min_switch_interval_s:
                key = f"{enabled}:{snap.desired.window_key}"
                if self._violation_reported_for != key:
                    self._violation_reported_for = key
                    self._event(now, Category.CHARGING, Severity.DEBUG, "SWITCH_CYCLE_VIOLATION",
                                "Schaltbefehl im Cooldown zurückgestellt",
                                wait_s=round(self.config.min_switch_interval_s - since))
                return False
        self._violation_reported_for = None
        self._last_switch_at = now
        self._command(CommandKind.ENABLE_CHARGER if enabled else CommandKind.DISABLE_CHARGER)
        return True

    def _start_disabling(self, snap: Snapshot) -> None:
        if self._switch(snap, False):
            self._confirm_attempts = 1
            self._go(ExecState.DISABLING, snap.now, "CHARGER_DISABLE",
                     f"Halo aus ({snap.desired.reason})")

    def _start_enabling(self, snap: Snapshot) -> None:
        if self._switch(snap, True):
            self._confirm_attempts = 1
            self._go(ExecState.ENABLING, snap.now, "CHARGER_ENABLE",
                     f"Halo an ({snap.desired.reason})")

    def _fail(self, snap: Snapshot, code: str, message: str) -> None:
        self.failure_code = code
        self.consecutive_start_failures += 1
        self._failed_window = snap.desired.window_key
        self._go(ExecState.START_FAILED, snap.now, code, message, Category.CHARGING,
                 Severity.ERROR)

    def _check_cp_restored(self, snap: Snapshot) -> None:
        """After every pulse the relay must be back on (§3.2)."""
        if self._pulse_check_at is None or snap.now < self._pulse_check_at:
            return
        self._pulse_check_at = None
        if _flag(snap.cp_relay_on) is True:
            self._event(snap.now, Category.CP, Severity.INFO, "CP_PULSE_DONE",
                        f"CP geschlossen nach {self.config.cp_pulse_s} s")
            return
        self.cp_not_restored = True
        self._event(snap.now, Category.CP, Severity.CRITICAL, "CP_NOT_RESTORED",
                    "CP-Relais nach dem Puls nicht wieder geschlossen")
        self._last_cp_close_at = snap.now
        self._command(CommandKind.CP_CLOSE)

    def _safety_hold(self, snap: Snapshot) -> None:
        """Health ERROR: no switching at all – except closing the CP (§7.5)."""
        if (
            self.config.cp_available
            and _flag(snap.cp_relay_on) is False
            and not self.cp_masked(snap.now)
            and (self._last_cp_close_at is None
                 or (snap.now - self._last_cp_close_at).total_seconds() >= CP_CLOSE_RETRY_S)
        ):
            self._last_cp_close_at = snap.now
            self._command(CommandKind.CP_CLOSE)
        if self.cp_not_restored and _flag(snap.cp_relay_on) is True:
            self.cp_not_restored = False
            self._event(snap.now, Category.CP, Severity.INFO, "CP_RESTORED",
                        "CP-Normalzustand wieder bestätigt")

    def _cp_wakeup_allowed(self, snap: Snapshot) -> bool:
        cfg = self.config
        return (
            cfg.cp_available
            and cfg.cp_failsafe_verified
            and not self.cp_not_restored
            and snap.health.status is not HealthStatus.ERROR
            and _flag(snap.cp_relay_on) is True
        )

    def _wakeup_gap_ok(self, now: datetime) -> bool:
        if self._last_wakeup_at is None:
            return True
        return (now - self._last_wakeup_at).total_seconds() >= self.config.min_gap_between_wakeups_s

    def _escalate(self, snap: Snapshot) -> None:
        """OVMS first, then CP, each at most once per window – then give up (§6)."""
        now = snap.now
        cfg = self.config
        attempts = self.attempts_for(snap.desired)
        ovms_left = cfg.ovms_available and attempts.ovms < cfg.max_ovms_attempts_per_window
        cp_left = self._cp_wakeup_allowed(snap) and attempts.cp < cfg.max_cp_attempts_per_window
        if (ovms_left or cp_left) and not self._wakeup_gap_ok(now):
            return
        if ovms_left:
            attempts.ovms += 1
            self._last_wakeup_at = now
            self._command(CommandKind.OVMS_WAKEUP)
            self._go(ExecState.WAKEUP_OVMS, now, "OVMS_WAKEUP", "Software-Wakeup über OVMS",
                     Category.WAKEUP)
            return
        if cp_left:
            attempts.cp += 1
            self._last_wakeup_at = now
            self._mask_until = now + timedelta(seconds=cfg.cp_pulse_s + cfg.cp_mask_grace_s)
            self._pulse_check_at = now + timedelta(
                seconds=cfg.cp_pulse_s + cfg.cp_restore_check_extra_s)
            self._command(CommandKind.CP_PULSE, seconds=cfg.cp_pulse_s)
            self._go(ExecState.WAKEUP_CP, now, "CP_PULSE_START",
                     f"CP-Puls {cfg.cp_pulse_s} s", Category.WAKEUP)
            return
        if attempts.restart_used:
            self._fail(snap, "CHARGE_INTERRUPTED", "Ladung abgebrochen, Neustart erfolglos")
        else:
            self._fail(snap, "CHARGE_START_FAILED", "Ladestart fehlgeschlagen (Kaskade erfolglos)")

    def _reconcile_off(self, snap: Snapshot) -> bool:
        """Halo on although it should be off → switch it off. True if handled."""
        if snap.desired.charger_enabled is False and _flag(snap.charger_on) is True:
            self._start_disabling(snap)
            return True
        return False

    def _starting(self, snap: Snapshot, timeout_s: float, on_timeout) -> None:
        """Shared logic of WAITING_FOR_CHARGE and both wakeup states."""
        if snap.desired.charger_enabled is False:
            self._start_disabling(snap)
            return
        if self.stable(snap):
            self._charging_started(snap)
            return
        if self._power_flowing():
            self._resume = (self.state, self.state_since)
            self._go(ExecState.CHARGE_STABILIZING, snap.now, "POWER_DETECTED",
                     f"Leistung erkannt ({self._last_sample_w:.0f} W)")
            return
        if self._elapsed(snap.now) >= timeout_s:
            on_timeout(snap)

    def _charging_started(self, snap: Snapshot) -> None:
        now = snap.now
        self.session_id = self.session_id or f"s-{now.strftime('%Y%m%d-%H%M%S')}"
        self.consecutive_start_failures = 0
        self.failure_code = None
        self._below_since = None
        self._resume = None
        self._go(ExecState.CHARGING, now, "CHARGE_STABLE", "Ladung stabil bestätigt")

    # --------------------------------------------------------------- states

    def _in_disconnected(self, snap: Snapshot) -> None:
        # Without a vehicle there is nothing to confirm; a Halo left on is
        # switched off fire-and-forget and re-checked on later steps.
        if snap.desired.charger_enabled is False and _flag(snap.charger_on) is True:
            self._switch(snap, False)

    def _in_idle(self, snap: Snapshot) -> None:
        if snap.desired.charger_enabled is True:
            if snap.desired.window_key == self._failed_window:
                return
            if _flag(snap.charger_on) is True:
                self._go(ExecState.WAITING_FOR_CHARGE, snap.now, "WAIT_FOR_CHARGE",
                         "Halo bereits an, warte auf Leistung")
            else:
                self._start_enabling(snap)
            return
        self._reconcile_off(snap)

    def _in_enabling(self, snap: Snapshot) -> None:
        if snap.desired.charger_enabled is False:
            self._start_disabling(snap)
            return
        if _flag(snap.charger_on) is True:
            self._go(ExecState.WAITING_FOR_CHARGE, snap.now, "CHARGER_CONFIRMED",
                     "Halo hat Freigabe bestätigt")
            return
        if self._elapsed(snap.now) >= self.config.confirm_timeout_s:
            if self._confirm_attempts >= self.config.max_confirm_attempts:
                self._fail(snap, "CHARGER_NOT_CONFIRMED", "Halo bestätigt die Freigabe nicht")
                return
            self._confirm_attempts += 1
            self._switch(snap, True, retry=True)
            self.state_since = snap.now

    def _in_waiting_for_charge(self, snap: Snapshot) -> None:
        self._starting(snap, self.config.start_detection_wait_s, self._escalate)

    def _in_wakeup_ovms(self, snap: Snapshot) -> None:
        self._starting(snap, self.config.ovms_wait_s, self._escalate)

    def _in_wakeup_cp(self, snap: Snapshot) -> None:
        if self.cp_not_restored:
            return
        wait = self.config.cp_pulse_s + self.config.post_cp_wait_s
        self._starting(snap, wait, self._escalate)

    def _in_charge_stabilizing(self, snap: Snapshot) -> None:
        if snap.desired.charger_enabled is False:
            self._start_disabling(snap)
            return
        if self.stable(snap):
            self._charging_started(snap)
            return
        if not self._power_flowing():
            state, since = self._resume or (ExecState.WAITING_FOR_CHARGE, snap.now)
            self._resume = None
            self._go(state, snap.now, "POWER_LOST", "Leistung vor Stabilisierung eingebrochen")
            self.state_since = since

    def _in_charging(self, snap: Snapshot) -> None:
        now = snap.now
        if snap.desired.charger_enabled is False:
            self._event(now, Category.CHARGING, Severity.INFO, "SESSION_END",
                        f"Ladesession beendet ({snap.desired.reason})")
            self._start_disabling(snap)
            return
        if self._power_flowing():
            self._below_since = None
            return
        if self._below_since is None:
            self._below_since = now
        status = snap.charger_status.normalized if snap.charger_status else None
        if snap.vehicle_charge_finished or (status is not None
                                            and status in self.config.finished_statuses):
            self._below_since = None
            self._go(ExecState.CHARGE_ENDED, now, "CHARGE_ENDED", "Fahrzeug hat Ladung beendet")
            return
        if (now - self._below_since).total_seconds() >= self.config.charging_loss_timeout_s:
            self._below_since = None
            self._go(ExecState.INTERRUPTED, now, "CHARGE_INTERRUPTED",
                     "Ladeleistung ohne Ladeende weggefallen", severity=Severity.WARNING)

    def _in_charge_ended(self, snap: Snapshot) -> None:
        if self._reconcile_off(snap):
            return
        if self.stable(snap):
            self._go(ExecState.CHARGING, snap.now, "CHARGE_RESUMED", "Fahrzeug lädt wieder")

    def _in_interrupted(self, snap: Snapshot) -> None:
        if self._reconcile_off(snap):
            return
        attempts = self.attempts_for(snap.desired)
        if attempts.restart_used:
            self._fail(snap, "CHARGE_INTERRUPTED", "Ladung abgebrochen, Neustart erfolglos")
            return
        attempts.restart_used = True
        self._go(ExecState.WAITING_FOR_CHARGE, snap.now, "CHARGE_RESTART",
                 "Ein Neustartversuch nach Ladeabbruch")

    def _in_disabling(self, snap: Snapshot) -> None:
        if _flag(snap.charger_on) is False:
            self._go(ExecState.COOLDOWN, snap.now, "CHARGER_OFF_CONFIRMED",
                     "Halo hat Abschaltung bestätigt")
            return
        if self._elapsed(snap.now) >= self.config.confirm_timeout_s:
            if self._confirm_attempts >= self.config.max_confirm_attempts:
                self._event(snap.now, Category.CHARGING, Severity.ERROR, "CHARGER_NOT_CONFIRMED",
                            "Halo bestätigt die Abschaltung nicht")
                self._go(ExecState.COOLDOWN, snap.now)
                return
            self._confirm_attempts += 1
            self._switch(snap, False, retry=True)
            self.state_since = snap.now

    def _in_cooldown(self, snap: Snapshot) -> None:
        since = (snap.now - self._last_switch_at).total_seconds() if self._last_switch_at else None
        if since is None or since >= self.config.min_switch_interval_s:
            self._go(ExecState.IDLE, snap.now)
            self._in_idle(snap)

    def _in_start_failed(self, snap: Snapshot) -> None:
        if snap.desired.charger_enabled is True and snap.desired.window_key != self._failed_window:
            self.failure_code = None
            self._failed_window = None
            self._go(ExecState.IDLE, snap.now, "NEW_WINDOW", "Neues Ladefenster")
            self._in_idle(snap)
            return
        if snap.desired.charger_enabled is False and _flag(snap.charger_on) is True:
            self._switch(snap, False)
