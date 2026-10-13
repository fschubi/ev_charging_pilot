"""Glue between Home Assistant and the HA-free core.

Every tick reads the configured entities into quality-tagged values, lets the
planners and the arbiter compute the desired state, evaluates health, runs
one executor step and dispatches the resulting commands through the ports.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.core import Event as HaEvent
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    BUS_EVENT,
    CONF_CABLE_CONNECTED,
    CONF_CAPACITY_KWH,
    CONF_CHARGE_POWER,
    CONF_CHARGE_START_TIME,
    CONF_CHARGER_ENABLE,
    CONF_CHARGER_STATUS,
    CONF_CP_FAILSAFE_VERIFIED,
    CONF_CP_PULSE_S,
    CONF_CP_RELAY,
    CONF_DEPARTURE_TIME,
    CONF_EFFICIENCY,
    CONF_FINISHED_STATUSES,
    CONF_GRID_LIMIT_KW,
    CONF_INTERNAL_SCHEDULE,
    CONF_MIN_SOC,
    CONF_MIN_SWITCH_INTERVAL_S,
    CONF_MODE,
    CONF_NOTIFY_SERVICE,
    CONF_OVMS_CHARGING,
    CONF_OVMS_SOC,
    CONF_PLAN_ENABLED,
    CONF_POWER_THRESHOLD_W,
    CONF_PREFERRED_SOC,
    CONF_READY_BUFFER_MIN,
    CONF_SHELLY_HOST,
    CONF_START_DETECTION_WAIT_S,
    CONF_VEHICLE_CHARGER_KW,
    CONF_WEEKDAYS,
    DEFAULTS,
    EVENT_RETENTION_DAYS,
    HEALTH_PUSH_DEBOUNCE_S,
    PUSH_EVENTS,
    STORAGE_KEY_EVENTS,
    STORAGE_KEY_STATE,
    STORAGE_VERSION,
    TICK_SECONDS,
)
from .core.arbiter import arbitrate
from .core.executor import Executor, ExecutorConfig, Snapshot
from .core.health import Health, HealthInputs, HealthStatus, evaluate
from .core.model import Category, Desired, Event, Quality, Reason, Severity, Value
from .core.planner import (
    ChargeWindow,
    ManualOverride,
    OneShot,
    OverrideMode,
    ScheduleMode,
    VehicleParams,
    WeeklySchedule,
    one_shot_window,
    override_wish,
    schedule_window,
    target_soc_wish,
    window_wish,
)
from .core.ports import CommandRecorder
from .core.quality import QualityRule, charging_conflict, classify, soc_plausible
from .ha_ports import HaPorts, shelly_config_ok

_LOGGER = logging.getLogger(__name__)

SOC_RULE = QualityRule(max_age_s=600, plausible=soc_plausible)
VEHICLE_CHARGING_RULE = QualityRule(max_age_s=300)
DRIFT_CHECK_INTERVAL = timedelta(minutes=15)
_MISSING = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def _parse_time(raw: str) -> time:
    return time.fromisoformat(raw)


class ChargingCenter:
    """One instance per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.conf: dict[str, Any] = dict(entry.data)
        self.opts: dict[str, Any] = {**DEFAULTS, **entry.options}
        self.tz = ZoneInfo(hass.config.time_zone)
        self.executor = Executor(self._executor_config())
        self.recorder = CommandRecorder()
        self.events: deque[dict[str, Any]] = deque(maxlen=5000)
        self.dry_run = True
        self.override: ManualOverride | None = None
        self.one_shot: OneShot | None = None
        self.desired: Desired | None = None
        self.health: Health = Health(HealthStatus.HEALTHY)
        self.window: ChargeWindow | None = None
        self.one_shot_window: ChargeWindow | None = None
        self.soc: Value | None = None
        self.data_conflict = False
        self.shelly_config_ok: bool | None = None
        self.last_activity_at: datetime | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._lock = asyncio.Lock()
        suffix = entry.entry_id
        self._state_store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_STATE}.{suffix}")
        self._event_store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_EVENTS}.{suffix}")
        self._health_candidate: tuple[HealthStatus, datetime] | None = None
        self._health_notified = HealthStatus.HEALTHY
        self.ports = HaPorts(
            hass,
            charger_switch=self.conf[CONF_CHARGER_ENABLE],
            cp_relay=self.conf.get(CONF_CP_RELAY),
            shelly_host=self.conf.get(CONF_SHELLY_HOST),
            dry_run=lambda: self.dry_run,
        )

    # ------------------------------------------------------------ lifecycle

    def _executor_config(self) -> ExecutorConfig:
        o = self.opts
        statuses = tuple(s.strip() for s in str(o[CONF_FINISHED_STATUSES]).split(",") if s.strip())
        return ExecutorConfig(
            power_threshold_w=float(o[CONF_POWER_THRESHOLD_W]),
            min_switch_interval_s=float(o[CONF_MIN_SWITCH_INTERVAL_S]),
            start_detection_wait_s=float(o[CONF_START_DETECTION_WAIT_S]),
            cp_pulse_s=int(o[CONF_CP_PULSE_S]),
            cp_available=bool(self.conf.get(CONF_CP_RELAY) and self.conf.get(CONF_SHELLY_HOST)),
            cp_failsafe_verified=bool(o[CONF_CP_FAILSAFE_VERIFIED]),
            # OVMS wakeup stays off until the command is tested on the car (§1.2).
            ovms_available=False,
            finished_statuses=statuses,
        )

    async def async_setup(self) -> None:
        stored = await self._state_store.async_load() or {}
        self.executor.restore(stored.get("executor") or {})
        self.dry_run = bool(stored.get("dry_run", True))
        self.override = self._load_override(stored.get("override"))
        self.one_shot = self._load_one_shot(stored.get("one_shot"))
        for item in await self._event_store.async_load() or []:
            self.events.append(item)

        watched = [
            self.conf.get(key)
            for key in (CONF_CHARGER_ENABLE, CONF_CABLE_CONNECTED, CONF_CHARGE_POWER,
                        CONF_CHARGER_STATUS, CONF_CP_RELAY, CONF_OVMS_SOC, CONF_OVMS_CHARGING)
        ]
        self._unsubs.append(async_track_state_change_event(
            self.hass, [e for e in watched if e], self._on_state_change))
        self._unsubs.append(async_track_time_interval(
            self.hass, self._on_interval, timedelta(seconds=TICK_SECONDS)))
        self._unsubs.append(async_track_time_interval(
            self.hass, self._on_drift_check, DRIFT_CHECK_INTERVAL))
        self.hass.async_create_task(self._drift_check())
        await self.async_tick()

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._save()

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def _on_state_change(self, event: HaEvent) -> None:
        if event.data.get("entity_id") == self.conf.get(CONF_CABLE_CONNECTED):
            self.last_activity_at = dt_util.utcnow()
        self.hass.async_create_task(self.async_tick())

    @callback
    def _on_interval(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_tick())

    @callback
    def _on_drift_check(self, _now: datetime) -> None:
        self.hass.async_create_task(self._drift_check())

    async def _drift_check(self) -> None:
        config = await self.ports.shelly_switch_config()
        self.shelly_config_ok = (
            None if config is None else shelly_config_ok(config, int(self.opts[CONF_CP_PULSE_S]))
        )

    # --------------------------------------------------------- reading state

    def _value(self, key: str, kind: type, source: str, *, reported: bool = False) -> Value:
        entity_id = self.conf.get(key)
        if not entity_id:
            return Value.unavailable(source)
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _MISSING:
            return Value.unavailable(source)
        stamp = state.last_reported if reported else state.last_updated
        if kind is bool:
            return Value(state.state, state.state == STATE_ON, source, stamp)
        if kind is float:
            try:
                number = float(state.state)
            except ValueError:
                return Value(state.state, None, source, stamp, Quality.INVALID)
            unit = state.attributes.get("unit_of_measurement")
            if unit == "kW":
                number *= 1000
            return Value(state.state, number, source, stamp, unit=unit)
        return Value(state.state, state.state, source, stamp)

    def _available(self, key: str) -> bool | None:
        entity_id = self.conf.get(key)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    def _schedule(self) -> WeeklySchedule:
        o = self.opts
        return WeeklySchedule(
            id="plan",
            enabled=bool(o[CONF_PLAN_ENABLED]),
            weekdays=frozenset(o[CONF_WEEKDAYS]),
            mode=ScheduleMode(o[CONF_MODE]),
            charge_start_time=_parse_time(o[CONF_CHARGE_START_TIME]),
            departure_time=_parse_time(o[CONF_DEPARTURE_TIME]),
            ready_buffer_min=int(o[CONF_READY_BUFFER_MIN]),
            minimum_departure_soc_pct=int(o[CONF_MIN_SOC]),
            preferred_departure_soc_pct=int(o[CONF_PREFERRED_SOC]),
        )

    def _params(self) -> VehicleParams:
        o = self.opts
        grid = float(o[CONF_GRID_LIMIT_KW])
        return VehicleParams(
            usable_capacity_kwh=float(o[CONF_CAPACITY_KWH]),
            charge_efficiency=float(o[CONF_EFFICIENCY]),
            vehicle_charger_kw=float(o[CONF_VEHICLE_CHARGER_KW]),
            grid_limit_kw=grid if grid > 0 else None,
        )

    # ------------------------------------------------------------------ tick

    async def async_tick(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            await self._tick(dt_util.utcnow())

    async def _tick(self, now: datetime) -> None:
        cable = self._value(CONF_CABLE_CONNECTED, bool, "halo")
        charger_on = self._value(CONF_CHARGER_ENABLE, bool, "halo")
        power = self._value(CONF_CHARGE_POWER, float, "halo", reported=True)
        status = self._value(CONF_CHARGER_STATUS, str, "halo")
        cp_relay = self._value(CONF_CP_RELAY, bool, "shelly")
        threshold = float(self.opts[CONF_POWER_THRESHOLD_W])
        if power.available and power.normalized is not None and power.normalized > threshold:
            self.last_activity_at = now

        self.soc = classify(self._value(CONF_OVMS_SOC, float, "ovms"), now, SOC_RULE,
                            self.last_activity_at)
        vehicle_charging = classify(self._value(CONF_OVMS_CHARGING, bool, "ovms"), now,
                                    VEHICLE_CHARGING_RULE)
        self.data_conflict = charging_conflict(power, vehicle_charging, threshold)

        cable_flag = bool(cable.normalized) if cable.available else True
        if self.override and self.override.expired(now, cable_flag, self.soc):
            self._log(Event(now, Category.USER, Severity.INFO, "OVERRIDE_ENDED",
                            f"Override {self.override.mode} beendet"))
            self.override = None
        if self.one_shot and self.one_shot.expired(now):
            self.one_shot = None

        params = self._params()
        self.window = schedule_window(self._schedule(), now, self.tz, self.soc, params)
        self.one_shot_window = (
            one_shot_window(self.one_shot, now, self.tz, self.soc, params)
            if self.one_shot else None
        )
        active = next((w for w in (self.one_shot_window, self.window) if w and w.contains(now)),
                      None)

        self.health = evaluate(HealthInputs(
            halo_available=bool(self._available(CONF_CHARGER_ENABLE)),
            in_charge_window=active is not None,
            cp_configured=self.conf.get(CONF_CP_RELAY) is not None,
            shelly_available=self._available(CONF_CP_RELAY),
            cp_relay_on=bool(cp_relay.normalized) if cp_relay.available else None,
            cp_pulse_running=self.executor.cp_masked(now),
            cp_not_restored=self.executor.cp_not_restored,
            ovms_configured=self.conf.get(CONF_OVMS_SOC) is not None,
            ovms_available=self._available(CONF_OVMS_SOC),
            soc_stale=self.soc.quality is Quality.STALE,
            halo_internal_schedule_on=(
                self._value(CONF_INTERNAL_SCHEDULE, bool, "halo").normalized
                if self.conf.get(CONF_INTERNAL_SCHEDULE) else None
            ),
            shelly_auto_on_ok=self.shelly_config_ok,
            consecutive_start_failures=self.executor.consecutive_start_failures,
        ))

        soc_for_target = None if self.health.blocks_soc_functions else self.soc
        target = active.preferred_soc_pct if active else None
        self.desired = arbitrate(
            [
                override_wish(self.override),
                window_wish(self.one_shot_window, now),
                target_soc_wish(soc_for_target, target),
                window_wish(self.window, now),
            ],
            safety_lock=self.health.blocks_automation,
        )

        previous_state = self.executor.state
        result = self.executor.step(Snapshot(
            now=now,
            desired=self.desired,
            health=self.health,
            cable_connected=cable,
            charger_on=charger_on,
            power_w=power,
            charger_status=status if status.available else None,
            cp_relay_on=cp_relay if self.conf.get(CONF_CP_RELAY) else None,
            vehicle_charging=vehicle_charging if vehicle_charging.available else None,
        ))

        for command in result.commands:
            try:
                executed = await self.ports.dispatch(command)
            except Exception as err:  # noqa: BLE001 – a port must never kill the tick
                self.recorder.record(now, command, False)
                self._log(Event(now, Category.CHARGING, Severity.ERROR, "COMMAND_FAILED",
                                f"{command.describe()} fehlgeschlagen: {err}"))
                continue
            self.recorder.record(now, command, executed)
            if not executed:
                self._log(Event(now, Category.CHARGING, Severity.INFO, "DRY_RUN",
                                f"WOULD {command.describe()}"))

        for event in result.events:
            self._log(event)
        await self._health_push(now)

        if result.events or previous_state != self.executor.state:
            self._schedule_save()
        self._notify_listeners()

    # ----------------------------------------------------- events and push

    def _log(self, event: Event) -> None:
        item = event.as_dict()
        self.events.append(item)
        self.hass.bus.async_fire(BUS_EVENT, item)
        if event.code in PUSH_EVENTS:
            self.hass.async_create_task(self._push(event.message, PUSH_EVENTS[event.code]))

    async def _health_push(self, now: datetime) -> None:
        """Push on DEGRADED/ERROR, debounced by five minutes (§8.3)."""
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
        self._log(Event(now, Category.HEALTH, Severity.WARNING if status != HealthStatus.HEALTHY
                        else Severity.INFO, f"HEALTH_{status}",
                        f"System-Health: {status} ({', '.join(self.health.reasons) or 'ok'})"))
        if status != HealthStatus.HEALTHY:
            await self._push(f"System-Health {status}: {', '.join(self.health.reasons)}",
                             "high" if status is HealthStatus.ERROR else "normal")

    async def _push(self, message: str, priority: str) -> None:
        target = self.conf.get(CONF_NOTIFY_SERVICE)
        if not target:
            return
        service = target.removeprefix("notify.")
        level = {"critical": "critical", "high": "time-sensitive"}.get(priority, "active")
        try:
            await self.hass.services.async_call(
                "notify", service,
                {"title": "Smart EQ Charging", "message": message,
                 "data": {"push": {"interruption-level": level}}},
                blocking=False,
            )
        except Exception:  # noqa: BLE001 – a broken notifier must not break charging
            _LOGGER.exception("Push über notify.%s fehlgeschlagen", service)

    # -------------------------------------------------------- user actions

    async def async_charge_now(self) -> None:
        self.override = ManualOverride(OverrideMode.UNTIL_UNPLUGGED, dt_util.utcnow())
        await self._user_action("OVERRIDE_CHARGE_NOW", "Jetzt laden (bis Kabel ab)")

    async def async_stop_charging(self) -> None:
        self.override = ManualOverride(OverrideMode.STOP, dt_util.utcnow())
        await self._user_action("OVERRIDE_STOP", "Laden stoppen (bis Kabel ab)")

    async def async_clear_override(self) -> None:
        self.override = None
        self.one_shot = None
        await self._user_action("OVERRIDE_CLEARED", "Override und One-Shot aufgehoben")

    async def async_charge_tonight(self) -> None:
        now = dt_util.utcnow()
        o = self.opts
        departure_time = _parse_time(o[CONF_DEPARTURE_TIME])
        local = now.astimezone(self.tz)
        departure = datetime.combine(local.date(), departure_time, tzinfo=self.tz)
        if departure <= local:
            departure = datetime.combine(local.date() + timedelta(days=1), departure_time,
                                         tzinfo=self.tz)
        self.one_shot = OneShot(
            departure_at=departure.astimezone(dt_util.UTC),
            mode=ScheduleMode(o[CONF_MODE]),
            charge_start_time=_parse_time(o[CONF_CHARGE_START_TIME]),
            ready_buffer_min=int(o[CONF_READY_BUFFER_MIN]),
            minimum_departure_soc_pct=int(o[CONF_MIN_SOC]),
            preferred_departure_soc_pct=int(o[CONF_PREFERRED_SOC]),
        )
        await self._user_action("ONE_SHOT_SET", f"Heute Nacht laden, Abfahrt {departure:%H:%M}")

    async def async_reset(self) -> None:
        self.executor.reset(dt_util.utcnow())
        await self._user_action("RESET", "Fehlerzustand zurückgesetzt")

    async def async_set_dry_run(self, enabled: bool) -> None:
        self.dry_run = enabled
        await self._user_action("DRY_RUN_ON" if enabled else "DRY_RUN_OFF",
                                "Dry-Run aktiv" if enabled else "Dry-Run aus – Automatik schaltet")

    async def _user_action(self, code: str, message: str) -> None:
        self._log(Event(dt_util.utcnow(), Category.USER, Severity.INFO, code, message))
        self._schedule_save()
        await self.async_tick()

    # --------------------------------------------------------------- storage

    def _schedule_save(self) -> None:
        self._state_store.async_delay_save(self._state_data, 5)
        self._event_store.async_delay_save(self._event_data, 30)

    def _state_data(self) -> dict[str, Any]:
        return {
            "executor": self.executor.as_dict(),
            "dry_run": self.dry_run,
            "override": None if self.override is None else {
                "mode": str(self.override.mode),
                "started_at": self.override.started_at.isoformat(),
                "expires_at": self.override.expires_at.isoformat()
                if self.override.expires_at else None,
                "target_soc": self.override.target_soc,
                "source": str(self.override.source),
            },
            "one_shot": None if self.one_shot is None else {
                "departure_at": self.one_shot.departure_at.isoformat(),
                "mode": str(self.one_shot.mode),
                "charge_start_time": self.one_shot.charge_start_time.isoformat(),
                "ready_buffer_min": self.one_shot.ready_buffer_min,
                "minimum_departure_soc_pct": self.one_shot.minimum_departure_soc_pct,
                "preferred_departure_soc_pct": self.one_shot.preferred_departure_soc_pct,
            },
        }

    def _event_data(self) -> list[dict[str, Any]]:
        cutoff = (dt_util.utcnow() - timedelta(days=EVENT_RETENTION_DAYS)).isoformat()
        return [e for e in self.events if e["timestamp"] >= cutoff]

    async def _save(self) -> None:
        await self._state_store.async_save(self._state_data())
        await self._event_store.async_save(self._event_data())

    @staticmethod
    def _load_override(raw: dict[str, Any] | None) -> ManualOverride | None:
        if not raw:
            return None
        return ManualOverride(
            mode=OverrideMode(raw["mode"]),
            started_at=datetime.fromisoformat(raw["started_at"]),
            expires_at=datetime.fromisoformat(raw["expires_at"]) if raw.get("expires_at") else None,
            target_soc=raw.get("target_soc"),
            source=Reason(raw.get("source", Reason.OVERRIDE)),
        )

    @staticmethod
    def _load_one_shot(raw: dict[str, Any] | None) -> OneShot | None:
        if not raw:
            return None
        return OneShot(
            departure_at=datetime.fromisoformat(raw["departure_at"]),
            mode=ScheduleMode(raw["mode"]),
            charge_start_time=time.fromisoformat(raw["charge_start_time"]),
            ready_buffer_min=int(raw["ready_buffer_min"]),
            minimum_departure_soc_pct=int(raw["minimum_departure_soc_pct"]),
            preferred_departure_soc_pct=int(raw["preferred_departure_soc_pct"]),
        )
