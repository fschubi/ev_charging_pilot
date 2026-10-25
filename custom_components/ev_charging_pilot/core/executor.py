"""Executor: reconcile the desired state with reality, incl. wakeup cascade (§6).

``Executor.step`` takes one immutable :class:`Snapshot` and returns the
commands to dispatch plus the events to log. It never performs I/O. Because
all timing comes from ``snapshot.now``, a replay of recorded snapshots runs
the identical logic at test speed.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from .health import Health, HealthStatus
from .model import Category, Desired, Event, Quality, Reason, Severity, Value
from .ports import Command, CommandKind
from .settings import Settings


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
    PAUSED = "PAUSED"
    DISABLING = "DISABLING"
    COOLDOWN = "COOLDOWN"
    START_FAILED = "START_FAILED"


# States in which the executor is still trying to get energy flowing.
_STARTING = (ExecState.WAITING_FOR_CHARGE, ExecState.WAKEUP_OVMS, ExecState.WAKEUP_CP)

STATE_TEXT = {
    ExecState.DISCONNECTED: "nicht eingesteckt", ExecState.IDLE: "bereit",
    ExecState.WAITING_FOR_CHARGE: "wartet auf Ladeleistung", ExecState.CHARGING: "lädt",
    ExecState.CHARGE_ENDED: "Auto hat fertig geladen",
    ExecState.PAUSED: "Ladepause (Auto nimmt keinen Strom)",
    ExecState.START_FAILED: "Start fehlgeschlagen",
}
# A car that stops drawing power below its target pauses (battery too warm or cold)
# rather than ending: the wallbox stays on. After this long without power it is woken
# once (OVMS, then CP with a longer wait); after that the wallbox simply stays on until
# the cable is pulled (Frank, 20.10.2026).
PAUSE_WAIT = timedelta(minutes=15)
PAUSE_POST_CP_WAIT_S = 300.0
# Pre-climatisation on grid power: the OVMS command only goes out once the Halo
# confirmed its release (field 18.10.2026: 7 s). Without confirmation it is skipped.
CLIMATE_CONFIRM_TIMEOUT = timedelta(seconds=60)
# After the wallbox refused to confirm "off" several times, wait this long.
OFF_RETRY_AFTER = timedelta(minutes=30)
# How often a "close the CP" command is repeated while the relay stays open.
CP_CLOSE_RETRY_S = 30.0
# A charge whose last power sample fell below this share of its peak tapered off:
# the car ended it (battery full), it was not interrupted.
TAPER_RATIO = 0.6


@dataclass(frozen=True, slots=True)
class ExecutorConfig:
    """Timing and limits (§6.2, §6.4). Provisional until Phase 0 measured them."""

    power_threshold_w: float = 300.0
    stable_samples: int = 2
    charging_stable_min_s: float = 20.0
    charging_loss_timeout_s: float = 180.0
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
    cp_fallback_enabled: bool = True
    climate_available: bool = False
    finished_statuses: Collection[str] = ()

    @classmethod
    def from_settings(cls, s: Settings, *, cp_available: bool,
                      ovms_port: bool = True) -> ExecutorConfig:
        return cls(
            power_threshold_w=s.power_threshold_w,
            stable_samples=s.stable_samples,
            charging_stable_min_s=s.stable_min_s,
            charging_loss_timeout_s=s.loss_timeout_s,
            start_detection_wait_s=s.start_detection_wait_s,
            ovms_wait_s=s.ovms_wait_s,
            post_cp_wait_s=s.post_cp_wait_s,
            max_ovms_attempts_per_window=s.max_ovms_attempts,
            max_cp_attempts_per_window=s.max_cp_attempts,
            min_gap_between_wakeups_s=s.min_gap_between_wakeups_s,
            min_switch_interval_s=s.min_switch_interval_s,
            confirm_timeout_s=s.confirm_timeout_s,
            cp_pulse_s=s.cp_pulse_s,
            cp_mask_grace_s=s.cp_mask_grace_s,
            ovms_available=s.ovms_enabled and ovms_port and bool(s.ovms_wakeup_command),
            cp_available=cp_available,
            cp_failsafe_verified=s.cp_failsafe_verified,
            cp_fallback_enabled=s.cp_fallback_enabled,
            climate_available=s.ovms_enabled and ovms_port and bool(s.ovms_climate_command),
            finished_statuses=s.finished_statuses,
        )


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
    # The known SOC is clearly below the target: a falling power is no end of charge.
    below_target: bool | None = None


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
        # Window in which the car finished charging by itself (survives a restart).
        self._ended_window: str | None = None
        # The wallbox refused to switch off – wait before the next attempt.
        self._off_given_up_at: datetime | None = None
        self._last_switch_at: datetime | None = None
        self._last_wakeup_at: datetime | None = None
        self._mask_until: datetime | None = None
        self._pulse_check_at: datetime | None = None
        self.last_pulse_at: datetime | None = None
        # Charging paused below the target (PAUSED): since when, woken already, and
        # whether the wakeup cascade currently runs on behalf of the pause.
        self._pause_since: datetime | None = None
        self._pause_woken = False
        self._pause_recovery = False
        self._confirm_attempts = 0
        self._resume: tuple[ExecState, datetime] | None = None
        self._below_since: datetime | None = None
        self._last_sample_at: datetime | None = None
        self._run_count = 0
        self._run_start: datetime | None = None
        self._last_sample_w: float | None = None
        self._violation_reported_for: str | None = None
        self._last_cp_close_at: datetime | None = None
        self._climate_sent: str | None = None
        # (request key, since): waiting for the Halo before the climate command.
        self._climate_wait: tuple[str, datetime] | None = None
        self._peak_w: float = 0.0
        self._last_flow_w: float | None = None
        self._halo_power_frozen = False
        # Dry-run/replay: decisions are only logged, so a missing reaction of the
        # hardware is no failure (no push, no failed session, no health penalty).
        self.shadow = False
        # Window bookkeeping of the live mode while a dry run works on its own copy
        self._live_windows: tuple | None = None
        self._last_snap: Snapshot | None = None
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

        self._last_snap = snap
        if snap.health.blocks_automation:
            self._safety_hold(snap)
            return self._result
        self._handle_climate(snap)
        if snap.desired.charger_enabled is None:
            # Automation off / nothing to decide: leave the Halo alone.
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

    @staticmethod
    def _vehicle_charging(snap: Snapshot) -> bool:
        """The car itself reports a running charge with a fresh value."""
        return _flag(snap.vehicle_charging) is True \
            and snap.vehicle_charging.quality is Quality.GOOD

    def stable(self, snap: Snapshot) -> bool:
        """Charging counts as started only once it is stable (§6.2)."""
        cfg = self.config
        if self._run_count == 0 or self._run_start is None:
            return False
        if self._vehicle_charging(snap):
            return True
        return (
            self._run_count >= cfg.stable_samples
            and (snap.now - self._run_start).total_seconds() >= cfg.charging_stable_min_s
        )

    def request_wakeup(self, kind: CommandKind, now: datetime) -> StepResult:
        """Manual "wake the car" button – same guards as the cascade (§12.2)."""
        self._result = StepResult()
        snap = self._last_snap
        if snap is None:
            return self._result
        if not self._wakeup_gap_ok(now):
            self._event(now, Category.WAKEUP, Severity.WARNING, "WAKEUP_REJECTED",
                        "Wakeup abgelehnt: Mindestabstand zum letzten Wakeup")
            return self._result
        attempts = self.attempts_for(snap.desired)
        if kind is CommandKind.OVMS_WAKEUP:
            if not self.config.ovms_available:
                self._event(now, Category.WAKEUP, Severity.WARNING, "WAKEUP_REJECTED",
                            "OVMS-Wakeup nicht verfügbar")
                return self._result
            attempts.ovms += 1
            self._last_wakeup_at = now
            self._command(CommandKind.OVMS_WAKEUP)
            self._event(now, Category.WAKEUP, Severity.INFO, "OVMS_WAKEUP",
                        "Manueller Software-Wakeup über OVMS")
        elif kind is CommandKind.CP_PULSE:
            if not self._cp_wakeup_allowed(snap, manual=True):
                self._event(now, Category.WAKEUP, Severity.WARNING, "WAKEUP_REJECTED",
                            "CP-Wakeup gesperrt (Failsafe, Health oder CP-Zustand)")
                return self._result
            attempts.cp += 1
            self._start_pulse(now)
            self._event(now, Category.WAKEUP, Severity.INFO, "CP_PULSE_START",
                        f"Manueller CP-Puls {self.config.cp_pulse_s} s")
        return self._result

    def request_climate_restart(self, now: datetime, minutes: int, number: int) -> StepResult:
        """One more climate block, sent by the pilot itself (no Halo wait: it is on)."""
        self._result = StepResult()
        if self.config.climate_available:
            self._command(CommandKind.CLIMATE_START, duration_min=minutes)
            self._event(now, Category.CLIMATE, Severity.INFO, "CLIMATE_RESTART",
                        f"Klima {minutes} min nachgestartet ({number}. Mal) – geplant ist "
                        "sie bis 5 min nach der Abfahrt")
        return self._result

    def request_climate_stop(self, now: datetime) -> StepResult:
        self._result = StepResult()
        if not self.config.climate_available:
            # Vehicle commands need the "read & write" access (§1.1 rule 8).
            self._event(now, Category.CLIMATE, Severity.WARNING, "CLIMATE_UNAVAILABLE",
                        "Klima-Stopp nicht gesendet – Fahrzeugbefehle sind nicht freigegeben")
            return self._result
        self._command(CommandKind.CLIMATE_STOP)
        self._event(now, Category.CLIMATE, Severity.INFO, "CLIMATE_STOP", "Klimatisierung gestoppt")
        return self._result

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
            "ended_window": self._ended_window,
            "failure_code": self.failure_code,
            "consecutive_start_failures": self.consecutive_start_failures,
            "cp_not_restored": self.cp_not_restored,
            "last_switch_at": self._last_switch_at.isoformat() if self._last_switch_at else None,
            "last_wakeup_at": self._last_wakeup_at.isoformat() if self._last_wakeup_at else None,
            # A restart during the climate window must not send the command twice.
            "climate_sent": self._climate_sent,
            # A paused charge keeps its wallbox until unplugged – also across a restart.
            "pause_since": self._pause_since.isoformat() if self._pause_since else None,
            "pause_woken": self._pause_woken,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self._attempts = {
            k: WindowAttempts(v.get("ovms", 0), v.get("cp", 0), v.get("restart_used", False))
            for k, v in (data.get("attempts") or {}).items()
        }
        self._failed_window = data.get("failed_window")
        self._ended_window = data.get("ended_window")
        self.failure_code = data.get("failure_code")
        self.consecutive_start_failures = int(data.get("consecutive_start_failures", 0))
        self.cp_not_restored = bool(data.get("cp_not_restored", False))
        switch_at, wakeup_at = data.get("last_switch_at"), data.get("last_wakeup_at")
        self._last_switch_at = datetime.fromisoformat(switch_at) if switch_at else None
        self._last_wakeup_at = datetime.fromisoformat(wakeup_at) if wakeup_at else None
        self._climate_sent = data.get("climate_sent")
        pause = data.get("pause_since")
        self._pause_since = datetime.fromisoformat(pause) if pause else None
        self._pause_woken = bool(data.get("pause_woken", False))

    def prune_expired(self, now: datetime, keep_last: int = 20) -> None:
        """Drop counters of windows that ended more than a day ago – keeps the store small."""
        def alive(key: str) -> bool:
            until = key.rsplit("|", 1)[-1]
            if until == "-":
                return True
            try:
                return datetime.fromisoformat(until) > now - timedelta(days=1)
            except ValueError:
                return False

        kept = [(k, v) for k, v in self._attempts.items() if alive(k)]
        self._attempts = dict(kept[-keep_last:])

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
        self._halo_power_frozen = not power.available or power.updated_at is None \
            or power.quality in (Quality.STALE, Quality.LAST_KNOWN_VALID)
        if self._halo_power_frozen:
            # A frozen power value (entity available, but no new report for longer than
            # max_age halo_power) must not keep "power flowing" – that hid charge loss.
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
            self._last_flow_w = watts
            self._peak_w = max(self._peak_w, watts)
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
        window = snap.desired.window_key
        if cable is False:
            state = ExecState.DISCONNECTED
        elif on and self._power_flowing():
            state = ExecState.CHARGING
            self._clear_pause()
        elif on and self._pause_since is not None:
            # Paused before the restart: wait on, never start the wakeup chain anew.
            state = ExecState.PAUSED
        elif self._failed_window is not None and self._failed_window == window:
            # The start of this window already failed – a restart is no new attempt.
            state = ExecState.START_FAILED
        elif on and self._ended_window is not None and self._ended_window == window:
            # The car finished charging in this window: never wake it again for it.
            state = ExecState.CHARGE_ENDED
        elif on:
            state = ExecState.WAITING_FOR_CHARGE
        else:
            state = ExecState.IDLE
        self._go(state, now, "EXECUTOR_STARTED",
                 f"Neustart der Steuerung – Zustand: {STATE_TEXT.get(state, state)}",
                 Category.CONFIG)

    def _on_unplugged(self, now: datetime) -> None:
        if self.state in (ExecState.CHARGING, ExecState.CHARGE_ENDED, ExecState.PAUSED) \
                or self._pause_recovery:
            self._event(now, Category.CHARGING, Severity.INFO, "SESSION_END",
                        "Ladesession beendet (Kabel gezogen)")
        self._clear_pause()
        self.session_id = None
        self.failure_code = None
        # §8.1: unplugging is the automatic way out of failed starts, repeated ones too
        self.consecutive_start_failures = 0
        self._failed_window = None
        self._ended_window = None
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
                                "Schaltbefehl zurückgestellt (Mindestpause zwischen Schaltungen)",
                                wait_s=round(self.config.min_switch_interval_s - since))
                return False
        self._violation_reported_for = None
        self._last_switch_at = now
        self._command(CommandKind.ENABLE_CHARGER if enabled else CommandKind.DISABLE_CHARGER)
        return True

    def _start_disabling(self, snap: Snapshot) -> bool:
        if self._switch(snap, False):
            self._confirm_attempts = 1
            self._go(ExecState.DISABLING, snap.now, "CHARGER_DISABLE",
                     f"Wallbox aus ({snap.desired.reason})")
            return True
        return False

    def _start_enabling(self, snap: Snapshot) -> None:
        if self._switch(snap, True):
            self._confirm_attempts = 1
            self._go(ExecState.ENABLING, snap.now, "CHARGER_ENABLE",
                     f"Wallbox an ({snap.desired.reason})")

    def _fail(self, snap: Snapshot, code: str, message: str) -> None:
        self.failure_code = code
        self._failed_window = snap.desired.window_key
        if self.shadow:
            self._go(ExecState.START_FAILED, snap.now, code,
                     f"{message} (Probebetrieb: Wallbox wurde nicht geschaltet)",
                     Category.CHARGING, Severity.WARNING)
            return
        self.consecutive_start_failures += 1
        # Never leave the wallbox enabled after a failed start: a car waking up later
        # would charge without any target stop (and a safety lock would freeze it on).
        if _flag(snap.charger_on) is True:
            self._switch(snap, False, retry=True)
        self._go(ExecState.START_FAILED, snap.now, code, message, Category.CHARGING,
                 Severity.ERROR)

    def _topup_not_started(self, snap: Snapshot) -> None:
        """Topping up after the target needs no wakeup: give up quietly for this window."""
        self._failed_window = snap.desired.window_key
        self._event(snap.now, Category.CHARGING, Severity.INFO, "TOPUP_SKIPPED",
                    "Nachladen nicht gestartet – das Auto wird dafür nicht geweckt")
        if _flag(snap.charger_on) is True:
            self._switch(snap, False, retry=True)
        self._go(ExecState.IDLE, snap.now)

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

    def _cp_wakeup_allowed(self, snap: Snapshot, manual: bool = False) -> bool:
        cfg = self.config
        return (
            cfg.cp_available
            and (manual or cfg.cp_fallback_enabled)
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
        if snap.desired.reason is Reason.CLIMATE:
            # The wallbox only offers grid power for the climate: the car may draw
            # nothing (full battery) or only later (field 20.10.2026: the HVAC started
            # 70 s after the release, the Halo had been switched off 6 s before).
            self.state_since = now
            return
        if not snap.desired.wake_allowed:
            if self._pause_recovery:
                self._hold_pause(snap)
                return
            self._topup_not_started(snap)
            return
        if self._vehicle_charging(snap):
            # The car reports charging: there is nothing to wake (rule 2) – only the
            # Halo's power has not arrived (yet).
            self.state_since = now
            return
        if _flag(snap.cable_connected) is not True:
            # Cable unknown (e.g. right after a restart): never wake a car that may not
            # even be plugged in.
            self._failed_window = snap.desired.window_key
            self._event(snap.now, Category.WAKEUP, Severity.INFO, "WAKEUP_SKIPPED",
                        "Kein Weckversuch – ob das Auto eingesteckt ist, ist unbekannt")
            if _flag(snap.charger_on) is True:
                self._switch(snap, False, retry=True)
            self._go(ExecState.IDLE, snap.now)
            return
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
            self._start_pulse(now)
            self._go(ExecState.WAKEUP_CP, now, "CP_PULSE_START",
                     f"CP-Puls {cfg.cp_pulse_s} s", Category.WAKEUP)
            return
        if self._pause_recovery:
            self._hold_pause(snap)
            return
        if attempts.restart_used:
            self._fail(snap, "CHARGE_INTERRUPTED", "Ladung abgebrochen, Neustart erfolglos")
        else:
            self._fail(snap, "CHARGE_START_FAILED",
                       "Ladestart fehlgeschlagen – das Auto ließ sich nicht wecken")

    def _start_pulse(self, now: datetime) -> None:
        cfg = self.config
        self._last_wakeup_at = now
        self.last_pulse_at = now
        self._mask_until = now + timedelta(seconds=cfg.cp_pulse_s + cfg.cp_mask_grace_s)
        self._pulse_check_at = now + timedelta(
            seconds=cfg.cp_pulse_s + cfg.cp_restore_check_extra_s)
        self._command(CommandKind.CP_PULSE, seconds=cfg.cp_pulse_s)

    def _handle_climate(self, snap: Snapshot) -> None:
        """Send the OVMS climate command once per request when it is due (§9.2)."""
        request = snap.desired.climate
        if request is None or request.key == self._climate_sent:
            return
        if not request.start_at <= snap.now < request.until:
            return
        if not self.config.climate_available:
            self._climate_sent = request.key
            self._event(snap.now, Category.CLIMATE, Severity.WARNING, "CLIMATE_UNAVAILABLE",
                        "Klimatisierung geplant, aber OVMS-Befehl nicht verfügbar")
            return
        if snap.desired.charger_enabled is True and _flag(snap.charger_on) is not True:
            # Plugged in: grid power first, then the climate – otherwise the car heats
            # from its battery until the cloud-polled Halo has switched.
            if self._climate_wait is None or self._climate_wait[0] != request.key:
                self._climate_wait = (request.key, snap.now)
            if snap.now - self._climate_wait[1] < CLIMATE_CONFIRM_TIMEOUT:
                return
            self._climate_sent = request.key
            self._event(snap.now, Category.CLIMATE, Severity.WARNING, "CLIMATE_SKIPPED",
                        "Vorklimatisierung ausgefallen: Wallbox hat die Freigabe nicht "
                        f"innerhalb von {int(CLIMATE_CONFIRM_TIMEOUT.total_seconds())} s "
                        "bestätigt")
            return
        self._climate_sent = request.key
        self._climate_wait = None
        self._command(CommandKind.CLIMATE_START, duration_min=request.duration_min)
        self._event(snap.now, Category.CLIMATE, Severity.INFO, "CLIMATE_START",
                    f"Vorklimatisierung {request.duration_min} min",
                    plugged_in=snap.desired.charger_enabled is True)

    def _reconcile_off(self, snap: Snapshot) -> bool:
        """Halo on although it should be off → switch it off. True if handled."""
        if snap.desired.charger_enabled is False and _flag(snap.charger_on) is True:
            if self._off_given_up_at is not None and \
                    snap.now - self._off_given_up_at < OFF_RETRY_AFTER:
                return True  # it refused to switch off – no endless retry loop (§1.1)
            self._start_disabling(snap)
            return True
        return False

    def _starting(self, snap: Snapshot, timeout_s: float, on_timeout) -> None:
        """Shared logic of WAITING_FOR_CHARGE and both wakeup states."""
        if snap.desired.charger_enabled is False:
            if self._pause_recovery:
                self._event(snap.now, Category.CHARGING, Severity.INFO, "SESSION_END",
                            f"Ladesession beendet ({snap.desired.reason})")
                self.session_id = None
                self._clear_pause()
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
        if self._pause_recovery:
            self._event(now, Category.CHARGING, Severity.INFO, "PAUSE_RESUMED",
                        "Lädt wieder nach der Ladepause (nach dem Wecken)")
        self._clear_pause()
        self.session_id = self.session_id or f"s-{now.strftime('%Y%m%d-%H%M%S')}"
        self._ended_window = None
        self.consecutive_start_failures = 0
        self.failure_code = None
        self._below_since = None
        self._resume = None
        self._peak_w = self._last_flow_w or 0.0
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
                         "Wallbox bereits an, warte auf Leistung")
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
                     "Wallbox hat Freigabe bestätigt")
            return
        if self._elapsed(snap.now) >= self.config.confirm_timeout_s:
            if self._confirm_attempts >= self.config.max_confirm_attempts:
                self._fail(snap, "CHARGER_NOT_CONFIRMED", "Wallbox bestätigt die Freigabe nicht")
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
        post = PAUSE_POST_CP_WAIT_S if self._pause_recovery else self.config.post_cp_wait_s
        self._starting(snap, self.config.cp_pulse_s + post, self._escalate)

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
            # The next start is a new session (field 19.10.2026: the climate session
            # reused the night's ID).
            self.session_id = None
            if not self._start_disabling(snap):
                # Minimum switch interval not over yet: wait in COOLDOWN (switching off
                # follows from IDLE) instead of ending the session again every tick.
                self._go(ExecState.COOLDOWN, now)
            return
        if self._power_flowing() or (self._halo_power_frozen and self._vehicle_charging(snap)):
            # The car's own "charging" outweighs a Halo power that froze in the cloud
            # (review 24.10.2026: that "pause" ended in a CP pulse cutting the charge);
            # a fresh 0 W from the Halo still wins over an OVMS flag that lags behind.
            self._below_since = None
            return
        if self._below_since is None:
            self._below_since = now
        status = snap.charger_status.normalized if snap.charger_status else None
        # A falling power only means "full" when the SOC does not say otherwise: a
        # battery too warm or cold also derates before it pauses.
        tapered = self._peak_w > 0 and self._last_flow_w is not None \
            and self._last_flow_w < TAPER_RATIO * self._peak_w \
            and snap.below_target is not True
        if snap.vehicle_charge_finished or tapered or (
                status is not None and status in self.config.finished_statuses):
            self._below_since = None
            why = "Leistung ist zum Schluss abgesunken" if tapered and not \
                snap.vehicle_charge_finished else "Fahrzeug meldet Ladeende"
            self._ended_window = snap.desired.window_key
            self._go(ExecState.CHARGE_ENDED, now, "CHARGE_ENDED",
                     f"Fahrzeug hat Ladung beendet ({why})")
            # The session closes here; topping up later starts a new one.
            self.session_id = None
            return
        if (now - self._below_since).total_seconds() >= self.config.charging_loss_timeout_s:
            self._below_since = None
            if snap.desired.reason is Reason.CLIMATE:
                return  # a cycling heater is no broken charge – the wallbox stays on
            self._pause_since, self._pause_woken = now, False
            self._go(ExecState.PAUSED, now, "CHARGE_PAUSED",
                     "Auto nimmt keinen Strom mehr, obwohl das Ziel nicht erreicht ist – "
                     "Ladepause, die Wallbox bleibt frei", severity=Severity.WARNING)

    def _in_charge_ended(self, snap: Snapshot) -> None:
        if self._reconcile_off(snap):
            return
        if snap.desired.charger_enabled is True and self._ended_window is not None \
                and snap.desired.window_key != self._ended_window:
            # A new request (e.g. "Jetzt laden" after the plan's charge ended).
            self._ended_window = None
            self._go(ExecState.WAITING_FOR_CHARGE, snap.now, "WAIT_FOR_CHARGE",
                     "Neue Anforderung nach Ladeende")
            return
        if self.stable(snap):
            self._go(ExecState.CHARGING, snap.now, "CHARGE_RESUMED", "Fahrzeug lädt wieder")

    def _in_paused(self, snap: Snapshot) -> None:
        now = snap.now
        if snap.desired.charger_enabled is False:
            self._event(now, Category.CHARGING, Severity.INFO, "SESSION_END",
                        f"Ladesession beendet ({snap.desired.reason})")
            self.session_id = None
            self._clear_pause()
            if not self._start_disabling(snap):
                self._go(ExecState.COOLDOWN, now)
            return
        if self.stable(snap):
            self._event(now, Category.CHARGING, Severity.INFO, "PAUSE_RESUMED",
                        "Lädt wieder nach der Ladepause")
            self._clear_pause()
            self._below_since = None
            self._go(ExecState.CHARGING, now, "CHARGE_RESUMED", "Fahrzeug lädt wieder")
            return
        if self._pause_woken or self._pause_since is None \
                or now - self._pause_since < PAUSE_WAIT:
            return
        self._pause_woken = True
        if not snap.desired.wake_allowed:
            self._hold_pause(snap)
            return
        self._pause_recovery = True
        self._go(ExecState.WAITING_FOR_CHARGE, now, "PAUSE_WAKE",
                 f"Seit {int(PAUSE_WAIT.total_seconds() // 60)} min keine Leistung – "
                 "einmal wecken")

    def _hold_pause(self, snap: Snapshot) -> None:
        """Nothing brought the power back: keep the wallbox on until the cable is pulled."""
        self._pause_recovery = False
        self._pause_woken = True
        self._pause_since = self._pause_since or snap.now
        self._go(ExecState.PAUSED, snap.now, "PAUSE_HOLD",
                 "Ladepause hält an – die Wallbox bleibt frei, bis das Kabel gezogen wird",
                 severity=Severity.WARNING)

    def set_shadow(self, shadow: bool) -> None:
        """Switch between dry run and live. A dry run never sees power flow, so its
        wakeup attempts, failed and ended windows say nothing about reality: it keeps
        them apart, and live continues with its own (field review 24.10.2026: a switch
        to live mid-window started in START_FAILED and charged 0 kWh)."""
        if shadow == self.shadow:
            return
        windows = (self._attempts, self._failed_window, self._ended_window,
                   self.failure_code)
        if shadow:
            self._live_windows = windows
            self._attempts, self._failed_window, self._ended_window = \
                {k: replace(v) for k, v in self._attempts.items()}, \
                self._failed_window, self._ended_window
        else:
            saved = self._live_windows or ({}, None, None, None)
            self._attempts, self._failed_window, self._ended_window, self.failure_code = saved
            self._live_windows = None
            self._clear_pause()
        self.shadow = shadow
        self.state = None

    def _clear_pause(self) -> None:
        self._pause_since = None
        self._pause_woken = False
        self._pause_recovery = False

    @property
    def paused(self) -> bool:
        """Charging paused below the target, the wallbox is held on for it."""
        return self.state is ExecState.PAUSED or self._pause_recovery

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
            self._off_given_up_at = None
            self._go(ExecState.COOLDOWN, snap.now, "CHARGER_OFF_CONFIRMED",
                     "Wallbox hat Abschaltung bestätigt")
            return
        if self._elapsed(snap.now) >= self.config.confirm_timeout_s:
            if self._confirm_attempts >= self.config.max_confirm_attempts:
                self._event(snap.now, Category.CHARGING, Severity.ERROR, "CHARGER_NOT_CONFIRMED",
                            "Wallbox bestätigt die Abschaltung nicht – neuer Versuch in "
                            f"{int(OFF_RETRY_AFTER.total_seconds() // 60)} min")
                self._off_given_up_at = snap.now
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
