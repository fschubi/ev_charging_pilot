"""Glue between Home Assistant and the HA-free engine.

The coordinator reads the configured entities as :class:`RawState`, runs one
:meth:`Engine.tick`, then executes (live), logs (dry-run) or ignores
(replay) the resulting commands, writes the event log, delivers push
notifications and persists everything.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components import logbook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.core import Event as HaEvent
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_NOW,
    ACTION_PLAN,
    ACTION_TONIGHT,
    BUS_EVENT,
    CONF_NAME,
    CONF_OVMS_COMMAND_SCRIPT,
    CONF_OVMS_COMMAND_TOPIC,
    CONF_SHELLY_HOST,
    DATA_DIR,
    DOMAIN,
    LOGBOOK_CODES,
    LOGBOOK_SEVERITIES,
    NAME,
    STATISTICS_REFRESH_S,
    STORAGE_KEY_EVENTS,
    STORAGE_KEY_MONITOR,
    STORAGE_KEY_STATE,
    STORAGE_VERSION,
    TICK_SECONDS,
)
from .core.engine import Engine, EngineConfig, Notification, TickResult
from .core.inputs import Inp, RawState
from .core.model import Category, Event, Severity
from .core.monitor import Monitor
from .core.planner import OverrideMode
from .core.ports import CommandRecorder
from .core.prices import PriceSlot
from .core.replay import ReplayDataset, run_replay
from .core.settings import OPT_MODE, RunMode, Settings
from .ha_ports import HaPorts, PortError, shelly_deviations
from .notifications import Notifier
from .price_source import PriceFetcher
from .reports import async_create_report, previous_month

_LOGGER = logging.getLogger(__name__)

DRIFT_CHECK_INTERVAL = timedelta(minutes=15)
MODE_MESSAGES = {
    RunMode.DRY_RUN: "Dry-Run: Befehle werden nur protokolliert",
    RunMode.LIVE: "Live: das Charging Center schaltet die Hardware",
    RunMode.REPLAY: "Replay-Modus: keine Hardware-Aktionen",
}


class ChargingCenter:
    """One instance per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.conf: dict[str, Any] = dict(entry.data)
        self.settings = Settings.from_options(dict(entry.options))
        self.tz = ZoneInfo(hass.config.time_zone)
        self.entity_ids: dict[Inp, str] = {
            inp: self.conf[inp.value] for inp in Inp if self.conf.get(inp.value)
        }
        self.ports = HaPorts(
            hass,
            charger_switch=self.conf[Inp.CHARGER_ENABLE.value],
            cp_relay=self.conf.get(Inp.CP_RELAY.value),
            shelly_host=self.conf.get(CONF_SHELLY_HOST),
            ovms_topic=self.conf.get(CONF_OVMS_COMMAND_TOPIC),
            ovms_script=self.conf.get(CONF_OVMS_COMMAND_SCRIPT),
        )
        self.monitor = Monitor(self.tz)
        self.engine = Engine(
            EngineConfig(
                settings=self.settings,
                tz=self.tz,
                configured=frozenset(self.entity_ids),
                cp_pulse_available=self.ports.cp_pulse_available,
                ovms_command_available=self.ports.ovms_command_available,
            ),
            self.monitor,
        )
        self.notifier = Notifier(hass, self.conf)
        self.price_fetcher = PriceFetcher(hass, self.tz, self._on_prices, self._on_price_problem)
        self.recorder = CommandRecorder()
        self.events: deque[dict[str, Any]] = deque(maxlen=20000)
        self.statistics: dict[str, Any] = {}
        # One sample per minute for the cockpit chart (24 h, not persisted).
        self.history: deque[tuple[str, float | None, float | None]] = deque(maxlen=1440)
        self.last_replay: dict[str, Any] | None = None
        self.shelly_deviations: list[dict[str, Any]] | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._lock = asyncio.Lock()
        self._statistics_at: datetime | None = None
        suffix = entry.entry_id
        self._state_store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_STATE}.{suffix}")
        self._event_store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_EVENTS}.{suffix}")
        self._monitor_store: Store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_MONITOR}.{suffix}")

    # ------------------------------------------------------------ lifecycle

    @property
    def mode(self) -> RunMode:
        return self.settings.mode

    @property
    def name(self) -> str:
        return self.conf.get(CONF_NAME) or NAME

    async def async_setup(self) -> None:
        self.engine.restore(await self._state_store.async_load() or {})
        self.monitor.restore(await self._monitor_store.async_load() or {})
        for item in await self._event_store.async_load() or []:
            self.events.append(item)

        self._unsubs.append(async_track_state_change_event(
            self.hass, list(self.entity_ids.values()), self._on_state_change))
        self._unsubs.append(async_track_time_interval(
            self.hass, self._on_interval, timedelta(seconds=TICK_SECONDS)))
        self._unsubs.append(async_track_time_interval(
            self.hass, self._on_drift_check, DRIFT_CHECK_INTERVAL))
        self._unsubs.append(self.notifier.async_listen_actions(self._on_notification_action))
        self._unsubs.append(async_track_time_change(
            self.hass, self._on_report_time, hour=6, minute=0, second=0))
        self.entry.async_create_background_task(
            self.hass, self._drift_check(), f"{DOMAIN} drift check")
        self.price_fetcher.start(self.settings)
        await self.async_tick()

    async def async_shutdown(self) -> None:
        self.price_fetcher.stop()
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
    def _on_state_change(self, _event: HaEvent) -> None:
        self.hass.async_create_task(self.async_tick())

    @callback
    def _on_interval(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_tick())

    @callback
    def _on_drift_check(self, _now: datetime) -> None:
        self.hass.async_create_task(self._drift_check())

    async def _drift_check(self) -> None:
        config = await self.ports.shelly_switch_config()
        if config is None:
            self.shelly_deviations = None
            self.engine.shelly_config_ok = None
        else:
            self.shelly_deviations = shelly_deviations(config, self.settings.cp_pulse_s)
            self.engine.shelly_config_ok = not self.shelly_deviations
        self._notify_listeners()

    async def async_configure_shelly(self) -> dict[str, Any]:
        """User button: write the failsafe settings to the Shelly, then re-check."""
        try:
            result = await self.ports.configure_shelly(self.settings.cp_pulse_s)
        except (PortError, OSError, TimeoutError) as err:
            self._log(Event(dt_util.utcnow(), Category.CP, Severity.ERROR,
                            "SHELLY_CONFIG_FAILED", f"Shelly-Konfiguration fehlgeschlagen: {err}"))
            raise
        await self._drift_check()
        self._log(Event(dt_util.utcnow(), Category.CP, Severity.INFO, "SHELLY_CONFIGURED",
                        "Shelly auf Failsafe-Werte gesetzt (Einschaltzustand an, Auto-On "
                        f"nach {self.settings.cp_pulse_s} s)", data={"restart": result}))
        self._schedule_save()
        return {"ok": bool(self.engine.shelly_config_ok),
                "deviations": self.shelly_deviations or []}

    # ---------------------------------------------------------------- prices

    @callback
    def _on_prices(self, slots: list[PriceSlot]) -> None:
        self.engine.set_prices(slots)
        self._schedule_save()
        self.hass.async_create_task(self.async_tick())

    @callback
    def _on_price_problem(self, message: str) -> None:
        self._log(Event(dt_util.utcnow(), Category.CONFIG, Severity.WARNING,
                        "PRICE_SOURCE_PROBLEM", f"{message} – Rückfall auf Festpreis"))
        self._notify_listeners()

    # --------------------------------------------------------------- reports

    @callback
    def _on_report_time(self, now: datetime) -> None:
        if now.astimezone(self.tz).day == 1 and self.settings.report_auto_monthly:
            self.hass.async_create_task(self.async_monthly_report(now))

    async def async_monthly_report(self, now: datetime) -> dict[str, Any]:
        year, month = previous_month(now.astimezone(self.tz))
        report = await async_create_report(self, year, month)
        self._log(Event(dt_util.utcnow(), Category.CONFIG, Severity.INFO, "REPORT_CREATED",
                        f"Monatsbericht {month:02d}/{year} erstellt", data=report))
        if self.settings.notify.report:
            await self.notifier.async_send(Notification(
                "report", "normal", "Monatsbericht",
                f"Der Bericht für {month:02d}/{year} liegt im Panel unter Hausstrom bereit."))
        return report

    def apply_options(self, options: dict[str, Any]) -> None:
        """Mode change only – no reload needed (the switch writes the option)."""
        self.settings = Settings.from_options(options)
        self.engine.settings = self.settings

    async def async_set_mode(self, mode: RunMode) -> None:
        """Switch dry-run / live / replay without reloading the entry."""
        options = {**self.entry.options, OPT_MODE: mode.value}
        self.apply_options(options)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self._handle(TickResult(events=[Event(
            dt_util.utcnow(), Category.CONFIG, Severity.INFO, f"MODE_{mode.upper()}",
            MODE_MESSAGES[mode])]))

    # ------------------------------------------------------------------ tick

    def _raw_states(self) -> dict[Inp, RawState | None]:
        raw: dict[Inp, RawState | None] = {}
        for inp, entity_id in self.entity_ids.items():
            state = self.hass.states.get(entity_id)
            raw[inp] = None if state is None else RawState(
                state.state, state.last_updated, state.last_reported, dict(state.attributes))
        return raw

    async def async_tick(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            now = dt_util.utcnow()
            result = self.engine.tick(now, self._raw_states())
            self._sample_history(now)
            await self._handle(result)
            if self._statistics_at is None or \
                    (now - self._statistics_at).total_seconds() >= STATISTICS_REFRESH_S:
                self.refresh_statistics(now)

    def _sample_history(self, now: datetime) -> None:
        minute = now.replace(second=0, microsecond=0).isoformat()
        if self.history and self.history[-1][0] == minute:
            return
        power = self.engine.values.get(Inp.CHARGE_POWER)
        soc = self.engine.soc
        self.history.append((
            minute,
            round(float(power.normalized)) if power and power.available
            and power.normalized is not None else None,
            round(float(soc.normalized), 1) if soc.available and soc.normalized is not None
            else None,
        ))

    async def async_run(self, action: Callable[[datetime], TickResult]) -> TickResult:
        """Run a user action against the engine, then a regular tick."""
        async with self._lock:
            result = action(dt_util.utcnow())
            await self._handle(result)
        await self.async_tick()
        return result

    async def _handle(self, result: TickResult) -> None:
        now = dt_util.utcnow()
        for command in result.commands:
            if self.mode is RunMode.LIVE:
                try:
                    await self.ports.execute(command, self.settings)
                except Exception as err:  # noqa: BLE001 – a port must never kill the tick
                    self.recorder.record(now, command, False)
                    self._log(Event(now, Category.CHARGING, Severity.ERROR, "COMMAND_FAILED",
                                    f"{command.describe()} fehlgeschlagen: {err}"))
                    continue
                self.recorder.record(now, command, True)
            else:
                self.recorder.record(now, command, False)
                self._log(Event(now, Category.CHARGING, Severity.INFO, "DRY_RUN",
                                f"WOULD {command.describe()}", data={"mode": str(self.mode)}))
        for event in result.events:
            self._log(event)
        for notification in result.notifications:
            await self.notifier.async_send(notification)
        monitor = bool(result.sessions or result.trips or result.external)
        if result.events or result.commands or monitor:
            self._schedule_save(monitor=monitor)
        if monitor:
            self.refresh_statistics(now)
        self._notify_listeners()

    def _log(self, event: Event) -> None:
        item = event.as_dict()
        self.events.append(item)
        self.hass.bus.async_fire(BUS_EVENT, item)
        if item["severity"] in LOGBOOK_SEVERITIES or item["code"] in LOGBOOK_CODES:
            logbook.async_log_entry(self.hass, self.name, item["message"], domain=DOMAIN)

    # ----------------------------------------------------------- statistics

    def refresh_statistics(self, now: datetime | None = None) -> None:
        now = now or dt_util.utcnow()
        local = now.astimezone(self.tz)
        today = local.date()
        self._statistics_at = now
        year = self.monitor.year(local.year, self.settings, today)
        year.pop("months", None)
        self.statistics = {
            "month": self.monitor.month(local.year, local.month, self.settings, today),
            "year": year,
        }

    # ------------------------------------------------- notification actions

    async def _on_notification_action(self, action: str) -> None:
        if action == ACTION_NOW:
            await self.async_run(lambda now: self.engine.set_override(
                now, OverrideMode.UNTIL_UNPLUGGED))
        elif action == ACTION_TONIGHT:
            await self.async_run(self.engine.start_one_shot)
        elif action == ACTION_PLAN:
            await self._handle(TickResult(events=[Event(
                dt_util.utcnow(), Category.USER, Severity.INFO, "PLAN_CONFIRMED",
                "Normaler Plan bestätigt")]))

    # --------------------------------------------------------------- replay

    @property
    def data_dir(self) -> Path:
        return Path(self.hass.config.path(DATA_DIR))

    def _replay_path(self, file: str) -> Path:
        folder = (self.data_dir / "replay").resolve()
        path = (folder / file).resolve()
        if path.parent != folder:
            raise ValueError("Die Datei muss im Replay-Ordner liegen")
        return path

    async def async_replay(self, dataset: dict[str, Any] | None = None,
                           file: str | None = None, tick_s: float = 5.0) -> dict[str, Any]:
        """Run a recorded night through the engine (no hardware, §6.1)."""
        if dataset is None:
            if not file:
                raise ValueError("file oder dataset ist nötig")
            text = await self.hass.async_add_executor_job(self._replay_path(file).read_text)
            dataset = json.loads(text)
        parsed = ReplayDataset.from_dict(dataset)
        settings = Settings.from_options({**self.entry.options, **(parsed.options or {})})
        plans = None if parsed.plans else list(self.engine.plans)
        result = await self.hass.async_add_executor_job(
            lambda: run_replay(parsed, settings, tick_s=tick_s, plans=plans))
        self.last_replay = result.as_dict()
        await self._handle(TickResult(events=[Event(
            dt_util.utcnow(), Category.CONFIG, Severity.INFO, "REPLAY_DONE",
            f"Replay „{parsed.name}“: Übereinstimmung {result.agreement}",
            data={"agreement": result.agreement, "mismatches": len(result.mismatches)})]))
        return self.last_replay

    async def async_stop_replay(self) -> None:
        self.last_replay = None
        if self.mode is RunMode.REPLAY:
            await self.async_set_mode(RunMode.DRY_RUN)
        self._notify_listeners()

    async def async_create_dataset(self, start: datetime, end: datetime, name: str,
                                   poll_interval_s: float = 60.0) -> dict[str, Any]:
        """Build a replay dataset from the recorder history (Phase-0 nights)."""
        from homeassistant.components.recorder import get_instance, history

        entity_ids = list(self.entity_ids.values())

        def load() -> dict[str, list]:
            return history.get_significant_states(
                self.hass, start, end, entity_ids, include_start_time_state=True,
                significant_changes_only=False)

        states = await get_instance(self.hass).async_add_executor_job(load)
        by_entity = {v: k for k, v in self.entity_ids.items()}
        dataset = ReplayDataset(
            name=name, timezone=str(self.tz), start=start, end=end,
            inputs={
                by_entity[entity_id]: [
                    RawState(s.state, s.last_updated, s.last_updated, dict(s.attributes))
                    for s in items
                ]
                for entity_id, items in states.items() if entity_id in by_entity
            },
            plans=[p.as_dict() for p in self.engine.plans],
            poll_interval_s=poll_interval_s,
        ).as_dict()
        target = self._replay_path(f"{name}.json")

        def write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(dataset, indent=1))

        await self.hass.async_add_executor_job(write)
        return {"file": target.name, "inputs": {k: len(v) for k, v in dataset["inputs"].items()}}

    async def async_list_datasets(self) -> list[str]:
        folder = self.data_dir / "replay"

        def scan() -> list[str]:
            return sorted(p.name for p in folder.glob("*.json")) if folder.exists() else []

        return await self.hass.async_add_executor_job(scan)

    # --------------------------------------------------------------- storage

    def _schedule_save(self, monitor: bool = False) -> None:
        self._state_store.async_delay_save(self.engine.as_dict, 5)
        self._event_store.async_delay_save(self._event_data, 30)
        if monitor:
            self._monitor_store.async_delay_save(self.monitor.as_dict, 5)

    def monitor_changed(self) -> None:
        """Manual monitor input (external charge, odometer) – save and refresh."""
        self._monitor_store.async_delay_save(self.monitor.as_dict, 5)
        self.refresh_statistics()
        self._notify_listeners()

    def _event_data(self) -> list[dict[str, Any]]:
        cutoff = (dt_util.utcnow()
                  - timedelta(days=self.settings.event_retention_days)).isoformat()
        return [e for e in self.events if e["timestamp"] >= cutoff]

    async def _save(self) -> None:
        self.monitor.prune(dt_util.now(self.tz).date())
        await self._state_store.async_save(self.engine.as_dict())
        await self._event_store.async_save(self._event_data())
        await self._monitor_store.async_save(self.monitor.as_dict())
