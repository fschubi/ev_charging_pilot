"""Services (§12.3). All of them go through arbiter and executor, never to hardware."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import ChargingCenter
from .core.planner import OverrideMode, WeeklySchedule
from .core.ports import CommandKind
from .core.statistics import ExternalCharge
from .export import DATASETS, render, rows

EXTERNAL_SOURCES = ("public", "workplace", "other_home")

OVERRIDE_SCHEMA = {
    vol.Optional("duration_min"): vol.All(vol.Coerce(int), vol.Range(min=1, max=24 * 60)),
    vol.Optional("until"): cv.datetime,
    vol.Optional("target_soc"): vol.All(vol.Coerce(int), vol.Range(min=10, max=100)),
}
PLAN_SCHEMA = vol.Schema({
    vol.Required("id"): cv.string,
    vol.Optional("name"): cv.string,
    vol.Optional("enabled", default=True): cv.boolean,
    vol.Optional("weekdays"): [vol.In(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])],
    vol.Optional("mode"): vol.In(["departure_based", "fixed_start"]),
    vol.Optional("charge_start_time"): cv.string,
    vol.Optional("departure_time"): cv.string,
    vol.Optional("ready_buffer_min"): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
    vol.Optional("minimum_departure_soc_pct"): vol.All(vol.Coerce(int), vol.Range(10, 100)),
    vol.Optional("preferred_departure_soc_pct"): vol.All(vol.Coerce(int), vol.Range(10, 100)),
    vol.Optional("climate"): vol.In(["off", "auto", "5", "10", "15"]),
}, extra=vol.REMOVE_EXTRA)

SCHEMAS: dict[str, vol.Schema] = {
    "start_charging": vol.Schema({
        vol.Optional("mode", default="until_unplugged"): vol.In(
            [m.value for m in OverrideMode if m is not OverrideMode.STOP]),
        **OVERRIDE_SCHEMA,
    }),
    "stop_charging": vol.Schema({}),
    "set_override": vol.Schema({
        vol.Required("mode"): vol.In([m.value for m in OverrideMode]), **OVERRIDE_SCHEMA}),
    "clear_override": vol.Schema({}),
    "start_one_shot": vol.Schema({vol.Optional("departure_time"): cv.time}),
    "cancel_one_shot": vol.Schema({}),
    "vehicle_wakeup": vol.Schema({}),
    "cp_wakeup": vol.Schema({}),
    "reset_error": vol.Schema({}),
    "start_climate": vol.Schema({
        vol.Optional("minutes", default=10): vol.All(vol.Coerce(int), vol.In([5, 10, 15]))}),
    "stop_climate": vol.Schema({}),
    "add_external_charge": vol.Schema({
        vol.Required("date"): cv.date,
        vol.Required("energy_kwh"): vol.All(vol.Coerce(float), vol.Range(min=0, max=200)),
        vol.Optional("source", default="public"): vol.In(EXTERNAL_SOURCES),
        vol.Optional("cost_eur"): vol.Coerce(float),
        vol.Optional("price_eur_kwh"): vol.Coerce(float),
        vol.Optional("odometer_km"): vol.Coerce(float),
        vol.Optional("soc_before"): vol.All(vol.Coerce(float), vol.Range(0, 100)),
        vol.Optional("soc_after"): vol.All(vol.Coerce(float), vol.Range(0, 100)),
        vol.Optional("provider"): cv.string,
        vol.Optional("note"): cv.string,
        vol.Optional("id"): cv.string,
    }),
    "delete_external_charge": vol.Schema({vol.Required("id"): cv.string}),
    "add_manual_odometer": vol.Schema({
        vol.Required("odometer_km"): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional("at"): cv.datetime,
    }),
    "set_plans": vol.Schema({vol.Required("plans"): [PLAN_SCHEMA]}),
    "export": vol.Schema({
        vol.Optional("dataset", default="sessions"): vol.In(DATASETS),
        vol.Optional("format", default="csv"): vol.In(["csv", "json"]),
        vol.Optional("start"): cv.date,
        vol.Optional("end"): cv.date,
    }),
    "start_replay": vol.Schema({
        vol.Exclusive("file", "source"): cv.string,
        vol.Exclusive("dataset", "source"): dict,
        vol.Optional("tick_s", default=5): vol.All(vol.Coerce(float), vol.Range(min=1, max=60)),
    }),
    "stop_replay": vol.Schema({}),
    "create_replay_dataset": vol.Schema({
        vol.Required("start"): cv.datetime,
        vol.Required("end"): cv.datetime,
        vol.Required("name"): vol.All(cv.string, vol.Match(r"^[\w\-]+$")),
        vol.Optional("poll_interval_s", default=60): vol.All(vol.Coerce(float),
                                                             vol.Range(min=0, max=900)),
    }),
}
RESPONSE = {"add_external_charge", "export", "start_replay", "create_replay_dataset"}


def _center(hass: HomeAssistant) -> ChargingCenter:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("Smart EQ Charging Center ist nicht geladen")
    return entries[0].runtime_data


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else dt_util.as_utc(dt_util.as_local(moment))


def _override_params(data: dict[str, Any], now: datetime) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if "duration_min" in data:
        params["expires_at"] = now + timedelta(minutes=data["duration_min"])
    if "until" in data:
        params["expires_at"] = _aware(data["until"])
    if "target_soc" in data:
        params["target_soc"] = data["target_soc"]
    return params


async def _handle(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    center = _center(hass)
    engine = center.engine
    data = dict(call.data)
    name = call.service
    try:
        match name:
            case "start_charging" | "set_override":
                mode = OverrideMode(data["mode"])
                await center.async_run(lambda now: engine.set_override(
                    now, mode, **_override_params(data, now)))
            case "stop_charging":
                await center.async_run(lambda now: engine.set_override(now, OverrideMode.STOP))
            case "clear_override":
                await center.async_run(engine.clear_override)
            case "start_one_shot":
                departure: time | None = data.get("departure_time")
                await center.async_run(lambda now: engine.start_one_shot(now, departure))
            case "cancel_one_shot":
                await center.async_run(engine.cancel_one_shot)
            case "vehicle_wakeup":
                await center.async_run(lambda now: engine.wakeup(now, CommandKind.OVMS_WAKEUP))
            case "cp_wakeup":
                await center.async_run(lambda now: engine.wakeup(now, CommandKind.CP_PULSE))
            case "reset_error":
                await center.async_run(engine.reset)
            case "start_climate":
                await center.async_run(lambda now: engine.start_climate(now, data["minutes"]))
            case "stop_climate":
                await center.async_run(engine.stop_climate)
            case "add_external_charge":
                charge = ExternalCharge(
                    id=data.get("id") or uuid.uuid4().hex[:10],
                    date=data["date"], source=data["source"], energy_kwh=data["energy_kwh"],
                    cost_eur=data.get("cost_eur"), price_eur_kwh=data.get("price_eur_kwh"),
                    odometer_km=data.get("odometer_km"), soc_before=data.get("soc_before"),
                    soc_after=data.get("soc_after"), provider=data.get("provider"),
                    note=data.get("note"))
                center.monitor.add_external(charge)
                center.monitor_changed()
                return {"id": charge.id}
            case "delete_external_charge":
                if not center.monitor.delete_external(data["id"]):
                    raise ServiceValidationError(f"Fremdladung {data['id']} nicht gefunden")
                center.monitor_changed()
            case "add_manual_odometer":
                at = _aware(data["at"]) if data.get("at") else dt_util.utcnow()
                center.monitor.add_odometer(at, data["odometer_km"])
                center.monitor_changed()
            case "set_plans":
                plans = [WeeklySchedule.from_dict(p) for p in data["plans"]]
                await center.async_run(lambda now: engine.set_plans(now, plans))
            case "export":
                return await _export(center, data)
            case "start_replay":
                result = await center.async_replay(
                    dataset=data.get("dataset"), file=data.get("file"), tick_s=data["tick_s"])
                return {k: result[k] for k in ("name", "ticks", "agreement", "matches",
                                               "mismatches", "states")}
            case "stop_replay":
                await center.async_stop_replay()
            case "create_replay_dataset":
                return await center.async_create_dataset(
                    _aware(data["start"]), _aware(data["end"]), data["name"],
                    data["poll_interval_s"])
    except (ValueError, FileNotFoundError) as err:
        raise ServiceValidationError(str(err)) from err
    return None


async def _export(center: ChargingCenter, data: dict[str, Any]) -> dict[str, Any]:
    items = rows(center.monitor, center.settings, data["dataset"], data.get("start"),
                 data.get("end"))
    text = render(items, data["format"])
    stamp = dt_util.now(center.tz).strftime("%Y%m%d-%H%M%S")
    target = center.data_dir / "export" / f"{data['dataset']}-{stamp}.{data['format']}"

    def write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    await center.hass.async_add_executor_job(write)
    return {"file": str(target), "rows": len(items)}


def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "start_charging"):
        return

    async def handler(call: ServiceCall) -> ServiceResponse:
        return await _handle(hass, call)

    for name, schema in SCHEMAS.items():
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema,
            supports_response=SupportsResponse.OPTIONAL if name in RESPONSE
            else SupportsResponse.NONE,
        )


def async_unregister_services(hass: HomeAssistant) -> None:
    for name in SCHEMAS:
        hass.services.async_remove(DOMAIN, name)
