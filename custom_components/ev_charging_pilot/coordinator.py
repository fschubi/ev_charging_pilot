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
from dataclasses import replace
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
    ACTION_EXT_PRICE,
    ACTION_NOW,
    ACTION_PLAN,
    ACTION_RETRY,
    ACTION_TONIGHT,
    BUS_EVENT,
    CONF_OVMS_COMMAND_SCRIPT,
    CONF_OVMS_COMMAND_TOPIC,
    CONF_SHELLY_HOST,
    CONF_VEHICLE_NAME,
    DATA_DIR,
    DEFAULT_VEHICLE_NAME,
    DOMAIN,
    LOGBOOK_CODES,
    LOGBOOK_SEVERITIES,
    STATISTICS_REFRESH_S,
    STORAGE_KEY_EVENTS,
    STORAGE_KEY_MONITOR,
    STORAGE_KEY_STATE,
    STORAGE_VERSION,
    TICK_SECONDS,
    title_for,
)
from .core.engine import (
    Engine,
    EngineConfig,
    Notification,
    TickResult,
    external_price_url,
)
from .core.inputs import Inp, RawState, to_value
from .core.mail import MONTHS, build_message, friendly_error, monthly_mail
from .core.mail import send as send_mail
from .core.model import Category, Event, Severity
from .core.monitor import Monitor
from .core.ports import CommandRecorder
from .core.prices import PriceSlot, parse_price_input
from .core.replay import ReplayDataset, run_replay
from .core.settings import OPT_MODE, RunMode, Settings
from .core.summary import weekly_text
from .ha_ports import HaPorts, PortError, shelly_deviations
from .notifications import Notifier
from .price_source import PriceFetcher
from .reports import async_create_report, previous_month, report_name

_LOGGER = logging.getLogger(__name__)
# Upper bound for one hardware/cloud command (switch, number, OVMS, script).
COMMAND_TIMEOUT_S = 30

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
            ovms_entity=self.conf.get(Inp.OVMS_SOC.value),
            max_current=self.conf.get(Inp.MAX_CURRENT.value),
        )
        self.monitor = Monitor(self.tz)
        self.engine = Engine(
            EngineConfig(
                settings=self.settings,
                tz=self.tz,
                configured=frozenset(self.entity_ids),
                cp_pulse_available=self.ports.cp_pulse_available,
                ovms_command_available=self.ports.ovms_command_available,
                current_settable=self.ports.current_settable,
            ),
            self.monitor,
        )
        self.notifier = Notifier(hass, self.conf, self.vehicle_name)
        self.notifier.price_buttons = self.settings.external_price_buttons
        # Diagnose: test of the price question of an external charge (push with text field).
        self.price_push_test: dict[str, Any] | None = None
        # Last report e-mail (Test-Center).
        self.mail_result: dict[str, Any] | None = None
        # Set on unload: a tick or price refresh still in flight must not act any more.
        self._closed = False
        # Monthly report waiting for a running session to end (year, month).
        self._report_due: tuple[int, int] | None = None
        self.price_fetcher = PriceFetcher(hass, self.tz, self._on_prices, self._on_price_problem)
        self.recorder = CommandRecorder()
        self.events: deque[dict[str, Any]] = deque(maxlen=20000)
        self.statistics: dict[str, Any] = {}
        # One sample per minute for the cockpit chart (24 h, not persisted).
        self.history: deque[tuple[str, float | None, float | None]] = deque(maxlen=1440)
        self.last_replay: dict[str, Any] | None = None
        self.shelly_deviations: list[dict[str, Any]] | None = None
        self.vehicle_image_version: int | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._lock = asyncio.Lock()
        self._statistics_at: datetime | None = None
        self.statistics_month_start: datetime | None = None
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
    def vehicle_name(self) -> str:
        return str(self.entry.options.get(CONF_VEHICLE_NAME)
                   or self.conf.get(CONF_VEHICLE_NAME) or DEFAULT_VEHICLE_NAME)

    @property
    def name(self) -> str:
        """Display title, e.g. "Smarty Charging Pilot" (panel, device, PDF, logbook)."""
        return title_for(self.vehicle_name)

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
        self._unsubs.append(async_track_time_change(
            self.hass, self._on_weekly_time, hour=18, minute=0, second=0))
        self.entry.async_create_background_task(
            self.hass, self._drift_check(), f"{DOMAIN} drift check")
        self.entry.async_create_background_task(
            self.hass, self._async_backfill_history(), f"{DOMAIN} chart history")
        self.price_fetcher.start(self.settings)
        from .vehicle_image import image_version

        self.vehicle_image_version = await self.hass.async_add_executor_job(
            image_version, self.hass)
        await self.async_tick()
        await self._catch_up_report()

    async def async_shutdown(self) -> None:
        self._closed = True
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
        if self._closed:
            return
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
            self._report_due = previous_month(now.astimezone(self.tz))
            self._run_due_report()

    @callback
    def _run_due_report(self) -> None:
        """The monthly report waits for a charge still running across midnight."""
        if self._report_due is None or self.engine.sessions.open is not None:
            return
        year, month = self._report_due
        self._report_due = None
        self.hass.async_create_task(self._monthly_report_safe(year, month))

    async def _monthly_report_safe(self, year: int, month: int) -> None:
        try:
            await self.async_monthly_report(datetime(year, month, 1, tzinfo=self.tz)
                                            + timedelta(days=32))
        except Exception as err:  # noqa: BLE001 – report it instead of a silent task error
            _LOGGER.exception("Monatsbericht %02d/%d fehlgeschlagen", month, year)
            await self._handle(TickResult(
                events=[Event(dt_util.utcnow(), Category.CONFIG, Severity.ERROR,
                              "REPORT_FAILED",
                              f"Monatsbericht {month:02d}/{year} fehlgeschlagen: {err}")],
                notifications=[Notification(
                    "report_failed", "high", "Monatsbericht fehlgeschlagen",
                    f"Der Bericht für {month:02d}/{year} konnte nicht erstellt werden: {err}")]))

    async def _catch_up_report(self) -> None:
        """HA was down at 06:00 on the 1st: produce last month's report later."""
        if not self.settings.report_auto_monthly:
            return
        local = dt_util.now(self.tz)
        if local.day > 7 or (local.day == 1 and local.hour < 6):
            return
        year, month = previous_month(local)
        path = self.data_dir / "reports" / report_name(year, month)
        if not await self.hass.async_add_executor_job(path.exists):
            self._report_due = (year, month)

    @callback
    def _on_weekly_time(self, now: datetime) -> None:
        if now.astimezone(self.tz).weekday() == 6:
            self.hass.async_create_task(self.async_weekly_summary(now))

    async def async_weekly_summary(self, now: datetime) -> str:
        """Sunday 18:00: the last seven days in one push."""
        text = weekly_text(self.monitor.week(now))
        self._log(Event(dt_util.utcnow(), Category.USER, Severity.INFO, "WEEKLY_SUMMARY",
                        f"Wochenrückblick: {text}"))
        if self.settings.notify.weekly:
            await self.notifier.async_send(Notification("weekly", "normal",
                                                        "Wochenrückblick", text))
        return text

    async def async_monthly_report(self, now: datetime) -> dict[str, Any]:
        year, month = previous_month(now.astimezone(self.tz))
        report = await async_create_report(self, year, month)
        self._log(Event(dt_util.utcnow(), Category.CONFIG, Severity.INFO, "REPORT_CREATED",
                        f"Monatsbericht {month:02d}/{year} erstellt", data=report))
        if self.settings.notify.report:
            await self.notifier.async_send(Notification(
                "report", "normal", "Monatsbericht",
                f"Der Bericht für {month:02d}/{year} liegt im Panel unter Hausstrom bereit."))
        if self.settings.mail_enabled:
            await self.async_send_report_mail(year, month, report)
        await self._push_report_amount(year, month)
        return report

    def _month_numbers(self, year: int, month: int) -> tuple[dict[str, Any], int]:
        today = datetime.now(self.tz).date()
        summary = self.monitor.month(year, month, self.settings, today)
        external = sum(1 for e in self.monitor.data.external
                       if e.date.year == year and e.date.month == month)
        return summary, external

    async def async_send_report_mail(self, year: int, month: int,
                                     report: dict[str, Any] | None = None,
                                     *, test: bool = False) -> dict[str, Any]:
        """Monthly PDF by e-mail; the result is kept for the Test-Center."""
        now = dt_util.utcnow()
        config = self.settings.mail
        result: dict[str, Any] = {"at": now.isoformat(), "month": f"{month:02d}/{year}",
                                  "recipients": list(config.recipients), "test": test}
        try:
            if missing := config.missing():
                raise ValueError(f"E-Mail nicht eingerichtet: {missing}")
            report = report or await async_create_report(self, year, month)
            summary, external = self._month_numbers(year, month)
            subject, body = monthly_mail(summary, self.vehicle_name, year, month, external)
            if test:
                subject = f"[Test] {subject}"
            pdf = await self.hass.async_add_executor_job(
                (self.data_dir / "reports" / report["file"]).read_bytes)
            message = build_message(config, subject, body, (report["file"], pdf),
                                    sender_name=f"{self.vehicle_name} Charging Pilot")
            await self.hass.async_add_executor_job(send_mail, config, message)
        except Exception as err:  # noqa: BLE001 – any SMTP/file problem is reported
            text = str(err) if isinstance(err, ValueError) else friendly_error(err)
            result.update(ok=False, error=text)
            self._log(Event(now, Category.CONFIG, Severity.WARNING, "REPORT_MAIL_FAILED",
                            f"Monatsbericht per Mail fehlgeschlagen: {text}"))
            if not test:
                await self.notifier.async_send(Notification(
                    "report_failed", "high", "Bericht nicht versendet",
                    f"Der Monatsbericht {month:02d}/{year} konnte nicht gemailt werden: {text}"))
        else:
            result.update(ok=True, subject=subject)
            count = len(config.recipients)
            self._log(Event(now, Category.CONFIG, Severity.INFO, "REPORT_MAIL_SENT",
                            f"Monatsbericht {month:02d}/{year} gemailt an {count} "
                            f"Empfänger"))  # addresses stay out of the event log
        self.mail_result = result
        self._notify_listeners()
        return result

    async def _push_report_amount(self, year: int, month: int) -> None:
        """The monthly amount as a push to extra phones (e.g. whoever pays the power)."""
        if not self.settings.report_push_targets:
            return
        summary, _ = self._month_numbers(year, month)
        kwh = f"{summary.get('home_energy_kwh') or 0:.1f}".replace(".", ",")
        eur = f"{summary.get('home_cost_eur') or 0:.2f}".replace(".", ",")
        text = (f"{MONTHS[month - 1]} {year}: zu Hause {kwh} kWh geladen = {eur} €. "
                "Antippen öffnet den Bericht im Panel.")
        for target in self.settings.report_push_targets:
            await self.notifier.async_send(
                Notification("report_amount", "normal", "Ladekosten Vormonat", text), target)

    def apply_options(self, options: dict[str, Any]) -> None:
        """Mode change only – no reload needed (the switch writes the option)."""
        self.settings = Settings.from_options(options)
        self.engine.settings = self.settings
        self.notifier.price_buttons = self.settings.external_price_buttons

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
        if self._lock.locked() or self._closed:
            return
        async with self._lock:
            now = dt_util.utcnow()
            self.engine.set_vehicle_commands(self.ports.ovms_command_available)
            self.engine.set_shadow(self.mode is not RunMode.LIVE)
            result = self.engine.tick(now, self._raw_states())
            self._sample_history(now)
            # A new month/year must be computed before any state is written: the
            # TOTAL sensors would otherwise publish last month's total under the new
            # last_reset, and the recorder would book it as a negative month.
            if self._statistics_at is None or self._new_period(now) or \
                    (now - self._statistics_at).total_seconds() >= STATISTICS_REFRESH_S:
                self.refresh_statistics(now)
            await self._handle(result)
            self._run_due_report()

    async def _async_backfill_history(self) -> None:
        """Cockpit chart after a restart: the last 24 h come from the recorder."""
        end = dt_util.utcnow().replace(second=0, microsecond=0)
        start = end - timedelta(hours=24)
        minutes = await self.async_recorder_minutes((Inp.CHARGE_POWER, Inp.OVMS_SOC), start, end)
        if not minutes:
            return
        samples = []
        for minute, values in minutes:
            power, soc = values.get(Inp.CHARGE_POWER), values.get(Inp.OVMS_SOC)
            samples.append((minute.isoformat(), round(power) if power is not None else None,
                            round(soc, 1) if soc is not None else None))
        live = list(self.history)
        first_live = live[0][0] if live else None
        self.history.clear()
        self.history.extend(s for s in samples if first_live is None or s[0] < first_live)
        self.history.extend(live)
        self._notify_listeners()

    async def async_recorder_minutes(
        self, inputs: tuple[Inp, ...], start: datetime, end: datetime, step_s: int = 60
    ) -> list[tuple[datetime, dict[Inp, float | None]]] | None:
        """Recorder values of the mapped inputs, resampled to one value per ``step_s``.

        The recorder only stores changes, so each step carries the last value
        known up to its end. None if nothing is mapped or the recorder fails.
        """
        if "recorder" not in self.hass.config.components:
            return None
        from homeassistant.components.recorder import get_instance, history

        ids = {inp: self.entity_ids[inp] for inp in inputs if inp in self.entity_ids}
        if not ids:
            return None
        start = start.replace(second=0, microsecond=0) if step_s >= 60 \
            else start.replace(microsecond=0)
        step = timedelta(seconds=step_s)

        def load() -> dict[str, list]:
            # A state stamped exactly at the start is neither "before" nor "after" it
            # for the recorder – one second earlier catches it.
            return history.get_significant_states(
                self.hass, start - timedelta(seconds=1), end, list(ids.values()),
                include_start_time_state=True, significant_changes_only=False)

        try:
            states = await get_instance(self.hass).async_add_executor_job(load)
        except Exception:  # noqa: BLE001 – charts are a nicety, never a reason to fail
            _LOGGER.debug("Verlauf aus dem Recorder nicht ladbar", exc_info=True)
            return None
        series: dict[Inp, list[tuple[datetime, float | None]]] = {}
        for inp, entity_id in ids.items():
            points = []
            for s in states.get(entity_id, []):
                value = to_value(inp, RawState(s.state, s.last_updated, s.last_updated,
                                               dict(s.attributes)))
                points.append((s.last_updated, float(value.normalized)
                               if value.available and value.normalized is not None else None))
            series[inp] = points
        current: dict[Inp, float | None] = dict.fromkeys(series)
        position = dict.fromkeys(series, 0)
        minutes = []
        minute = start
        while minute < end:
            for inp, points in series.items():
                while position[inp] < len(points) and \
                        points[position[inp]][0] < minute + step:
                    current[inp] = points[position[inp]][1]
                    position[inp] += 1
            minutes.append((minute, dict(current)))
            minute += step
        return minutes

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
            # A mode switched a moment ago must already count for this action.
            self.engine.set_shadow(self.mode is not RunMode.LIVE)
            result = action(dt_util.utcnow())
            await self._handle(result)
        await self.async_tick()
        return result

    async def _handle(self, result: TickResult) -> None:
        now = dt_util.utcnow()
        for command in result.commands:
            if self.mode is RunMode.LIVE:
                try:
                    # A hanging cloud call (wallbox, OVMS) must not hold the lock – the
                    # control loop (target stop, loss detection) would stand still.
                    async with asyncio.timeout(COMMAND_TIMEOUT_S):
                        await self.ports.execute(command, self.settings)
                except Exception as err:  # noqa: BLE001 – a port must never kill the tick
                    self.recorder.record(now, command, False)
                    reason = f"keine Antwort nach {COMMAND_TIMEOUT_S} s" \
                        if isinstance(err, TimeoutError) else str(err)
                    self._log(Event(now, Category.CHARGING, Severity.ERROR, "COMMAND_FAILED",
                                    f"{command.describe()} fehlgeschlagen: {reason}"))
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

    def log_event(self, event: Event) -> None:
        """Log from outside the tick (system check, …) and persist it."""
        self._log(event)
        self._schedule_save()
        self._notify_listeners()

    def _log(self, event: Event) -> None:
        item = event.as_dict()
        self.events.append(item)
        self.hass.bus.async_fire(BUS_EVENT, item)
        if item["severity"] in LOGBOOK_SEVERITIES or item["code"] in LOGBOOK_CODES:
            logbook.async_log_entry(self.hass, self.name, item["message"], domain=DOMAIN)

    # ----------------------------------------------------------- statistics

    def _new_period(self, now: datetime) -> bool:
        return self.statistics_month_start is None or \
            now.astimezone(self.tz).replace(day=1, hour=0, minute=0, second=0,
                                            microsecond=0) != self.statistics_month_start

    def refresh_statistics(self, now: datetime | None = None) -> None:
        now = now or dt_util.utcnow()
        local = now.astimezone(self.tz)
        today = local.date()
        self._statistics_at = now
        # The period the figures belong to – the sensors' last_reset comes from here.
        self.statistics_month_start = local.replace(day=1, hour=0, minute=0, second=0,
                                                    microsecond=0)
        year = self.monitor.year(local.year, self.settings, today)
        year.pop("months", None)
        self.statistics = {
            "month": self.monitor.month(local.year, local.month, self.settings, today),
            "year": year,
        }

    # ------------------------------------------------- notification actions

    async def _on_notification_action(self, action: str, reply: str | None = None) -> None:
        now = dt_util.utcnow()
        if action.startswith(f"{ACTION_EXT_PRICE}|"):
            # "<prefix>|<id>|<price>" from a quick-pick button, else the typed reply.
            _, charge_id, *preset = action.split("|")
            await self._set_external_price(now, charge_id, preset[0] if preset else reply)
            return
        if action == ACTION_RETRY:
            await self.async_run(self.engine.retry)
            return
        if not self.engine.plug_offer_valid(now):
            # An old push (cable pulled since, or hours ago) must not start anything.
            await self._handle(TickResult(events=[Event(
                now, Category.USER, Severity.INFO, "PUSH_ACTION_EXPIRED",
                "Push-Auswahl ignoriert – sie gehörte zu einem früheren Einstecken")]))
            return
        if action == ACTION_NOW:
            await self.async_run(self.engine.charge_now)
        elif action == ACTION_TONIGHT:
            await self.async_run(self.engine.start_one_shot)
        elif action == ACTION_PLAN:
            await self._handle(TickResult(events=[Event(
                dt_util.utcnow(), Category.USER, Severity.INFO, "PLAN_CONFIRMED",
                "Normaler Plan bestätigt")]))

    async def async_test_price_push(self) -> dict[str, Any]:
        """Send the external-charge price question once, without any charge behind it."""
        if not self.notifier.service:
            raise ValueError("Kein Push-Ziel eingerichtet (Einstellungen → Benachrichtigungen)")
        now = dt_util.utcnow()
        test_id = f"test-{now:%Y%m%d%H%M%S}"
        self.price_push_test = {"id": test_id, "sent_at": now.isoformat(), "reply": None,
                                "price_eur_kwh": None, "received_at": None}
        await self._handle(TickResult(
            events=[Event(now, Category.USER, Severity.INFO, "PRICE_PUSH_TEST_SENT",
                          "Test der Preisabfrage per Push gesendet")],
            notifications=[Notification(
                "external_test", "normal", "Test: Preis eingeben",
                "Nur ein Test – keine echte Fremdladung. Antippen öffnet die Preiseingabe, "
                "lange drücken zeigt die Preis-Knöpfe.",
                actions=(f"ext_price:{test_id}",), url=external_price_url(test_id))]))
        self._notify_listeners()
        return self.price_push_test

    def _price_push_test_answer(self, now: datetime, test_id: str,
                                reply: str | None) -> TickResult:
        test = self.price_push_test
        if test is None or test["id"] != test_id:
            return TickResult(events=[Event(now, Category.USER, Severity.INFO,
                                            "PRICE_PUSH_TEST_EXPIRED",
                                            "Antwort auf einen älteren Push-Test ignoriert")])
        price = parse_price_input(reply)
        test.update(reply=reply, price_eur_kwh=price, received_at=now.isoformat())
        text = f"{price:.2f} €/kWh erkannt".replace(".", ",") if price is not None \
            else f"Eingabe „{reply or ''}“ nicht als Preis erkannt"
        return TickResult(events=[Event(
            now, Category.USER, Severity.INFO if price is not None else Severity.WARNING,
            "PRICE_PUSH_TEST_ANSWER", f"Push-Test Preisabfrage: {text}")])

    async def async_set_external_price(self, charge_id: str, price: str) -> None:
        """Price from the panel dialog; errors go back to the caller."""
        await self._set_external_price(dt_util.utcnow(), charge_id, price, from_push=False)

    async def _set_external_price(self, now: datetime, charge_id: str,
                                  reply: str | None, *, from_push: bool = True) -> None:
        """Price per kWh for a detected external charge (push button or panel dialog)."""
        if charge_id.startswith("test-"):
            if not from_push and parse_price_input(reply) is None:
                raise ValueError(f"Kein gültiger Preis: „{reply or ''}“")
            await self._handle(self._price_push_test_answer(now, charge_id, reply))
            self._notify_listeners()
            return
        charge = next((e for e in self.monitor.data.external if e.id == charge_id), None)
        price = parse_price_input(reply)
        if charge is None or price is None:
            what = "Fremdladung nicht mehr vorhanden" if charge is None \
                else f"Preis nicht erkannt: „{reply or ''}“"
            if not from_push:
                raise ValueError(what)
            await self._handle(TickResult(
                events=[Event(now, Category.USER, Severity.WARNING, "EXTERNAL_PRICE_INVALID",
                              f"{what} – bitte im Panel ergänzen")],
                notifications=[Notification(
                    "external", "normal", "Preis nicht gespeichert",
                    f"{what}. Bitte unter Drive & Energy → Fremdladen ergänzen.")]))
            return
        self.monitor.add_external(replace(charge, price_eur_kwh=price, cost_eur=None))
        self.monitor_changed()
        def de(value: float) -> str:
            return f"{value:.2f}".replace(".", ",")

        await self._handle(TickResult(events=[Event(
            now, Category.USER, Severity.INFO, "EXTERNAL_PRICE_SET",
            f"Fremdladung {charge.date:%d.%m.}: {de(price)} €/kWh, "
            f"ca. {de(charge.energy_kwh * price)} €",
            data={"id": charge.id, "price_eur_kwh": price})]))

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
                raise ValueError("Bitte eine Datei oder einen Datensatz angeben")
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
