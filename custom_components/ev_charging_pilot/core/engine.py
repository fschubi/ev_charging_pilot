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
from .climate import climate_blocker, climate_request, climate_wish, planned_duration
from .costs import FixedPriceHistory
from .executor import ExecState, Executor, ExecutorConfig, Snapshot, StepResult
from .external import ExternalChargeDetector
from .health import Health, HealthInputs, HealthStatus, evaluate
from .inputs import Inp, RawState, to_value
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
from .settings import ClimateAfterTarget, OdometerSource, PriceSource, Settings
from .source_policy import HvCycleMonitor, mark_conflict, outside_temperature, vehicle_charging
from .statistics import ExternalCharge
from .trips import Trip, TripTracker

HEALTH_PUSH_DEBOUNCE_S = 300
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
REMINDER_HORIZON = timedelta(hours=12)
# The buttons of the plug-in push only apply to that plug-in, and not forever.
PLUG_OFFER_VALID = timedelta(hours=12)
CP_REASONS = ("CP_NOT_RESTORED", "CP_STATE_UNKNOWN", "CP_OPEN")
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
        self.data_conflict = False
        self.last_activity_at: datetime | None = None
        self.last_result: dict[str, Any] | None = None

        self._latched: dict[str, ChargeWindow] = {}
        self._latched_raw: dict[str, Any] = {}
        self._cable: bool | None = None
        self._reminder_day: date | None = None
        self._health_candidate: tuple[HealthStatus, datetime] | None = None
        self._health_notified = HealthStatus.HEALTHY
        self._cp_alarm = False
        self._was_conflict = False
        self._conflict_since: datetime | None = None
        self._target_hold: str | None = None
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

        self._expire(now, cable_flag)
        self._plan(now)

        self.health = evaluate(self._health_inputs(now))
        self._climate(now)
        self.desired = self._arbitrate(now, cable_flag is True)

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
        )))
        if self.shadow:
            for command in result.commands:
                if command.kind is CommandKind.ENABLE_CHARGER:
                    self._virtual_charger = True
                elif command.kind is CommandKind.DISABLE_CHARGER:
                    self._virtual_charger = False
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

        power = values[Inp.CHARGE_POWER]
        if power.available and power.normalized is not None \
                and float(power.normalized) > s.power_threshold_w:
            self.last_activity_at = now
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
        ):
            values[key] = classify(values[key], now, r, self.last_activity_at)
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
        if charging_conflict(values[Inp.CHARGE_POWER], values[Inp.OVMS_CHARGING],
                             s.power_threshold_w):
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

        self.values = values
        self.soc = values[Inp.OVMS_SOC]
        self.outside = outside_temperature(
            values[Inp.OVMS_OUTSIDE_TEMP], values[Inp.OUTSIDE_TEMP], values[Inp.WEATHER])
        self._vehicle_charging = vehicle_charging(
            values[Inp.OVMS_CHARGING], values[Inp.CHARGE_POWER], s.power_threshold_w)

    def _vehicle_finished(self, now: datetime) -> bool:
        """The car ended the charge itself (§6.3 step 1).

        A car that falls asleep right after a full charge stops reporting, so a
        recent "not charging" also counts once it is no longer GOOD, and so does
        a full battery.
        """
        charging = self.values[Inp.OVMS_CHARGING]
        if charging.normalized is False and charging.quality in (
                Quality.GOOD, Quality.LAST_KNOWN_VALID) and charging.updated_at is not None \
                and now - charging.updated_at <= FINISHED_SIGNAL_MAX_AGE:
            return True
        soc = self.soc
        return soc.quality.usable_for_planning and soc.normalized is not None \
            and float(soc.normalized) >= FULL_SOC_PCT

    # ------------------------------------------------------------ planning

    def _params(self) -> VehicleParams:
        s = self.settings
        return VehicleParams(
            usable_capacity_kwh=s.usable_capacity_kwh,
            charge_efficiency=s.charge_efficiency,
            halo_limit_kw=s.max_power_kw,
            vehicle_charger_kw=s.vehicle_charger_kw,
            grid_limit_kw=s.grid_limit_kw,
        )

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
        if window.start <= now:
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
        self.windows = [w for w in windows if w is not None]
        self.active_window = next((w for w in self.windows if w.contains(now)), None)
        upcoming = sorted(self.windows, key=lambda w: w.start)
        self.next_window = self.active_window or (upcoming[0] if upcoming else None)
        keep = {w.key for w in self.windows}
        self._latched = {k: v for k, v in self._latched.items() if k in keep}
        if self._target_hold not in keep:
            self._target_hold = None
        self.executor.prune_expired(now)

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
        degraded = self.health.status is not HealthStatus.HEALTHY
        self.climate_blocked = climate_blocker(self.soc, self.settings, degraded) \
            if self.climate_plan else None

    def _arbitrate(self, now: datetime, plugged_in: bool) -> Desired:
        s = self.settings
        climate_req = self.climate_plan if self.climate_blocked is None else None
        climate_running = climate_req is not None and climate_req.start_at <= now < \
            climate_req.until
        wishes: list[Desired | None] = [override_wish(self.override)]
        if self.manual_climate is not None and climate_req is not None:
            wishes.append(climate_wish(climate_req, now, plugged_in, "manual"))
        if self.automation_enabled:
            one_shot = next((w for w in self.windows if w.reason is Reason.ONE_SHOT), None)
            wishes.append(window_wish(one_shot, now))
            window = self.active_window
            target = window.preferred_soc_pct if window else None
            soc = None if self.health.blocks_soc_functions else self.soc
            topup = climate_running and s.climate_after_target is ClimateAfterTarget.ALLOW_TOPUP
            if climate_running and s.climate_after_target is ClimateAfterTarget.ENFORCE_TARGET \
                    and target is not None:
                target += ENFORCE_TARGET_MARGIN_PCT
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
            if self.manual_climate is None:
                wishes.append(climate_wish(climate_req, now, plugged_in, "plan"))
            wishes += [window_wish(w, now) for w in self.windows if w.reason is Reason.SCHEDULE]
        desired = arbitrate(
            wishes,
            safety_lock=self.health.blocks_automation,
            default=DEFAULT_OFF if self.automation_enabled else HANDS_OFF,
        )
        if self.active_window is not None and self._target_hold == self.active_window.key \
                and desired.charger_enabled and desired.reason in (
                    Reason.SCHEDULE, Reason.ONE_SHOT, Reason.CLIMATE):
            # Topping up after the target: the car is awake anyway or it is not worth a wakeup.
            desired = replace(desired, wake_allowed=False)
        return desired

    # -------------------------------------------------------------- health

    def _health_inputs(self, now: datetime) -> HealthInputs:
        v = self.values
        cfg = self.config
        relay = v[Inp.CP_RELAY]
        schedule = v[Inp.INTERNAL_SCHEDULE]
        needs_temperature = self.settings.climate_enabled and any(
            w.climate == "auto" for w in self.windows)
        return HealthInputs(
            halo_available=v[Inp.CHARGER_ENABLE].available,
            in_charge_window=self.active_window is not None,
            cp_configured=cfg.cp_configured,
            shelly_available=relay.available if cfg.cp_configured else None,
            cp_relay_on=bool(relay.normalized) if relay.available else None,
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
                        f"Ca. {charge.energy_kwh:.1f} kWh außer Haus geladen "
                        "(geschätzt). Kosten bitte im Panel ergänzen."))

        if self.soc.quality is Quality.GOOD:
            self.monitor.record_soc(now, float(self.soc.normalized))
        odometer = v[Inp.OVMS_ODOMETER]
        if odometer.quality is Quality.GOOD and \
                self.settings.odometer_source is OdometerSource.OVMS:
            readings = self.monitor.data.odometer_readings
            if not readings or readings[-1].at.astimezone(self.tz).date() != local_day \
                    or float(odometer.normalized) - readings[-1].value >= 1:
                self.monitor.add_odometer(now, float(odometer.normalized))

        active = self.executor.state is ExecState.CHARGING or bool(
            v[Inp.OVMS_VEHICLE_ON].normalized)
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
            elif event.code.startswith("HV_CYCLE") and n.hv_cycles:
                out.append(Notification("hv_cycles", "normal", "HV-Kontaktor auffällig",
                                        event.message))

        # CP state unknown/open: immediate and critical, not debounced (§8.3).
        cp_alarm = any(r in CP_REASONS for r in self.health.reasons)
        if cp_alarm and not self._cp_alarm and n.cp and \
                "CP_NOT_RESTORED" not in self.health.reasons:
            out.append(Notification("cp", "critical", "CP-Zustand unbekannt",
                                    f"CP-Zustand: {', '.join(self.health.reasons)}"))
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
        reasons = ", ".join(self.health.reasons) or "ok"
        result.events.append(Event(
            now, Category.HEALTH,
            Severity.INFO if status is HealthStatus.HEALTHY else Severity.WARNING,
            f"HEALTH_{status}", f"System-Health: {status} ({reasons})"))
        if status is not HealthStatus.HEALTHY and self.settings.notify.health:
            result.notifications.append(Notification(
                "health", "high" if status is HealthStatus.ERROR else "normal",
                f"System-Health {status}", reasons))

    # ======================================================== user actions

    def _user_event(self, now: datetime, code: str, message: str, **data: Any) -> TickResult:
        return TickResult(events=[Event(now, Category.USER, Severity.INFO, code, message,
                                        data=data)])

    def set_override(self, now: datetime, mode: OverrideMode, *,
                     expires_at: datetime | None = None, target_soc: int | None = None,
                     source: Reason = Reason.OVERRIDE) -> TickResult:
        """Manual override (§5.3); never bypasses health locks or the cooldown."""
        if mode is OverrideMode.DURATION and expires_at is None:
            raise ValueError("duration override needs expires_at")
        if mode is OverrideMode.UNTIL_TIME and expires_at is None:
            raise ValueError("until_time override needs expires_at")
        if mode is OverrideMode.UNTIL_SOC and target_soc is None:
            raise ValueError("until_soc override needs target_soc")
        self.override = ManualOverride(mode, now, expires_at, target_soc, source)
        return self._user_event(now, "OVERRIDE_SET", f"Override {mode}", mode=str(mode),
                                source=str(source))

    def charge_now(self, now: datetime) -> TickResult:
        """"Jetzt laden": up to the manual target SOC, or until unplugged without one."""
        target = self.settings.manual_target_soc
        if target < 100 and self.config.ovms_configured:
            return self.set_override(now, OverrideMode.UNTIL_SOC, target_soc=target)
        return self.set_override(now, OverrideMode.UNTIL_UNPLUGGED)

    def clear_override(self, now: datetime) -> TickResult:
        self.override = None
        return self._user_event(now, "OVERRIDE_CLEARED", "Override aufgehoben")

    def start_one_shot(self, now: datetime, departure_time: time | None = None) -> TickResult:
        plan = self.plans[0] if self.plans else DEFAULT_PLAN
        self.one_shot = OneShot.for_next(plan, now, self.tz, departure_time)
        local = self.one_shot.departure_at.astimezone(self.tz)
        day = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")[local.weekday()]
        return self._user_event(now, "ONE_SHOT_SET",
                                f"Heute Nacht laden, Abfahrt {day} {local:%H:%M}")

    def cancel_one_shot(self, now: datetime) -> TickResult:
        self.one_shot = None
        return self._user_event(now, "ONE_SHOT_CANCELLED", "One-Shot gelöscht")

    def start_climate(self, now: datetime, minutes: int) -> TickResult:
        self.manual_climate = ClimateRequest(minutes, now, now + timedelta(minutes=minutes))
        return self._user_event(now, "CLIMATE_REQUESTED", f"Klimatisierung {minutes} min")

    def stop_climate(self, now: datetime) -> TickResult:
        self.manual_climate = None
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
            raise ValueError("plan ids must be unique")
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
