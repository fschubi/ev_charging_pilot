"""WebSocket API (§12.4). Large lists only ever travel through here, never as attributes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, VERSION
from .coordinator import ChargingCenter
from .core.engine import FAILURE_HINTS
from .core.inputs import Inp
from .core.model import Value
from .core.planner import ChargeWindow, WeeklySchedule
from .core.settings import (
    DEFAULT_OPTIONS,
    OPT_MANUAL_CURRENT_A,
    OPT_MANUAL_TARGET_SOC,
    PriceSource,
    RunMode,
)
from .core.summary import summary
from .reports import async_create_report, async_list_reports
from .settings_schema import GROUPS, apply_changes, current_values
from .vehicle_image import IMAGE_URL

PREFIX = DOMAIN


def _center(hass: HomeAssistant) -> ChargingCenter | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0].runtime_data if entries else None


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _value(value: Value, now: datetime) -> dict[str, Any]:
    age = value.age_s(now)
    return {
        "raw": value.raw,
        "value": value.normalized,
        "unit": value.unit,
        "source": value.source,
        "updated_at": _iso(value.updated_at),
        "age_s": round(age) if age is not None else None,
        "quality": str(value.quality),
    }


def _window(window: ChargeWindow | None) -> dict[str, Any] | None:
    if window is None:
        return None
    e = window.estimate
    return {
        "source_id": window.source_id,
        "name": window.name,
        "reason": str(window.reason),
        "start": _iso(window.start),
        "departure": _iso(window.departure),
        "ready_at": _iso(window.ready_at),
        "fallback_without_soc": window.fallback_without_soc,
        "blocks": [[_iso(a), _iso(b)] for a, b in window.blocks],
        "minimum_soc_pct": window.minimum_soc_pct,
        "preferred_soc_pct": window.preferred_soc_pct,
        "climate": window.climate,
        "estimate": {
            "soc_pct": e.soc_pct,
            "needed_kwh": e.needed_kwh,
            "duration_min": round(e.duration.total_seconds() / 60) if e.duration else None,
            "expected_soc_at_departure": e.expected_soc_at_departure,
            "minimum_reachable": e.minimum_reachable,
            "preferred_reachable": e.preferred_reachable,
            "finish_at": _iso(e.finish_at),
            "cost_eur": e.cost_eur,
        },
    }


def vehicle_link(center: ChargingCenter) -> dict[str, Any]:
    """Vehicle access: data is always read; commands only with "read & write" (§1.2)."""
    soc = center.engine.soc
    path = center.ports.ovms_path
    return {
        "data_configured": Inp.OVMS_SOC in center.entity_ids,
        "data_quality": str(soc.quality),
        "data_updated_at": _iso(soc.updated_at),
        "read_write": center.settings.ovms_enabled,
        "command_path": path,
        "commands_ready": center.settings.ovms_enabled and path is not None,
    }


def snapshot(center: ChargingCenter) -> dict[str, Any]:
    engine = center.engine
    now = dt_util.utcnow()
    desired = engine.desired
    session = engine.sessions.open
    return {
        "name": center.name,
        "vehicle_name": center.vehicle_name,
        "version": VERSION,
        "mode": str(center.mode),
        "automation_enabled": engine.automation_enabled,
        "summary": summary(engine, now, center.mode is RunMode.LIVE),
        "target_held": engine.target_held,
        "learned": engine.learned.as_dict(),
        "executor": {
            "state": str(engine.executor.state) if engine.executor.state else None,
            "since": _iso(engine.executor.state_since),
            "failure_code": engine.executor.failure_code,
            "failure_hint": FAILURE_HINTS.get(engine.executor.failure_code or ""),
            "session_id": engine.executor.session_id,
            "cp_masked": engine.executor.cp_masked(now),
        },
        "desired": None if desired is None else {
            "charger_enabled": desired.charger_enabled,
            "reason": str(desired.reason),
            "source_id": desired.source_id,
            "valid_until": _iso(desired.valid_until),
            "climate": None if desired.climate is None else {
                "duration_min": desired.climate.duration_min,
                "start_at": _iso(desired.climate.start_at),
            },
        },
        "health": {"status": str(engine.health.status), "reasons": list(engine.health.reasons),
                   "shelly_config_ok": engine.shelly_config_ok,
                   "shelly_deviations": center.shelly_deviations,
                   "shelly_host": bool(center.ports.shelly_host)},
        "data_conflict": engine.data_conflict,
        "values": {k.value: _value(v, now) for k, v in engine.values.items()
                   if k in center.entity_ids},
        "soc": _value(engine.soc, now),
        "cabin_changed_at": _iso(engine.cabin_changed_at),
        "outside_temperature": _value(engine.outside, now),
        "active_window": _window(engine.active_window),
        "next_window": _window(engine.next_window),
        "windows": [_window(w) for w in engine.windows],
        "plans": [p.as_dict() for p in engine.plans],
        "override": engine.override.as_dict() if engine.override else None,
        "one_shot": engine.one_shot.as_dict() if engine.one_shot else None,
        "charge_test": engine.charge_test.as_dict() if engine.charge_test else None,
        "price_push_test": center.price_push_test,
        "mail_result": {**center.mail_result, "recipients": len(
            center.mail_result.get("recipients") or [])} if center.mail_result else None,
        "mail_enabled": center.settings.mail_enabled,
        "climate": None if engine.climate_plan is None else {
            "duration_min": engine.climate_plan.duration_min,
            "start_at": _iso(engine.climate_plan.start_at),
            "until": _iso(engine.climate_plan.until),
            "blocked": engine.climate_blocked,
        },
        "session": None if session is None else {
            "session_id": session.session_id,
            "started_at": _iso(session.started_at),
            "energy_kwh": engine.sessions.session_energy_kwh,
            "max_power_w": session.max_power_w,
            "start_soc_pct": session.start_soc_pct,
        },
        "last_result": engine.last_result,
        "hv_cycles_today": engine.hv.today,
        "prices": {
            "source": str(center.settings.price_source),
            "dynamic": engine.dynamic_prices,
            "current_eur_kwh": round(engine.price_at(now), 4),
            "last_update": _iso(center.price_fetcher.last_update),
            "error": center.price_fetcher.last_error,
            "slots": [s.as_dict() for s in engine.price_schedule.slots
                      if s.end > now][:96],
        },
        "statistics": center.statistics,
        "settings": {
            "cp_failsafe_verified": center.settings.cp_failsafe_verified,
            "ovms_enabled": center.settings.ovms_enabled,
            "climate_enabled": center.settings.climate_enabled,
            "odometer_source": str(center.settings.odometer_source),
            "price_eur_kwh": center.settings.price_history[-1].eur_per_kwh,
            "vehicle_charger_kw": center.settings.vehicle_charger_kw,
            "manual_target_soc": center.settings.manual_target_soc,
            "max_power_kw": center.settings.max_power_kw,
            "manual_current_a": center.settings.manual_current_a,
            "default_current_a": center.settings.default_current_a,
            "phases": center.settings.phases,
            "current_settable": center.ports.current_settable,
            "external_price_buttons": list(center.settings.external_price_buttons),
        },
        "history": [list(item) for item in center.history],
        "vehicle_link": vehicle_link(center),
        "vehicle_image": f"{IMAGE_URL}?v={center.vehicle_image_version}"
        if center.vehicle_image_version else None,
        "entities": {k.value: v for k, v in center.entity_ids.items()},
    }


def _send(connection, msg, payload) -> None:
    connection.send_result(msg["id"], payload)


def _require(connection, msg, hass) -> ChargingCenter | None:
    center = _center(hass)
    if center is None:
        connection.send_error(msg["id"], "not_loaded", "EV Charging Pilot ist nicht geladen")
    return center


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/state"})
@callback
def ws_state(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        _send(connection, msg, snapshot(center))


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/get_health"})
@callback
def ws_health(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        state = snapshot(center)
        _send(connection, msg, {"health": state["health"], "values": state["values"],
                                "data_conflict": state["data_conflict"],
                                "executor": state["executor"],
                                "hv_cycles_today": state["hv_cycles_today"]})


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/get_plan_preview"})
@callback
def ws_plan_preview(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        state = snapshot(center)
        _send(connection, msg, {k: state[k] for k in (
            "next_window", "active_window", "windows", "climate", "soc", "outside_temperature",
            "override", "one_shot")})


def _paged(items: list, msg) -> dict[str, Any]:
    items = list(reversed(items))
    offset, limit = msg.get("offset", 0), msg.get("limit", 100)
    return {"total": len(items), "items": items[offset:offset + limit]}


PAGING = {vol.Optional("limit", default=100): vol.All(int, vol.Range(1, 2000)),
          vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0))}


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/get_sessions", **PAGING})
@callback
def ws_sessions(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        # The power curve only travels with the detail view.
        items = [{k: v for k, v in s.as_dict().items() if k != "trace"}
                 for s in center.monitor.data.sessions]
        _send(connection, msg, _paged(items, msg))


# Events shown with a session: wakeups and the switch-on happen before the stable start.
DETAIL_EVENTS_BEFORE = timedelta(minutes=15)
DETAIL_EVENTS_AFTER = timedelta(minutes=2)
DETAIL_TRACE_INPUTS = (Inp.CHARGE_POWER, Inp.OVMS_CHARGE_POWER, Inp.OVMS_SOC)


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/get_session_detail", vol.Required("session_id"): str})
@websocket_api.async_response
async def ws_session_detail(hass, connection, msg) -> None:
    if not (center := _require(connection, msg, hass)):
        return
    session = next((s for s in center.monitor.data.sessions
                    if s.session_id == msg["session_id"]), None)
    if session is None:
        connection.send_error(msg["id"], "not_found", "Session nicht gefunden")
        return
    data = session.as_dict()
    end = session.ended_at or session.started_at
    data["trace_source"] = "session" if len(session.trace) >= 2 else None
    if data["trace_source"] is None and session.ended_at is not None:
        # Sessions from before v0.20.0 have no curve of their own: take it from
        # the recorder while it still holds those days.
        minutes = await center.async_recorder_minutes(
            DETAIL_TRACE_INPUTS, session.started_at, end + timedelta(minutes=1))
        if minutes:
            data["trace"] = [
                [round((minute - session.started_at).total_seconds()),
                 _rounded(values.get(Inp.CHARGE_POWER), 0),
                 _rounded(values.get(Inp.OVMS_CHARGE_POWER), 0),
                 _rounded(values.get(Inp.OVMS_SOC), 1)]
                for minute, values in minutes]
            data["trace_source"] = "recorder"
    since, until = session.started_at - DETAIL_EVENTS_BEFORE, end + DETAIL_EVENTS_AFTER
    data["events"] = [e for e in center.events if e["severity"] != "debug"
                      and since <= datetime.fromisoformat(e["timestamp"]) <= until][-100:]
    _send(connection, msg, data)


def _rounded(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(value) if digits == 0 else round(value, digits)


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/get_trips", **PAGING})
@callback
def ws_trips(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        items = [{k: v for k, v in t.as_dict().items() if k != "trace"}
                 for t in center.monitor.data.trips]
        _send(connection, msg, _paged(items, msg))


TRIP_TRACE_INPUTS = (Inp.OVMS_SPEED, Inp.OVMS_BATTERY_POWER, Inp.OVMS_SOC)
TRIP_RECORDER_STEP_S = 15


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/get_trip_detail", vol.Required("trip_id"): str})
@websocket_api.async_response
async def ws_trip_detail(hass, connection, msg) -> None:
    if not (center := _require(connection, msg, hass)):
        return
    trip = next((t for t in center.monitor.data.trips if t.trip_id == msg["trip_id"]), None)
    if trip is None:
        connection.send_error(msg["id"], "not_found", "Fahrt nicht gefunden")
        return
    data = trip.as_dict()
    data["trace_source"] = "trip" if len(trip.trace) >= 2 else None
    if data["trace_source"] is None:
        # Trips from before v0.22.0: the curve comes from the recorder.
        steps = await center.async_recorder_minutes(
            TRIP_TRACE_INPUTS, trip.started_at, trip.ended_at + timedelta(seconds=15),
            step_s=TRIP_RECORDER_STEP_S)
        if steps:
            data["trace"] = [
                [round((moment - trip.started_at).total_seconds()),
                 _rounded1(values.get(Inp.OVMS_SPEED)), _rounded(values.get(
                     Inp.OVMS_BATTERY_POWER), 0), _rounded(values.get(Inp.OVMS_SOC), 1)]
                for moment, values in steps]
            data["trace_source"] = "recorder"
    if data.get("style") is None and data.get("trace"):
        from .core.trips import driving_style

        data["style"] = driving_style(data["trace"])
    # What the trip cost at home: net battery energy, charging loss, home price.
    s = center.engine.settings
    net = (trip.vehicle_energy_used_kwh or 0) - (trip.recovered_energy_kwh or 0) \
        if trip.vehicle_energy_used_kwh is not None else None
    price = center.monitor.home_price(s)
    data["home_price_eur_kwh"] = round(price, 4)
    data["grid_energy_kwh"] = round(net / s.charge_efficiency, 3) if net else None
    data["cost_eur"] = round(net / s.charge_efficiency * price, 2) if net else None
    _send(connection, msg, data)


TEMPERATURE_INPUTS = (Inp.OVMS_CABIN_TEMP, Inp.OVMS_OUTSIDE_TEMP, Inp.OVMS_HVAC)


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/get_temperature_history",
    vol.Optional("hours", default=24): vol.All(int, vol.Range(1, 72))})
@websocket_api.async_response
async def ws_temperature_history(hass, connection, msg) -> None:
    """Cabin and outside temperature with the climate runs, from the recorder."""
    if not (center := _require(connection, msg, hass)):
        return
    end = dt_util.utcnow()
    start = end - timedelta(hours=msg["hours"])
    step_s = 60 if msg["hours"] <= 6 else 120 if msg["hours"] <= 24 else 300
    steps = await center.async_recorder_minutes(TEMPERATURE_INPUTS, start, end, step_s=step_s)
    _send(connection, msg, {
        "step_s": step_s,
        "points": [[_iso(moment), _rounded1(values.get(Inp.OVMS_CABIN_TEMP)),
                    _rounded1(values.get(Inp.OVMS_OUTSIDE_TEMP)),
                    bool(values.get(Inp.OVMS_HVAC)) if values.get(Inp.OVMS_HVAC) is not None
                    else None]
                   for moment, values in steps or []],
    })


def _rounded1(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


@websocket_api.websocket_command(
    {vol.Required("type"): f"{PREFIX}/get_external_charges", **PAGING})
@callback
def ws_external(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        _send(connection, msg, _paged([e.as_dict() for e in center.monitor.data.external], msg))


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/get_month_statistics",
    vol.Optional("year"): int,
    vol.Optional("month"): vol.All(int, vol.Range(1, 12)),
})
@callback
def ws_month(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        today = dt_util.now(center.tz).date()
        _send(connection, msg, center.monitor.month(
            msg.get("year", today.year), msg.get("month", today.month), center.settings, today))


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/get_year_statistics", vol.Optional("year"): int})
@callback
def ws_year(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        today = dt_util.now(center.tz).date()
        _send(connection, msg, center.monitor.year(msg.get("year", today.year), center.settings,
                                                   today))


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/get_temperature_statistics", vol.Optional("year"): int})
@callback
def ws_temperature(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        _send(connection, msg, center.monitor.temperatures(center.settings, msg.get("year")))


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/get_events",
    vol.Optional("limit", default=200): vol.All(int, vol.Range(1, 5000)),
    vol.Optional("category"): str,
    vol.Optional("min_severity"): vol.In(["debug", "info", "warning", "error", "critical"]),
})
@callback
def ws_events(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        order = ["debug", "info", "warning", "error", "critical"]
        floor = order.index(msg.get("min_severity", "debug"))
        items = [e for e in center.events
                 if (not msg.get("category") or e["category"] == msg["category"])
                 and order.index(e["severity"]) >= floor]
        _send(connection, msg, {"total": len(items),
                                "items": list(reversed(items))[: msg["limit"]]})


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/get_plans"})
@callback
def ws_get_plans(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        _send(connection, msg, {"plans": [p.as_dict() for p in center.engine.plans]})


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/set_plans", vol.Required("plans"): [dict]})
# Charging plans are everyday use (every household member), unlike the settings.
@websocket_api.async_response
async def ws_set_plans(hass, connection, msg) -> None:
    center = _require(connection, msg, hass)
    if center is None:
        return
    try:
        plans = [WeeklySchedule.from_dict(p) for p in msg["plans"]]
        await center.async_run(lambda now: center.engine.set_plans(now, plans))
    except (KeyError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_plan", str(err))
        return
    _send(connection, msg, {"plans": [p.as_dict() for p in center.engine.plans]})


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/get_replay"})
@websocket_api.async_response
async def ws_replay(hass, connection, msg) -> None:
    center = _require(connection, msg, hass)
    if center is None:
        return
    _send(connection, msg, {"last": center.last_replay,
                            "files": await center.async_list_datasets()})


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/create_report",
    vol.Optional("year"): int,
    vol.Optional("month"): vol.Any(None, vol.All(int, vol.Range(1, 12))),
})
@websocket_api.async_response
async def ws_create_report(hass, connection, msg) -> None:
    center = _require(connection, msg, hass)
    if center is None:
        return
    today = dt_util.now(center.tz).date()
    _send(connection, msg, await async_create_report(
        center, msg.get("year", today.year), msg.get("month")))


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/list_reports"})
@websocket_api.async_response
async def ws_list_reports(hass, connection, msg) -> None:
    center = _require(connection, msg, hass)
    if center is None:
        return
    _send(connection, msg, {"items": await async_list_reports(center)})


# Personal data in the settings: only admins see it (others get a placeholder).
PRIVATE_FIELDS = ("mail_user", "mail_from", "mail_to_1", "mail_to_2", "report_push_targets")


def _private(values: dict[str, Any], user) -> dict[str, Any]:
    if user.is_admin:
        return values
    return {k: ("•••" if k in PRIVATE_FIELDS and v else v) for k, v in values.items()}


@websocket_api.websocket_command({vol.Required("type"): f"{PREFIX}/get_settings"})
@callback
def ws_get_settings(hass, connection, msg) -> None:
    if center := _require(connection, msg, hass):
        _send(connection, msg, {
            "groups": GROUPS,
            "values": _private(current_values(dict(center.entry.options)), connection.user),
            "price_history": list(dict(center.entry.options).get("price_history")
                                  or DEFAULT_OPTIONS["price_history"]),
            "is_admin": connection.user.is_admin,
            # Suggestions for push-target fields (the phones known to HA).
            "notify_services": sorted(
                f"notify.{name}" for name in hass.services.async_services().get("notify", {})
                if name.startswith("mobile_app_")),
        })


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/set_settings", vol.Required("values"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set_settings(hass, connection, msg) -> None:
    center = _require(connection, msg, hass)
    if center is None:
        return
    entry = center.entry
    try:
        options = apply_changes(dict(entry.options), dict(msg["values"]))
    except (ValueError, TypeError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    # Saving reloads the entry (except a pure mode change) – the panel reconnects itself.
    hass.config_entries.async_update_entry(entry, options=options)
    _send(connection, msg, {"values": current_values(options)})


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/set_manual_target",
    vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=20, max=100))})
@callback
def ws_set_manual_target(hass, connection, msg) -> None:
    """Target of "Jetzt laden" – everyday use, applied live without a reload."""
    if center := _require(connection, msg, hass):
        value = int(msg["value"]) // 5 * 5
        hass.config_entries.async_update_entry(
            center.entry, options={**center.entry.options, OPT_MANUAL_TARGET_SOC: value})
        _send(connection, msg, {"value": value})


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/check_prices",
    vol.Required("source"): vol.In([s.value for s in PriceSource]),
    vol.Optional("entity_id"): vol.Any(None, str)})
@websocket_api.async_response
async def ws_check_prices(hass, connection, msg) -> None:
    """Settings: does the chosen price source deliver a usable price list?"""
    if center := _require(connection, msg, hass):
        _send(connection, msg, await center.price_fetcher.async_check(
            PriceSource(msg["source"]), msg.get("entity_id")))


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/set_manual_current",
    vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=32))})
@callback
def ws_set_manual_current(hass, connection, msg) -> None:
    """Charging current of "Jetzt laden" (0 = standard) – applied live without a reload."""
    if center := _require(connection, msg, hass):
        value = int(msg["value"])
        value = value if value >= 6 else 0
        hass.config_entries.async_update_entry(
            center.entry, options={**center.entry.options, OPT_MANUAL_CURRENT_A: value})
        _send(connection, msg, {"value": value})


@websocket_api.websocket_command({
    vol.Required("type"): f"{PREFIX}/run_system_check",
    vol.Optional("send_test_push", default=False): bool})
@websocket_api.async_response
async def ws_run_system_check(hass, connection, msg) -> None:
    """Check every link without switching anything and without waking the car."""
    center = _require(connection, msg, hass)
    if center is None:
        return
    from .system_check import async_system_check

    results = await async_system_check(center, send_test_push=msg["send_test_push"])
    _send(connection, msg, {"results": results, "at": _iso(dt_util.utcnow())})


COMMANDS = (ws_run_system_check, ws_set_manual_target, ws_set_manual_current, ws_check_prices,
            ws_get_settings,
            ws_set_settings,
            ws_create_report, ws_list_reports, ws_state,
            ws_health, ws_plan_preview, ws_sessions, ws_session_detail, ws_trip_detail,
            ws_temperature_history,
            ws_trips, ws_external, ws_month, ws_year,
            ws_temperature, ws_events, ws_get_plans, ws_set_plans, ws_replay)


def async_register(hass: HomeAssistant) -> None:
    key = f"{DOMAIN}_ws_registered"
    if hass.data.get(key):
        return
    hass.data[key] = True
    for command in COMMANDS:
        websocket_api.async_register_command(hass, command)
