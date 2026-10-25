"""Engine: one complete, HA-free control tick (§4).

``Engine.tick(now, raw)`` turns raw entity states into quality-tagged values,
lets the planners and the arbiter compute the desired state, evaluates
health, runs the executor and the monitor, and returns commands, events,
finished sessions/trips and push intents. The Home Assistant coordinator and
the replay runner both drive exactly this class.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .arbiter import DEFAULT_OFF, HANDS_OFF, arbitrate
from .charge_test import ChargeTest
from .climate import (
    BLOCK_MIN,
    MAX_RESTARTS,
    climate_blocker,
    climate_request,
    climate_wish,
    planned_duration,
)
from .costs import FixedPriceHistory
from .executor import ExecState, Executor, ExecutorConfig, Snapshot, StepResult
from .external import ExternalChargeDetector
from .health import (
    STATUS_TEXT,
    Health,
    HealthInputs,
    HealthStatus,
    evaluate,
    reasons_text,
)
from .inputs import Inp, RawState, to_value
from .learning import LearnedCharging, learn
from .model import Category, ClimateRequest, Desired, Event, Quality, Reason, Severity, Value
from .monitor import Monitor
from .planner import (
    DEFAULT_PLAN,
    ChargeWindow,
    ManualOverride,
    OneShot,
    OverrideMode,
    VehicleParams,
    WeeklySchedule,
    current_kw,
    one_shot_window,
    override_wish,
    schedule_window,
    target_soc_wish,
    window_wish,
)
from .ports import Command, CommandKind
from .prices import PriceSchedule, PriceSlot
from .quality import QualityRule, charging_conflict, classify, non_negative, soc_plausible
from .sessions import ChargeSession, SessionTracker
from .settings import ClimateAfterTarget, PriceSource, Settings
from .source_policy import (
    HvCycleMonitor,
    mark_conflict,
    outside_temperature,
    plugged_in,
    vehicle_charging,
)
from .statistics import ExternalCharge
from .trips import Trip, TripTracker

HEALTH_PUSH_DEBOUNCE_S = 300


def external_price_url(charge_id: str) -> str:
    """Panel page with the price dialog (numeric keypad) for one external charge."""
    return f"/ev-pilot?external_price={charge_id}"

OVERRIDE_TEXT = {
    OverrideMode.UNTIL_UNPLUGGED: "Laden bis Kabel ab",
    OverrideMode.DURATION: "Laden für eine Dauer",
    OverrideMode.UNTIL_TIME: "Laden bis Uhrzeit",
    OverrideMode.UNTIL_SOC: "Laden bis Ladestand",
    OverrideMode.STOP: "Laden gestoppt",
}
# Wallbox status texts meaning "connector locked – cable state not reported" (Halo).
BLIND_WHEN_LOCKED = frozenset({"unavailable", "disabled"})
# Charging only makes a vehicle value STALE if it went on this long after it.
CHARGING_ACTIVITY_GRACE = timedelta(minutes=15)
# A current command the wallbox has not taken over yet is repeated after this.
CURRENT_RETRY_S = 120
ENFORCE_TARGET_MARGIN_PCT = 1
# After the target was reached a window only tops up again when a fresh SOC is
# clearly below it – otherwise an aging SOC would restart the charge (and wake the car).
TOPUP_HYSTERESIS_PCT = 3
# Wallbox and car are polled with different delays; a contradiction only counts
# once it lasts this long.
CONFLICT_GRACE_S = 180
# An OVMS "not charging" is only an end-of-charge signal while it is this recent.
FINISHED_SIGNAL_MAX_AGE = timedelta(minutes=15)
FULL_SOC_PCT = 99
# HVAC off this long before the planned end → the pilot restarts a climate block.
# 10 s (was 30): the driver noticed a silent car between two blocks (21.10.2026).
CLIMATE_GAP = timedelta(seconds=10)
# OVMS repeats the last values of a sleeping car, so a value that has not changed for
# this long is no current measurement any more (temperatures only).
UNCHANGED_STALE = timedelta(minutes=30)
CHANGE_TRACKED = (Inp.OVMS_CABIN_TEMP, Inp.OVMS_OUTSIDE_TEMP)
# A 100 % target is never ended by the SOC: the smart shows 100 % at a real ~93 %
# (field 19.10.2026) and still balances. The car ends the charge itself; once it
# has drawn no power for this long, the wallbox goes off.
FULL_TARGET_PCT = 100
FULL_END_WAIT = timedelta(minutes=3)
# The car reporting "not charging" counts as its own end of charge only from here …
CAR_FULL_PCT = 95
# … or this close to the window's target; below that it is an interruption.
FINISHED_TARGET_MARGIN_PCT = 3
REMINDER_HORIZON = timedelta(hours=12)
# The buttons of the plug-in push only apply to that plug-in, and not forever.
PLUG_OFFER_VALID = timedelta(hours=12)
CP_REASONS = ("CP_NOT_RESTORED", "CP_STATE_UNKNOWN", "CP_OPEN")
# A Shelly that drops off the WLAN for a moment keeps its last confirmed "CP closed"
# for this long (field 18.10.2026: 30 short dropouts at −80 dBm in three hours).
# Never right after a CP pulse: then only a fresh reading proves the CP is closed.
SHELLY_DROPOUT_GRACE = timedelta(minutes=3)
NO_GRACE_AFTER_PULSE = timedelta(minutes=10)
# What the user can check – shown in pushes and in the panel.
FAILURE_HINTS = {
    "CHARGE_START_FAILED": "Bitte prüfen: Stecker am Auto ganz eingerastet, Auto entriegelt, "
                           "Ladeklappe zu? Dann „Erneut versuchen“",
    "CHARGER_NOT_CONFIRMED": "Die Wallbox reagiert nicht – ist sie online (App des "
                             "Herstellers)? Dann „Erneut versuchen“",
    "CHARGE_INTERRUPTED": "Wenn der Akku nicht voll ist: Stecker prüfen, dann "
                          "„Erneut versuchen“",
}


@dataclass(frozen=True, slots=True)
class Notification:
    """A push intent (§8.3). The HA side decides how to deliver it."""

    category: str
    priority: str
    title: str
    message: str
    actionable: bool = False
    # Extra buttons, e.g. ("retry",) after a failed start.
    actions: tuple[str, ...] = ()
    # Page a tap on the push opens (default: the panel).
    url: str | None = None


@dataclass(slots=True)
class TickResult:
    commands: list[Command] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    sessions: list[ChargeSession] = field(default_factory=list)
    trips: list[Trip] = field(default_factory=list)
    external: list[ExternalCharge] = field(default_factory=list)
    notifications: list[Notification] = field(default_factory=list)

    def extend(self, other: StepResult) -> None:
        self.commands += other.commands
        self.events += other.events


@dataclass(frozen=True, slots=True)
class EngineConfig:
    settings: Settings
    tz: ZoneInfo
    configured: frozenset[Inp]
    cp_pulse_available: bool = False
    ovms_command_available: bool = False
    # The wallbox current is a writable number entity.
    current_settable: bool = False

    @property
    def cp_configured(self) -> bool:
        return Inp.CP_RELAY in self.configured

    @property
    def ovms_configured(self) -> bool:
        return Inp.OVMS_SOC in self.configured


class Engine:
    def __init__(self, config: EngineConfig, monitor: Monitor | None = None) -> None:
        self.config = config
        self.settings = config.settings
        self.tz = config.tz
        self.executor = Executor(ExecutorConfig.from_settings(
            config.settings, cp_available=config.cp_configured and config.cp_pulse_available,
            ovms_port=config.ovms_command_available))
        self.monitor = monitor or Monitor(config.tz)
        self.monitor.ovms_odometer = Inp.OVMS_ODOMETER in config.configured
        self.sessions = SessionTracker(config.settings.interval_min)
        self.trips = TripTracker(config.settings.trip_merge_gap_min, config.tz)
        self.hv = HvCycleMonitor(config.settings.hv_cycles_warn_per_day)
        self.prices = FixedPriceHistory(config.settings.price_history, config.tz)
        self.price_schedule = PriceSchedule([])
        s = config.settings
        self.external = ExternalChargeDetector(
            capacity_kwh=s.usable_capacity_kwh, efficiency=s.charge_efficiency,
            min_kwh=s.external_min_kwh, soc_jump_pct=s.external_soc_jump_pct,
            price_eur_kwh=s.external_price_eur_kwh, threshold_w=s.power_threshold_w,
            tz=config.tz)

        self.plans: list[WeeklySchedule] = [DEFAULT_PLAN]
        self.override: ManualOverride | None = None
        self.charge_test: ChargeTest | None = None
        self._test_override: ManualOverride | None = None
        self.one_shot: OneShot | None = None
        self.manual_climate: ClimateRequest | None = None
        self.automation_enabled = True

        self.values: dict[Inp, Value] = {}
        self.soc: Value = Value.unavailable("ovms")
        self.outside: Value = Value.unavailable("none")
        self.health = Health(HealthStatus.HEALTHY)
        self.desired: Desired | None = None
        self.windows: list[ChargeWindow] = []
        self.active_window: ChargeWindow | None = None
        self.next_window: ChargeWindow | None = None
        self.climate_plan: ClimateRequest | None = None
        self.climate_blocked: str | None = None
        # The climate request once its start is reached: frozen (a temperature change
        # must not move it and send a second command) with its progress:
        # due → sent → running (car reports HVAC on) → done; or skipped.
        self._climate_lock: ClimateRequest | None = None
        self._climate_restarts = 0
        self._climate_off_since: datetime | None = None
        # A charge paused below its target: (target %, the request that charged).
        self._pause_hold: tuple[int | None, Desired] | None = None
        self._pause_pushed = False
        self.cabin_changed_at: datetime | None = None
        # Last real change per tracked input: (state, when). HA resets last_updated
        # on every restart, so this is kept in the store.
        self._changed: dict[Inp, tuple[str, datetime]] = {}
        # Last moment the Shelly confirmed "CP closed" (for SHELLY_DROPOUT_GRACE).
        self._relay_closed_at: datetime | None = None
        self.climate_phase: str | None = None
        self.data_conflict = False
        self.last_activity_at: datetime | None = None
        # Last moment the wallbox delivered power – charging changes the SOC only slowly.
        self._charging_at: datetime | None = None
        self.last_result: dict[str, Any] | None = None

        self._latched: dict[str, ChargeWindow] = {}
        self._latched_raw: dict[str, Any] = {}
        self._cable: bool | None = None
        self._overrun_key: str | None = None
        # Automation off: the end of a manual override still switches the wallbox off once.
        self._had_override = False
        self._off_after_override = False
        self._current_sent: tuple[int, datetime] | None = None
        self._pending_events: list[Event] = []
        self._reminder_day: date | None = None
        self._health_candidate: tuple[HealthStatus, datetime] | None = None
        self._health_notified = HealthStatus.HEALTHY
        self._cp_alarm = False
        self._was_conflict = False
        self._conflict_since: datetime | None = None
        self._target_hold: str | None = None
        self.learned = LearnedCharging()
        self._learned_key: tuple[int, str | None] | None = None
        self.plug_offer_at: datetime | None = None
        self.last_unplug_at: datetime | None = None
        self.shadow = False
        self._virtual_charger: bool | None = None
        self.shelly_config_ok: bool | None = None

    def set_shadow(self, shadow: bool) -> None:
        """Dry-run/replay: switching is only logged, the executor works on a virtual
        wallbox state. Changing the mode re-derives the executor state from reality."""
        if shadow == self.shadow:
            return
        self.shadow = shadow
        self.executor.shadow = shadow
        self.executor.state = None
        self._virtual_charger = None

    # ================================================================ tick

    def tick(self, now: datetime, raw: dict[Inp, RawState | None]) -> TickResult:
        result = TickResult()
        self._read_values(now, raw)
        values = self.values

        cable = values[Inp.CABLE_CONNECTED]
        cable_flag = bool(cable.normalized) if cable.available else None
        status = values[Inp.CHARGER_STATUS]
        locked_blind = cable_flag is False and Inp.OVMS_PLUG not in self.config.configured \
            and values[Inp.CHARGER_ENABLE].normalized is False and status.available \
            and str(status.normalized).strip().lower() in BLIND_WHEN_LOCKED
        if locked_blind:
            # A locked Halo reports status "Unavailable" and never sees the cable: without
            # the car's own plug signal "no cable" is unknown, not "unplugged".
            cable_flag = None
            cable = cable.with_quality(Quality.UNAVAILABLE)
        elif cable_flag is False and Inp.OVMS_PLUG in self.config.configured \
                and not values[Inp.OVMS_PLUG].available:
            # Right after a restart the OVMS plug may not be there yet: "no cable" from
            # the locked Halo alone says nothing – otherwise the car seems plugged in anew.
            cable_flag = None
            cable = cable.with_quality(Quality.UNAVAILABLE)
        plugged_in_event = self._cable is False and cable_flag is True \
            and not self.executor.cp_masked(now)
        if cable_flag is not None and cable_flag != self._cable \
                and not self.executor.cp_masked(now):
            # The first observation (e.g. after a restart) is no plug event.
            if self._cable is not None:
                self.last_activity_at = now
                if cable_flag is False:
                    self.last_unplug_at = now
            self._cable = cable_flag

        # During a CP pulse the wallbox briefly sees "no vehicle" (§3.4): that must not
        # end a "Jetzt laden" override or the charge test that caused the pulse.
        self._expire(now, None if self.executor.cp_masked(now) else cable_flag)
        if self._had_override and self.override is None:
            self._off_after_override = True
        self._had_override = self.override is not None
        charger_value = self.values[Inp.CHARGER_ENABLE]
        if self.automation_enabled or self.override is not None or (
                charger_value.available and charger_value.normalized is False):
            self._off_after_override = False
        self._plan(now)
        result.events += self._pending_events
        self._pending_events.clear()

        self.health = evaluate(self._health_inputs(now))
        self._climate(now)
        self.desired = self._arbitrate(now, cable_flag is True)
        self.desired = replace(self.desired, current_a=self._current_for(self.desired))
        self._set_current(now, result)

        charger_on = values[Inp.CHARGER_ENABLE]
        if self.shadow:
            if self._virtual_charger is None and charger_on.available:
                self._virtual_charger = bool(charger_on.normalized)
            if self._virtual_charger is not None:
                charger_on = Value(charger_on.raw, self._virtual_charger, "virtual", now)
        result.extend(self.executor.step(Snapshot(
            now=now,
            desired=self.desired,
            health=self.health,
            cable_connected=cable,
            charger_on=charger_on,
            power_w=values[Inp.CHARGE_POWER],
            charger_status=values[Inp.CHARGER_STATUS]
            if values[Inp.CHARGER_STATUS].available else None,
            cp_relay_on=values[Inp.CP_RELAY] if self.config.cp_configured else None,
            vehicle_charging=self._vehicle_charging,
            vehicle_charge_finished=self._vehicle_finished(now),
            below_target=self._below_target(),
        )))
        if self.shadow:
            for command in result.commands:
                if command.kind is CommandKind.ENABLE_CHARGER:
                    self._virtual_charger = True
                elif command.kind is CommandKind.DISABLE_CHARGER:
                    self._virtual_charger = False
        self._pause_bookkeeping(result, cable_flag is True)
        self._climate_progress(now, result)
        self._charge_test(now, result)
        self._monitor(now, result)
        self._notifications(now, result, plugged_in_event, cable_flag)
        if self.data_conflict and not self._was_conflict:
            result.events.append(Event(now, Category.HEALTH, Severity.WARNING, "DATA_CONFLICT",
                                       "Wallbox und Fahrzeug widersprechen sich beim Ladezustand"))
        return result

    # ------------------------------------------------------------- values

    def _read_values(self, now: datetime, raw: dict[Inp, RawState | None]) -> None:
        s = self.settings
        ages = s.max_ages
        values = {key: to_value(key, raw.get(key)) if key in self.config.configured
                  else Value.unavailable("none") for key in Inp}
        # A sleeping car repeats its last temperatures (cabin 23 °C all night at a real
        # 11 °C, field 19.10.2026): only a change proves the value is current.
        for key in CHANGE_TRACKED:
            item = raw.get(key)
            if item is None or key not in self.config.configured:
                continue
            seen = self._changed.get(key)
            if seen is None or seen[0] != str(item.state):
                self._changed[key] = (str(item.state), item.last_updated or now)
        cabin_seen = self._changed.get(Inp.OVMS_CABIN_TEMP)
        self.cabin_changed_at = cabin_seen[1] if cabin_seen else None

        power = values[Inp.CHARGE_POWER]
        if power.available and power.normalized is not None \
                and float(power.normalized) > s.power_threshold_w:
            self._charging_at = now
        vehicle_on = values[Inp.OVMS_VEHICLE_ON]
        if vehicle_on.available and vehicle_on.normalized:
            self.last_activity_at = now

        def rule(age, plausible=None):
            return QualityRule(max_age_s=age, plausible=plausible)

        # A value from a sleeping car keeps LAST_KNOWN_VALID until activity (§7.2).
        for key, r in (
            (Inp.OVMS_SOC, rule(ages.soc_s, soc_plausible)),
            (Inp.OVMS_SOH, rule(ages.odometer_s, soc_plausible)),
            (Inp.OVMS_RANGE, rule(ages.soc_s, non_negative)),
            (Inp.OVMS_ODOMETER, rule(ages.odometer_s, non_negative)),
            (Inp.OVMS_CHARGING, rule(ages.vehicle_charging_s)),
            (Inp.OVMS_CHARGE_POWER, rule(ages.vehicle_charging_s)),
            (Inp.OVMS_VEHICLE_ON, rule(ages.vehicle_charging_s)),
            (Inp.OVMS_BATTERY_TEMP, rule(ages.temperature_s)),
            (Inp.OVMS_OUTSIDE_TEMP, rule(ages.temperature_s)),
            (Inp.OVMS_HV_CYCLES, rule(ages.odometer_s, non_negative)),
            (Inp.OVMS_ENERGY_USED, rule(ages.odometer_s)),
            (Inp.OVMS_ENERGY_RECD, rule(ages.odometer_s)),
            (Inp.OVMS_AUX_CONSUMPTION, rule(ages.odometer_s)),
            (Inp.OVMS_12V, rule(ages.temperature_s)),
            (Inp.OVMS_HVAC, rule(ages.vehicle_charging_s)),
            (Inp.OVMS_BATTERY_POWER, rule(ages.vehicle_charging_s)),
            (Inp.OVMS_SPEED, rule(ages.vehicle_charging_s)),
            (Inp.OVMS_LOCKED, rule(ages.vehicle_charging_s)),
            (Inp.OVMS_CABIN_TEMP, rule(ages.temperature_s)),
            (Inp.OVMS_CHARGE_ENERGY, rule(ages.odometer_s)),
        ):
            values[key] = classify(values[key], now, r, self._activity_for_quality())
        for key, r in (
            (Inp.OUTSIDE_TEMP, rule(ages.temperature_s)),
            (Inp.WEATHER, rule(ages.temperature_s * 4)),
            (Inp.TOTAL_ENERGY, rule(ages.halo_energy_s, non_negative)),
        ):
            values[key] = classify(values[key], now, r)
        # The Halo power is the stability signal; the polling interval decides
        # how old it may be (§7.3). Other Halo values keep their raw quality.
        values[Inp.CHARGE_POWER] = classify(power, now, rule(ages.halo_power_s, non_negative))

        self._was_conflict = self.data_conflict
        # While the car heats from the grid it draws power without charging – that is
        # no contradiction (field 19.10.2026: DATA_CONFLICT during the climate).
        # Away from home the wallbox is not involved at all (field 21.10.2026: charging
        # at a supermarket raised a conflict).
        at_home = values[Inp.CABLE_CONNECTED].normalized is not False
        if charging_conflict(values[Inp.CHARGE_POWER], values[Inp.OVMS_CHARGING],
                             s.power_threshold_w) and not self._climate_heating(values) \
                and at_home:
            self._conflict_since = self._conflict_since or now
        else:
            self._conflict_since = None
        self.data_conflict = self._conflict_since is not None and \
            (now - self._conflict_since).total_seconds() >= CONFLICT_GRACE_S
        if self.data_conflict:
            values[Inp.CHARGE_POWER], values[Inp.OVMS_CHARGING] = mark_conflict(
                values[Inp.CHARGE_POWER], values[Inp.OVMS_CHARGING])
            # The executor still needs the raw power samples to measure stability.
            values[Inp.CHARGE_POWER] = values[Inp.CHARGE_POWER].with_quality(Quality.CONFLICT)

        values[Inp.CABLE_CONNECTED] = plugged_in(
            values[Inp.CABLE_CONNECTED], values[Inp.OVMS_PLUG], values[Inp.OVMS_LOCATION])

        for key, (_, changed_at) in self._changed.items():
            if now - changed_at > UNCHANGED_STALE and values[key].quality is Quality.GOOD:
                values[key] = replace(values[key], quality=Quality.LAST_KNOWN_VALID)
        self.values = values
        self.soc = values[Inp.OVMS_SOC]
        self.outside = outside_temperature(
            values[Inp.OVMS_OUTSIDE_TEMP], values[Inp.OUTSIDE_TEMP], values[Inp.WEATHER])
        self._vehicle_charging = vehicle_charging(
            values[Inp.OVMS_CHARGING], values[Inp.CHARGE_POWER], s.power_threshold_w)

    def _activity_for_quality(self) -> datetime | None:
        """Activity that makes an older vehicle value STALE.

        Driving and (un)plugging count at once. Charging counts only when it went on
        well after a value was recorded: the wallbox (cloud polling) reports its last
        power a few minutes after the car's last SOC, and the car then sleeps – that
        SOC is right, not stale (it would otherwise block climate and SOC functions
        after every charge).
        """
        charging = self._charging_at - CHARGING_ACTIVITY_GRACE if self._charging_at else None
        candidates = [t for t in (self.last_activity_at, charging) if t is not None]
        return max(candidates) if candidates else None

    def _vehicle_finished(self, now: datetime) -> bool:
        """The car ended the charge itself (§6.3 step 1).

        A car that falls asleep right after a full charge stops reporting, so a
        recent "not charging" also counts once it is no longer GOOD, and so does
        a full battery.
        """
        soc = self.soc
        level = float(soc.normalized) if soc.quality.usable_for_planning \
            and soc.normalized is not None else None
        if level is not None and level >= FULL_SOC_PCT:
            return True
        charging = self.values[Inp.OVMS_CHARGING]
        stopped = charging.normalized is False and charging.quality in (
            Quality.GOOD, Quality.LAST_KNOWN_VALID) and charging.updated_at is not None \
            and now - charging.updated_at <= FINISHED_SIGNAL_MAX_AGE
        if not stopped:
            return False
        # "Not charging" alone also happens on a real interruption (RCD, wallbox fault).
        # The car ended the charge itself only near full or near the window's target.
        window = self.active_window
        target = window.preferred_soc_pct if window else None
        if level is None:
            return True  # nothing better to go by – trust the car
        return level >= CAR_FULL_PCT or (target is not None
                                         and level >= target - FINISHED_TARGET_MARGIN_PCT)

    # ------------------------------------------------------------ planning

    def _params(self) -> VehicleParams:
        s = self.settings
        nominal = VehicleParams(
            usable_capacity_kwh=s.usable_capacity_kwh,
            charge_efficiency=s.charge_efficiency,
            halo_limit_kw=s.max_power_kw,
            vehicle_charger_kw=s.vehicle_charger_kw,
            grid_limit_kw=s.grid_limit_kw,
            taper_from_pct=s.taper_from_pct,
            full_soc_pct=s.full_soc_pct,
            full_hold_max_h=s.full_hold_max_h,
            phases=s.phases,
            current_a=self._wallbox_current(),
        )
        learned = self._learn(nominal)
        if not s.learn_charging or not learned.active:
            return nominal
        return replace(nominal, learned_kwh_per_pct=learned.grid_kwh_per_pct,
                       learned_power_kw=learned.power_kw)

    def _wallbox_current(self) -> float | None:
        """The current a charge without its own setting runs at."""
        if self.settings.default_current_a and self.config.current_settable:
            return float(self.settings.default_current_a)
        current = self.values.get(Inp.MAX_CURRENT) if self.values else None
        if current is not None and current.available and current.normalized is not None:
            return float(current.normalized)
        return None

    def _current_for(self, desired: Desired) -> int | None:
        """Current for the winning wish: its own, "Jetzt laden" or the default."""
        if not self.config.current_settable or desired.charger_enabled is not True:
            return None
        s = self.settings
        if desired.reason is Reason.OVERRIDE and s.manual_current_a:
            return s.manual_current_a
        return desired.current_a or s.default_current_a or None

    def _set_current(self, now: datetime, result: TickResult) -> None:
        """Set the wallbox current before and while charging (never when it stays off)."""
        amps = self.desired.current_a if self.desired else None
        if amps is None:
            return
        actual = self.values[Inp.MAX_CURRENT]
        if actual.available and actual.normalized is not None \
                and abs(float(actual.normalized) - amps) < 0.5:
            self._current_sent = None
            return
        if self._current_sent is not None and self._current_sent[0] == amps and (
                self.shadow or (now - self._current_sent[1]).total_seconds() < CURRENT_RETRY_S):
            # Dry run: the wallbox never takes the value over – log it once.
            return
        self._current_sent = (amps, now)
        result.commands.append(Command(CommandKind.SET_CURRENT, {"amps": amps}))
        kw = f"{current_kw(amps, self.settings.phases):.1f}".replace(".", ",")
        result.events.append(Event(now, Category.CHARGING, Severity.INFO, "CURRENT_SET",
                                   f"Ladestrom {amps} A (ca. {kw} kW)", data={"amps": amps}))

    def _learn(self, nominal: VehicleParams) -> LearnedCharging:
        """Re-learn only when a session was added (cheap enough, but not every tick)."""
        sessions = self.monitor.data.sessions
        key = (len(sessions), sessions[-1].session_id if sessions else None)
        if key != self._learned_key:
            self._learned_key = key
            self.learned = learn(sessions, nominal_kwh_per_pct=nominal.kwh_per_pct,
                                 max_power_kw=nominal.wallbox_limit_kw)
        return self.learned

    def _expire(self, now: datetime, cable: bool | None) -> None:
        if self.override and self.override.expired(now, cable is not False, self.soc):
            self.override = None
        if self.one_shot and self.one_shot.expired(now):
            self.one_shot = None
        if self.manual_climate and now >= self.manual_climate.until:
            self.manual_climate = None

    def _latch(self, window: ChargeWindow | None, now: datetime) -> ChargeWindow | None:
        """Once a window has started its start is frozen.

        Otherwise a rising SOC would shorten the computed duration, push the
        start past ``now`` and stop the running charge.
        """
        if window is None:
            return None
        latched = self._latched.get(window.key)
        raw = self._latched_raw.pop(window.key, None)
        if latched is None and raw is not None:
            # Restored after a restart (§6.5): the night keeps its plan.
            latched = replace(window, start=datetime.fromisoformat(raw["start"]), blocks=tuple(
                (datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b in raw["blocks"]))
            self._latched[window.key] = latched
        if latched is not None:
            # Keep start and price blocks, refresh the estimate.
            return replace(window, start=latched.start, blocks=latched.blocks)
        # Only a start the car is plugged in for is frozen. A cheap block that passes
        # while the car is away (office, daytime prices) is planned again from now.
        if window.start <= now and self._cable is not False:
            self._latched[window.key] = window
        return window

    def _plan(self, now: datetime) -> None:
        params = self._params()
        prices, blocks = self._planning_prices()
        windows = [self._latch(schedule_window(p, now, self.tz, self.soc, params, prices,
                                               blocks), now)
                   for p in self.plans if p.enabled]
        if self.one_shot:
            windows.insert(0, self._latch(
                one_shot_window(self.one_shot, now, self.tz, self.soc, params, prices, blocks),
                now))
        self.windows = [self._overrun(w, now) for w in windows if w is not None]
        self.active_window = next((w for w in self.windows if w.contains(now)), None)
        upcoming = sorted(self.windows, key=lambda w: w.start)
        self.next_window = self.active_window or (upcoming[0] if upcoming else None)
        keep = {w.key for w in self.windows}
        self._latched = {k: v for k, v in self._latched.items() if k in keep}
        if self._target_hold not in keep:
            self._target_hold = None
        self.executor.prune_expired(now)

    def _overrun(self, window: ChargeWindow, now: datetime) -> ChargeWindow:
        """A price block that ends while the car is still charging keeps going.

        Waking up or a cold battery can eat the reserve; stopping at the block's end
        would leave the car below its target although there is time until "ready".
        The charge continues until the target, the car stops it, or "ready" – the car
        is awake, so nothing is woken for it.
        """
        if not window.blocks or window.key not in self._latched \
                or self._target_hold == window.key:
            return window
        start, end = window.blocks[-1]
        if not end <= now < window.ready_at or self.executor.state not in (
                ExecState.CHARGING, ExecState.CHARGE_STABILIZING):
            return window
        if self._overrun_key != window.key:
            self._overrun_key = window.key
            self._pending_events.append(Event(
                now, Category.CHARGING, Severity.INFO, "BLOCK_EXTENDED",
                "Ladeziel zum Blockende noch nicht erreicht – lade weiter bis zum Ziel"))
        return replace(window, blocks=(*window.blocks[:-1], (start, window.ready_at)),
                       overrun=True)

    @property
    def target_held(self) -> bool:
        """The running window already reached its target and keeps the wallbox off."""
        return self.active_window is not None and self._target_hold == self.active_window.key

    def set_vehicle_commands(self, available: bool) -> None:
        """The command path may appear later (OVMS integration starts after us)."""
        if available == self.config.ovms_command_available:
            return
        self.config = replace(self.config, ovms_command_available=available)
        self.executor.config = ExecutorConfig.from_settings(
            self.settings, cp_available=self.config.cp_configured
            and self.config.cp_pulse_available, ovms_port=available)

    # -------------------------------------------------------------- prices

    def set_prices(self, slots: list[PriceSlot]) -> None:
        """New dynamic prices (Tibber/entity). Old slots are kept for costing."""
        known = {s.start: s for s in self.price_schedule.slots}
        if slots:
            # New prices replace everything they cover – also old slots of another
            # length (15-min source → hourly source), which a start-only merge kept.
            first, last = min(s.start for s in slots), max(s.end for s in slots)
            known = {k: v for k, v in known.items() if not (first <= k < last)}
        known.update({s.start: s for s in slots})
        horizon = max(known) - timedelta(days=3) if known else None
        self.price_schedule = PriceSchedule(
            s for start, s in known.items() if horizon is None or start >= horizon)

    @property
    def dynamic_prices(self) -> bool:
        return self.settings.price_source is not PriceSource.FIXED and bool(self.price_schedule)

    def _planning_prices(self) -> tuple[PriceSchedule | None, int]:
        if not self.dynamic_prices or not self.settings.price_optimization:
            return None, 0
        return self.price_schedule, max(1, self.settings.price_blocks)

    def price_at(self, moment: datetime) -> float:
        dynamic = self.price_schedule.price_at(moment) if self.dynamic_prices else None
        return dynamic if dynamic is not None else self.prices.price_at(moment)

    def _dynamic_price(self, moment: datetime) -> float | None:
        return self.price_schedule.price_at(moment) if self.dynamic_prices else None

    def _climate(self, now: datetime) -> None:
        """Planned climate for the next departure (§9.2)."""
        self.climate_plan = None
        if self.manual_climate is not None:
            self.climate_plan = self.manual_climate
        elif self.next_window is not None and self.automation_enabled:
            minutes = planned_duration(self.next_window.climate, self.outside, self.settings)
            self.climate_plan = climate_request(self.next_window.departure, minutes)
        lock = self._climate_lock
        if lock is not None and (now >= lock.until or (
                self.manual_climate is not None and self.manual_climate.key != lock.key)):
            lock = self._climate_lock = None
            self.climate_phase = None
            self._climate_restarts = 0
            self._climate_off_since = None
        if lock is not None:
            self.climate_plan = lock
        elif self.climate_plan is not None and self.climate_plan.start_at <= now \
                < self.climate_plan.until:
            self._climate_lock = self.climate_plan
            self.climate_phase = "due"
        degraded = self.health.blocks_soc_functions
        self.climate_blocked = climate_blocker(self.soc, self.settings, degraded) \
            if self.climate_plan else None
        if self.climate_active:
            # A climate the car already runs is not cut off halfway because a value
            # aged meanwhile (outside temperature, SOC); a safety lock still stops it.
            self.climate_blocked = None

    def _climate_progress(self, now: datetime, result: TickResult) -> None:
        """Follow the running climate: command sent, HVAC on, gaps, restarts.

        The smart climatises in 5-minute blocks. When the car reports its HVAC off
        before the planned end (departure + 5 min) for ``CLIMATE_GAP``, the pilot
        sends one more block itself (at most ``MAX_RESTARTS``). The wallbox stays on
        until the planned end – a gap between blocks never cuts the grid power
        (field 20.10.2026: OVMS skipped the third block, the cabin cooled down).
        """
        lock = self._climate_lock
        if lock is None:
            return
        for event in result.events:
            if event.code == "CLIMATE_START" and self.climate_phase in (None, "due"):
                self.climate_phase = "sent"
            elif event.code == "CLIMATE_SKIPPED":
                self.climate_phase = "skipped"
        hvac = self.values.get(Inp.OVMS_HVAC)
        if hvac is None or not hvac.available or hvac.normalized is None:
            return
        if hvac.normalized:
            self._climate_off_since = None
            if self.climate_phase in ("sent", "gap"):
                self.climate_phase = "running"
            return
        if self.climate_phase not in ("running", "gap"):
            return
        self._climate_off_since = self._climate_off_since or now
        remaining = lock.until - now
        if self.climate_phase == "running":
            self.climate_phase = "gap"
        if remaining >= timedelta(minutes=2) and self._climate_restarts < MAX_RESTARTS \
                and now - self._climate_off_since >= CLIMATE_GAP:
            self._climate_restarts += 1
            self._climate_off_since = None
            result.extend(self.executor.request_climate_restart(
                now, BLOCK_MIN, self._climate_restarts))
            self.climate_phase = "sent"
        elif remaining < timedelta(minutes=2) or self._climate_restarts >= MAX_RESTARTS:
            self.climate_phase = "finished"
            result.events.append(Event(now, Category.CLIMATE, Severity.INFO, "CLIMATE_ENDED",
                                       "Vorklimatisierung beendet – Auto meldet Klima aus; "
                                       f"Wallbox bleibt frei bis {lock.until:%H:%M} UTC"))

    def _full_charge_ended(self, now: datetime, window) -> Desired | None:
        """Target 100 %: off only after the car ended the charge itself (FULL_END_WAIT)."""
        ex = self.executor
        if window is None or ex.state is not ExecState.CHARGE_ENDED or ex.state_since is None \
                or now - ex.state_since < FULL_END_WAIT:
            return None
        soc = self.soc
        if soc.quality is not Quality.GOOD or soc.normalized is None \
                or float(soc.normalized) < FULL_SOC_PCT:
            # "The car stopped" at 60 % is a pause, not a full battery (Frank, 20.10.2026).
            return None
        return Desired(False, Reason.TARGET_SOC_REACHED, source_id="vehicle_full")

    def _climate_heating(self, values: dict[Inp, Value]) -> bool:
        """Is the car's climate drawing power right now? The car's own report wins."""
        hvac = values.get(Inp.OVMS_HVAC)
        if Inp.OVMS_HVAC in self.config.configured and hvac is not None and hvac.available:
            return bool(hvac.normalized)
        return self.climate_active

    @property
    def climate_active(self) -> bool:
        """The climate command went out and the climate has not ended yet."""
        return self.climate_phase in ("sent", "running", "gap")

    def _arbitrate(self, now: datetime, plugged_in: bool) -> Desired:
        s = self.settings
        climate_req = self.climate_plan if self.climate_blocked is None \
            and self.climate_phase not in ("done", "skipped") else None
        climate_running = climate_req is not None and climate_req.start_at <= now < \
            climate_req.until
        wishes: list[Desired | None] = [override_wish(self.override)]
        if self.manual_climate is not None and climate_req is not None:
            wishes.append(climate_wish(climate_req, now, plugged_in, "manual"))
        if self.automation_enabled:
            one_shot = next((w for w in self.windows if w.reason is Reason.ONE_SHOT), None)
            window = self.active_window
            target = window.preferred_soc_pct if window else None
            soc = None if self.health.blocks_soc_functions else self.soc
            topup = climate_running and s.climate_after_target is ClimateAfterTarget.ALLOW_TOPUP
            if climate_running and s.climate_after_target is ClimateAfterTarget.ENFORCE_TARGET \
                    and target is not None:
                target += ENFORCE_TARGET_MARGIN_PCT
            if target is not None and target >= FULL_TARGET_PCT:
                reached = self._full_charge_ended(now, window)
            else:
                reached = target_soc_wish(soc, target, climate_topup_active=topup)
            if reached is not None and window is not None:
                self._target_hold = window.key
            hold = window is not None and self._target_hold == window.key
            if hold and reached is None and not topup:
                fresh_below = soc is not None and soc.quality is Quality.GOOD and \
                    float(soc.normalized) < target - TOPUP_HYSTERESIS_PCT
                if not fresh_below:
                    reached = Desired(False, Reason.TARGET_SOC_REACHED,
                                      source_id=f"held>={target}")
            wishes.append(reached)
            # The one-off departure ranks above "target reached" (§4.2) – so it only
            # wishes to charge while its own target is not reached (like a weekly plan).
            if not (reached is not None and window is not None and window is one_shot):
                wishes.append(window_wish(one_shot, now))
            if self.manual_climate is None:
                wishes.append(climate_wish(climate_req, now, plugged_in, "plan"))
            wishes += [window_wish(w, now) for w in self.windows if w.reason is Reason.SCHEDULE]
        desired = arbitrate(
            wishes,
            safety_lock=self.health.blocks_automation,
            # Automation off leaves the wallbox alone – except right after a manual
            # override ended (target reached, time over): that switch-off is still ours.
            default=DEFAULT_OFF if self.automation_enabled or self._off_after_override
            else HANDS_OFF,
        )
        if self.active_window is not None and self.active_window.overrun \
                and desired.charger_enabled and desired.source_id == self.active_window.source_id:
            desired = replace(desired, wake_allowed=False)
        if self.active_window is not None and self._target_hold == self.active_window.key \
                and desired.charger_enabled and desired.reason in (
                    Reason.SCHEDULE, Reason.ONE_SHOT, Reason.CLIMATE):
            # Topping up after the target: the car is awake anyway or it is not worth a wakeup.
            desired = replace(desired, wake_allowed=False)
        if desired.charger_enabled and desired.wake_allowed and desired.reason in (
                Reason.SCHEDULE, Reason.ONE_SHOT) and self._target_known_reached():
            # The last known SOC already meets the target: the wallbox may offer power,
            # but waking the car only to learn its SOC is forbidden (§1.1 rule 2).
            desired = replace(desired, wake_allowed=False)
        hold = self._pause_hold
        if hold is not None and plugged_in and desired.reason is Reason.DEFAULT_OFF:
            # A charge paused below its target keeps its wallbox until the cable is
            # pulled – also after the window or price block (Frank, 20.10.2026).
            desired = replace(hold[1], valid_until=None, held_key=hold[1].window_key)
        return desired

    def _soc_text(self) -> str:
        soc = self.soc
        return f"{float(soc.normalized):.0f} %" if soc.available and soc.normalized is not None \
            else "unbekanntem Ladestand"

    def _target_known_reached(self) -> bool:
        """Does a SOC that is not fresh (sleeping car) already meet the window's target?

        A GOOD SOC is handled by the target shutdown itself; an older value may not
        switch off (rule 6), but it is reason enough not to wake the car.
        """
        window = self.active_window
        soc = self.soc
        if window is None or soc.normalized is None or soc.quality is Quality.GOOD \
                or not soc.quality.usable_for_planning:
            return False
        return float(soc.normalized) >= min(window.preferred_soc_pct, FULL_SOC_PCT)

    def _below_target(self) -> bool | None:
        """Is a GOOD SOC clearly below the target of the running charge?"""
        window = self.active_window
        target = window.preferred_soc_pct if window else \
            (self._pause_hold[0] if self._pause_hold else None)
        soc = self.soc
        if target is None or soc.quality is not Quality.GOOD or soc.normalized is None:
            return None
        return float(soc.normalized) < min(target, FULL_SOC_PCT) - FINISHED_TARGET_MARGIN_PCT

    def _pause_bookkeeping(self, result: TickResult, plugged_in: bool) -> None:
        """Remember the request of a paused charge; forget it once it is over."""
        if any(e.code == "CHARGE_PAUSED" for e in result.events) and self.desired \
                and self.desired.charger_enabled:
            window = self.active_window
            self._pause_hold = (window.preferred_soc_pct if window else None, self.desired)
            return
        if self._pause_hold is None:
            return
        target, soc = self._pause_hold[0], self.soc
        reached = target is not None and soc.quality is Quality.GOOD \
            and soc.normalized is not None and float(soc.normalized) >= target
        over = self.executor.state in (ExecState.IDLE, ExecState.DISCONNECTED,
                                       ExecState.START_FAILED, ExecState.CHARGE_ENDED)
        if not plugged_in or reached or over:
            self._pause_hold = None

    # -------------------------------------------------------------- health

    def _shelly_dropout_tolerated(self, now: datetime) -> bool:
        """Unreachable Shelly, but it confirmed "CP closed" moments ago (no pulse since)."""
        closed_at, pulse_at = self._relay_closed_at, self.executor.last_pulse_at
        return closed_at is not None and now - closed_at < SHELLY_DROPOUT_GRACE \
            and not (pulse_at is not None and now - pulse_at < NO_GRACE_AFTER_PULSE)

    def _health_inputs(self, now: datetime) -> HealthInputs:
        v = self.values
        cfg = self.config
        relay = v[Inp.CP_RELAY]
        relay_on = bool(relay.normalized) if relay.available else None
        if relay_on is True:
            self._relay_closed_at = now
        elif relay_on is False:
            self._relay_closed_at = None
        elif self._shelly_dropout_tolerated(now):
            relay_on = True
        schedule = v[Inp.INTERNAL_SCHEDULE]
        needs_temperature = self.settings.climate_enabled and any(
            w.climate == "auto" for w in self.windows)
        return HealthInputs(
            halo_available=v[Inp.CHARGER_ENABLE].available,
            in_charge_window=self.active_window is not None,
            cp_configured=cfg.cp_configured,
            shelly_available=(relay_on is not None) if cfg.cp_configured else None,
            cp_relay_on=relay_on,
            cp_pulse_running=self.executor.cp_masked(now),
            cp_not_restored=self.executor.cp_not_restored,
            ovms_configured=cfg.ovms_configured,
            ovms_available=v[Inp.OVMS_SOC].quality is not Quality.UNAVAILABLE
            if cfg.ovms_configured else None,
            soc_stale=self.soc.quality is Quality.STALE,
            temperature_missing=needs_temperature and not self.outside.available,
            halo_internal_schedule_on=bool(schedule.normalized) if schedule.available else None,
            shelly_auto_on_ok=self.shelly_config_ok,
            consecutive_start_failures=self.executor.consecutive_start_failures,
        )

    # ------------------------------------------------------------- monitor

    def _monitor(self, now: datetime, result: TickResult) -> None:
        v = self.values
        local_day = now.astimezone(self.tz).date()
        self.monitor.record_day(local_day)

        started_now = any(e.code in ("CHARGE_STABLE", "CHARGE_RESUMED") for e in result.events)
        if self.executor.state is ExecState.CHARGING and self.sessions.open is None \
                and not started_now:
            # Restart during a session: reopen it from the Halo counter (§6.5).
            result.events.append(Event(now, Category.CHARGING, Severity.INFO, "SESSION_RESUMED",
                                       "Laufende Ladung nach Neustart übernommen",
                                       self.executor.session_id))
            self.sessions.update(now, [Event(now, Category.CHARGING, Severity.INFO,
                                             "CHARGE_STABLE", "", self.executor.session_id)],
                                 total_energy=v[Inp.TOTAL_ENERGY], power=v[Inp.CHARGE_POWER],
                                 vehicle_power=v[Inp.OVMS_CHARGE_POWER], soc=self.soc,
                                 reason=self.desired.reason if self.desired else None,
                                 prices=self.prices)
        if self.sessions.open is not None and self.executor.session_id is None \
                and self.executor.state is ExecState.CHARGING:
            self.executor.session_id = self.sessions.open.session_id

        closed = self.sessions.update(
            now, result.events,
            total_energy=v[Inp.TOTAL_ENERGY], power=v[Inp.CHARGE_POWER],
            vehicle_power=v[Inp.OVMS_CHARGE_POWER], soc=self.soc,
            reason=self.desired.reason if self.desired else None, prices=self.prices,
            dynamic_price=self._dynamic_price,
            climate=self._climate_heating(v), battery_power=v.get(Inp.OVMS_BATTERY_POWER),
            efficiency=self.settings.charge_efficiency,
            charge_energy=v.get(Inp.OVMS_CHARGE_ENERGY),
        )
        if self.shadow:
            # A start that "failed" only because nothing was switched is no session.
            closed = [c for c in closed if c.success]
        for session in closed:
            self.monitor.add_session(session)
            self.last_result = {
                "at": (session.ended_at or now).isoformat(),
                "success": session.success,
                "failure_code": session.failure_code,
                "energy_kwh": session.grid_energy_kwh,
                "session_id": session.session_id,
            }
        result.sessions += closed

        trips = self.trips.update(
            now,
            vehicle_on=v[Inp.OVMS_VEHICLE_ON],
            odometer=v[Inp.OVMS_ODOMETER],
            energy_used=v[Inp.OVMS_ENERGY_USED],
            energy_recd=v[Inp.OVMS_ENERGY_RECD],
            aux=v[Inp.OVMS_AUX_CONSUMPTION],
            soc=self.soc,
            outside_temp=self.outside,
            speed=v.get(Inp.OVMS_SPEED),
            battery_power=v.get(Inp.OVMS_BATTERY_POWER),
            locked=v.get(Inp.OVMS_LOCKED),
            range_km=v.get(Inp.OVMS_RANGE),
        )
        for trip in trips:
            self.monitor.add_trip(trip)
        result.trips += trips

        if self.settings.external_detection and self.config.ovms_configured:
            cable = v[Inp.CABLE_CONNECTED]
            for charge in self.external.update(
                now,
                vehicle_charging=v[Inp.OVMS_CHARGING],
                vehicle_power=v[Inp.OVMS_CHARGE_POWER],
                soc=self.soc,
                halo_power=v[Inp.CHARGE_POWER],
                cable_connected=bool(cable.normalized) if cable.available else None,
                halo_total=v[Inp.TOTAL_ENERGY],
                charge_energy=v.get(Inp.OVMS_CHARGE_ENERGY),
            ):
                self.monitor.add_external(charge)
                result.external.append(charge)
                result.events.append(Event(
                    now, Category.CHARGING, Severity.INFO, "EXTERNAL_CHARGE_DETECTED",
                    f"Fremdladung erkannt: ca. {charge.energy_kwh:.1f} kWh",
                    data={"id": charge.id, "energy_kwh": charge.energy_kwh}))
                if self.settings.notify.external:
                    result.notifications.append(Notification(
                        "external", "normal", "Fremdladung erkannt",
                        f"Ca. {charge.energy_kwh:.1f} kWh außer Haus geladen (geschätzt). "
                        "Was hast du pro kWh bezahlt? Antippen öffnet die Preiseingabe, "
                        "lange drücken zeigt die Preis-Knöpfe.",
                        actions=(f"ext_price:{charge.id}",),
                        url=external_price_url(charge.id)))

        if self.soc.quality is Quality.GOOD:
            self.monitor.record_soc(now, float(self.soc.normalized))
        odometer = v[Inp.OVMS_ODOMETER]
        if odometer.quality is Quality.GOOD and self.monitor.odometer_from_ovms(self.settings):
            readings = self.monitor.data.odometer_readings
            if not readings or readings[-1].at.astimezone(self.tz).date() != local_day \
                    or float(odometer.normalized) - readings[-1].value >= 1:
                self.monitor.add_odometer(now, float(odometer.normalized))

        # Starting a charge or running the climate closes the HV contactor, too
        # (field 18.10.2026: a warning while the Halo waited for the first power).
        hvac = v.get(Inp.OVMS_HVAC)
        active = self.executor.state is ExecState.CHARGING or self.executor.starting \
            or self.climate_active or bool(v[Inp.OVMS_VEHICLE_ON].normalized) \
            or bool(hvac is not None and hvac.available and hvac.normalized) \
            or self.external.live is not None \
            or bool(v[Inp.OVMS_CHARGING].available and v[Inp.OVMS_CHARGING].normalized)
        for code in self.hv.update(v[Inp.OVMS_HV_CYCLES], local_day, active):
            message = ("HV-Kontaktor geschaltet, ohne dass das Auto lud oder fuhr"
                       if code == "HV_CYCLE_WITHOUT_ACTIVITY"
                       else f"Mehr als {self.hv.warn_per_day} HV-Zyklen heute")
            result.events.append(Event(now, Category.HEALTH, Severity.WARNING, code, message))

    # ------------------------------------------------------- notifications

    def _notifications(self, now: datetime, result: TickResult, plugged_in: bool,
                       cable: bool | None) -> None:
        n = self.settings.notify
        out = result.notifications
        for event in result.events:
            if event.code in ("CHARGE_START_FAILED", "CHARGER_NOT_CONFIRMED") \
                    and event.severity is Severity.ERROR and n.start_failed:
                out.append(Notification("start_failed", "high", "Ladestart fehlgeschlagen",
                                        f"{event.message}. {FAILURE_HINTS[event.code]}",
                                        actions=("retry",)))
            elif event.code == "CHARGE_INTERRUPTED" and event.severity is Severity.ERROR \
                    and n.start_failed:
                out.append(Notification("start_failed", "high", "Ladung abgebrochen",
                                        f"{event.message}. {FAILURE_HINTS[event.code]}",
                                        actions=("retry",)))
            elif event.code == "CP_NOT_RESTORED" and n.cp:
                out.append(Notification("cp", "critical", "CP nicht zurückgestellt",
                                        "Shelly-Relais nach dem Puls nicht geschlossen – prüfen!"))
            elif event.code == "CLIMATE_SKIPPED" and n.start_failed:
                out.append(Notification("start_failed", "high", "Vorklimatisierung ausgefallen",
                                        f"{event.message}. Das Auto wurde nicht geweckt; "
                                        "bitte Wallbox prüfen."))
            elif event.code == "PAUSE_HOLD" and n.start_failed:
                self._pause_pushed = True
                out.append(Notification("start_failed", "high", "Ladepause",
                                        f"Ladung pausiert bei {self._soc_text()} – das Auto "
                                        "nimmt keinen Strom. Die Wallbox bleibt frei, bis du "
                                        "das Kabel ziehst."))
            elif event.code == "PAUSE_RESUMED" and self._pause_pushed and n.start_failed:
                self._pause_pushed = False
                out.append(Notification("start_failed", "normal", "Lädt wieder",
                                        f"Die Ladepause ist vorbei ({self._soc_text()})."))
            elif event.code.startswith("HV_CYCLE") and n.hv_cycles:
                out.append(Notification("hv_cycles", "normal", "HV-Kontaktor auffällig",
                                        event.message))

        # CP state unknown/open: immediate and critical, not debounced (§8.3).
        cp_alarm = any(r in CP_REASONS for r in self.health.reasons)
        if cp_alarm and not self._cp_alarm and n.cp and \
                "CP_NOT_RESTORED" not in self.health.reasons:
            cp_reasons = [r for r in self.health.reasons if r in CP_REASONS]
            out.append(Notification("cp", "critical", "CP-Leitung prüfen",
                                    f"{reasons_text(cp_reasons)} – die Automatik schaltet aus "
                                    "Sicherheitsgründen nichts."))
        self._cp_alarm = cp_alarm
        self._health_push(now, result)

        if plugged_in and self.active_window is None and n.plug_in_action:
            self.plug_offer_at = now
            out.append(Notification("plug_in_action", "normal", "Eingesteckt",
                                    "Wie soll geladen werden?", actionable=True))
            result.events.append(Event(now, Category.USER, Severity.INFO, "PLUGGED_IN",
                                       "Eingesteckt – Auswahl per Push angeboten"))

        local = now.astimezone(self.tz)
        reminder = self.settings.plug_reminder_time
        if local.time() >= reminder and self._reminder_day != local.date():
            self._reminder_day = local.date()
            upcoming = self.next_window
            if upcoming and upcoming.start - now <= REMINDER_HORIZON:
                if cable is False and n.plug_reminder:
                    out.append(Notification("plug_reminder", "normal", "Nicht eingesteckt",
                                            f"Plan „{upcoming.name}“ ist aktiv, aber das "
                                            "Kabel steckt nicht."))
                elif upcoming.estimate.minimum_reachable is False and n.plan_infeasible:
                    out.append(Notification(
                        "plan_infeasible", "normal", "Mindest-SOC nicht erreichbar",
                        f"Erwartet {upcoming.estimate.expected_soc_at_departure:.0f} % bei "
                        f"Abfahrt, Minimum {upcoming.minimum_soc_pct} %."))

    def _health_push(self, now: datetime, result: TickResult) -> None:
        """Health changes are pushed after five stable minutes (§8.3)."""
        status = self.health.status
        if status == self._health_notified:
            self._health_candidate = None
            return
        if self._health_candidate is None or self._health_candidate[0] != status:
            self._health_candidate = (status, now)
            return
        if (now - self._health_candidate[1]).total_seconds() < HEALTH_PUSH_DEBOUNCE_S:
            return
        self._health_notified = status
        self._health_candidate = None
        reasons = reasons_text(self.health.reasons)
        label = STATUS_TEXT.get(str(status), str(status))
        result.events.append(Event(
            now, Category.HEALTH,
            Severity.INFO if status is HealthStatus.HEALTHY else Severity.WARNING,
            f"HEALTH_{status}", f"Systemzustand: {label} ({reasons})"))
        if status is not HealthStatus.HEALTHY and self.settings.notify.health:
            result.notifications.append(Notification(
                "health", "high" if status is HealthStatus.ERROR else "normal",
                f"Systemzustand: {label}", reasons))

    # ======================================================== user actions

    def _user_event(self, now: datetime, code: str, message: str, **data: Any) -> TickResult:
        return TickResult(events=[Event(now, Category.USER, Severity.INFO, code, message,
                                        data=data)])

    def set_override(self, now: datetime, mode: OverrideMode, *,
                     expires_at: datetime | None = None, target_soc: int | None = None,
                     source: Reason = Reason.OVERRIDE) -> TickResult:
        """Manual override (§5.3); never bypasses health locks or the cooldown."""
        if mode is OverrideMode.DURATION and expires_at is None:
            raise ValueError("Für „Für eine Dauer“ bitte duration_min oder until angeben")
        if mode is OverrideMode.UNTIL_TIME and expires_at is None:
            raise ValueError("Für „Bis Uhrzeit“ bitte until angeben")
        if mode is OverrideMode.UNTIL_SOC and target_soc is None:
            raise ValueError("Für „Bis Ladestand“ bitte target_soc angeben")
        self.override = ManualOverride(mode, now, expires_at, target_soc, source)
        return self._user_event(now, "OVERRIDE_SET", f"Manuell: {OVERRIDE_TEXT.get(mode, mode)}",
                                mode=str(mode),
                                source=str(source))

    def charge_now(self, now: datetime) -> TickResult:
        """"Jetzt laden": up to the manual target SOC, or until unplugged without one."""
        target = self.settings.manual_target_soc
        if target < 100 and self.config.ovms_configured:
            return self.set_override(now, OverrideMode.UNTIL_SOC, target_soc=target)
        return self.set_override(now, OverrideMode.UNTIL_UNPLUGGED)

    def start_charge_test(self, now: datetime) -> TickResult:
        """Function test: Halo on, wakeup cascade if needed, short stable charge, Halo off."""
        if self.shadow:
            raise ValueError("Der Ladetest schaltet wirklich – bitte zuerst den Live-Modus "
                             "einschalten")
        if self._cable is not True:
            raise ValueError("Das Auto ist nicht eingesteckt")
        if self.health.blocks_automation or self.executor.cp_not_restored:
            raise ValueError("Das System ist im Fehlerzustand – bitte zuerst den Fehler beheben")
        if self.charge_test is not None and self.charge_test.running:
            raise ValueError("Es läuft bereits ein Ladetest")
        if self.executor.state in (ExecState.CHARGING, ExecState.CHARGE_STABILIZING,
                                   ExecState.WAITING_FOR_CHARGE, ExecState.WAKEUP_OVMS,
                                   ExecState.WAKEUP_CP):
            raise ValueError("Es wird gerade geladen oder ein Ladestart läuft")
        if self.executor.state is ExecState.START_FAILED:
            # The test is a deliberate new attempt after a failed start.
            self.executor.reset(now)
        self.charge_test = ChargeTest.start(now)
        self.override = self._test_override = ManualOverride(
            OverrideMode.DURATION, now, self.charge_test.deadline)
        return self._user_event(now, "CHARGE_TEST_START", "Ladetest gestartet")

    def _charge_test(self, now: datetime, result: TickResult) -> None:
        test = self.charge_test
        if test is None or not test.running:
            return
        if test.phase == "running":
            power = self.values[Inp.CHARGE_POWER]
            watts = float(power.normalized) if power.available \
                and power.normalized is not None else None
            test.observe(now, result.events, watts)
            if test.phase == "running":
                due = test.due(now)
                if due is not None:
                    test.stop(now, *due)
                elif self.override is not self._test_override:
                    test.stop(now, False, "Abgebrochen – Kabel gezogen oder Laden manuell "
                                          "geändert")
            if test.phase == "stopping" and self.override is self._test_override:
                self.override = None
            return
        charger = self.values[Inp.CHARGER_ENABLE]
        kept_on = self.desired is not None and self.desired.charger_enabled is True \
            and self.desired.reason is not Reason.OVERRIDE
        if test.stopped(now, bool(charger.normalized) if charger.available else None, kept_on):
            self._test_override = None
            verdict = "erfolgreich" if test.ok else "fehlgeschlagen"
            result.events.append(Event(
                now, Category.CHARGING, Severity.INFO if test.ok else Severity.WARNING,
                "CHARGE_TEST_RESULT", f"Ladetest {verdict}: {test.summary}",
                data={"ok": test.ok, "woke_by": test.woke_by, "power_w": test.power_w}))

    def clear_override(self, now: datetime) -> TickResult:
        self.override = None
        return self._user_event(now, "OVERRIDE_CLEARED", "Override aufgehoben")

    def start_one_shot(self, now: datetime, departure_time: time | None = None, *,
                       departure_at: datetime | None = None,
                       target_soc: int | None = None,
                       current_a: int | None = None) -> TickResult:
        plan = self.plans[0] if self.plans else DEFAULT_PLAN
        self.one_shot = OneShot.for_next(plan, now, self.tz, departure_time,
                                         departure_at=departure_at, target_soc=target_soc,
                                         current_a=current_a)
        local = self.one_shot.departure_at.astimezone(self.tz)
        day = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")[local.weekday()]
        what = "Einmalige Abfahrt" if departure_at else "Heute Nacht laden"
        return self._user_event(
            now, "ONE_SHOT_SET", f"{what}: Abfahrt {day} {local:%d.%m. %H:%M}, Ziel "
            f"{self.one_shot.preferred_departure_soc_pct} %")

    def cancel_one_shot(self, now: datetime) -> TickResult:
        self.one_shot = None
        return self._user_event(now, "ONE_SHOT_CANCELLED", "Einmalige Abfahrt gelöscht")

    def start_climate(self, now: datetime, minutes: int) -> TickResult:
        self.manual_climate = ClimateRequest(minutes, now, now + timedelta(minutes=minutes))
        return self._user_event(now, "CLIMATE_REQUESTED", f"Klimatisierung {minutes} min")

    def stop_climate(self, now: datetime) -> TickResult:
        self.manual_climate = None
        if self._climate_lock is not None:
            self.climate_phase = "done"
        result = TickResult()
        result.extend(self.executor.request_climate_stop(now))
        return result

    def wakeup(self, now: datetime, kind: CommandKind) -> TickResult:
        result = TickResult()
        result.extend(self.executor.request_wakeup(kind, now))
        return result

    def plug_offer_valid(self, now: datetime) -> bool:
        """May a button of the plug-in push still act? Only for that plug-in."""
        offer = self.plug_offer_at
        return offer is not None and now - offer <= PLUG_OFFER_VALID \
            and self._cable is True \
            and (self.last_unplug_at is None or self.last_unplug_at <= offer)

    def retry(self, now: datetime) -> TickResult:
        """"Erneut versuchen" after a failed start: forget the failure, try once more."""
        if self._cable is not True:
            return self._user_event(now, "RETRY_IGNORED",
                                    "Erneut versuchen ignoriert – kein Kabel gesteckt")
        self.executor.reset(now)
        return self._user_event(now, "RETRY", "Neuer Ladeversuch angefordert")

    def reset(self, now: datetime) -> TickResult:
        self.executor.reset(now)
        return self._user_event(now, "RESET", "Fehlerzustand zurückgesetzt")

    def set_automation(self, now: datetime, enabled: bool) -> TickResult:
        self.automation_enabled = enabled
        return self._user_event(now, "AUTOMATION_ON" if enabled else "AUTOMATION_OFF",
                                "Automatik an" if enabled else "Automatik aus")

    def set_plans(self, now: datetime, plans: list[WeeklySchedule]) -> TickResult:
        ids = [p.id for p in plans]
        if len(ids) != len(set(ids)):
            raise ValueError("Plan-IDs müssen eindeutig sein")
        self.plans = list(plans)
        return self._user_event(now, "PLANS_CHANGED", f"{len(plans)} Ladepläne gespeichert")

    def update_primary_plan(self, now: datetime, **changes: Any) -> TickResult:
        base = self.plans[0] if self.plans else DEFAULT_PLAN
        data = {**base.as_dict(), **changes}
        self.plans = [WeeklySchedule.from_dict(data), *self.plans[1:]]
        return self._user_event(now, "PLANS_CHANGED", f"Plan „{base.name}“ geändert",
                                changes={k: str(v) for k, v in changes.items()})

    # ============================================================= storage

    def as_dict(self) -> dict[str, Any]:
        return {
            "plans": [p.as_dict() for p in self.plans],
            "override": self.override.as_dict() if self.override else None,
            "one_shot": self.one_shot.as_dict() if self.one_shot else None,
            "automation_enabled": self.automation_enabled,
            "executor": self.executor.as_dict(),
            "sessions": self.sessions.as_dict(),
            "trips": self.trips.as_dict(),
            "hv": self.hv.as_dict(),
            "latched": {k: {"start": w.start.isoformat(),
                            "blocks": [[a.isoformat(), b.isoformat()] for a, b in w.blocks]}
                        for k, w in self._latched.items()},
            "external": self.external.as_dict(),
            "prices": [p.as_dict() for p in self.price_schedule.slots],
            "last_activity_at": self.last_activity_at.isoformat()
            if self.last_activity_at else None,
            "last_result": self.last_result,
            "reminder_day": self._reminder_day.isoformat() if self._reminder_day else None,
            "target_hold": self._target_hold,
            "plug_offer_at": self.plug_offer_at.isoformat() if self.plug_offer_at else None,
            "last_unplug_at": self.last_unplug_at.isoformat() if self.last_unplug_at else None,
            "changed": {k.value: [state, at.isoformat()]
                        for k, (state, at) in self._changed.items()},
            "climate_lock": {"duration_min": self._climate_lock.duration_min,
                             "start_at": self._climate_lock.start_at.isoformat(),
                             "until": self._climate_lock.until.isoformat(),
                             "phase": self.climate_phase,
                             "restarts": self._climate_restarts} if self._climate_lock else None,
        }

    def restore(self, data: dict[str, Any]) -> None:
        if data.get("plans") is not None:  # an empty list means "all plans deleted"
            self.plans = [WeeklySchedule.from_dict(p) for p in data["plans"]]
        self.override = ManualOverride.from_dict(data["override"]) if data.get("override") \
            else None
        self.one_shot = OneShot.from_dict(data["one_shot"]) if data.get("one_shot") else None
        self.automation_enabled = bool(data.get("automation_enabled", True))
        self.executor.restore(data.get("executor") or {})
        self.sessions.restore(data.get("sessions") or {})
        self.trips.restore(data.get("trips") or {})
        self.hv = HvCycleMonitor.from_dict(data.get("hv") or {},
                                           self.settings.hv_cycles_warn_per_day)
        self._latched_raw = data.get("latched") or {}
        self.external.restore(data.get("external") or {})
        self.price_schedule = PriceSchedule(
            PriceSlot(datetime.fromisoformat(p["start"]), datetime.fromisoformat(p["end"]),
                      float(p["eur_per_kwh"])) for p in data.get("prices") or [])
        last = data.get("last_activity_at")
        self.last_activity_at = datetime.fromisoformat(last) if last else None
        self.last_result = data.get("last_result")
        day = data.get("reminder_day")
        self._reminder_day = date.fromisoformat(day) if day else None
        self._target_hold = data.get("target_hold")
        offer, unplug = data.get("plug_offer_at"), data.get("last_unplug_at")
        self.plug_offer_at = datetime.fromisoformat(offer) if offer else None
        self.last_unplug_at = datetime.fromisoformat(unplug) if unplug else None
        known = {i.value for i in Inp}
        self._changed = {Inp(k): (v[0], datetime.fromisoformat(v[1]))
                         for k, v in (data.get("changed") or {}).items() if k in known}
        lock = data.get("climate_lock")
        if lock:
            self._climate_lock = ClimateRequest(
                int(lock["duration_min"]), datetime.fromisoformat(lock["start_at"]),
                datetime.fromisoformat(lock["until"]))
            self.climate_phase = lock.get("phase")
            self._climate_restarts = int(lock.get("restarts", 0))
