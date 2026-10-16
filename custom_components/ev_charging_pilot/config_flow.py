"""Config flow (§13.1) and options flow (§13.2).

Setup asks only for entities and basics, in five small steps; every time
constant and threshold lives in the options flow with provisional defaults
that Phase 0 overwrites.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_NOTIFY_SERVICE,
    CONF_OVMS_COMMAND_SCRIPT,
    CONF_OVMS_COMMAND_TOPIC,
    CONF_SHELLY_HOST,
    CONF_VEHICLE_NAME,
    DEFAULT_VEHICLE_NAME,
    DOMAIN,
    HALO_OPTIONAL,
    HALO_REQUIRED,
    INPUT_DOMAINS,
    OVMS_INPUTS,
    title_for,
)
from .core.inputs import Inp
from .core.settings import (
    DEFAULT_OPTIONS,
    OPT_CAPACITY_KWH,
    OPT_CLIMATE_AFTER_TARGET,
    OPT_CLIMATE_COLD_BELOW,
    OPT_CLIMATE_COLD_MIN,
    OPT_CLIMATE_COOL_BELOW,
    OPT_CLIMATE_COOL_MIN,
    OPT_CLIMATE_ENABLED,
    OPT_CLIMATE_MIN_SOC,
    OPT_CLIMATE_VERY_COLD_BELOW,
    OPT_CLIMATE_VERY_COLD_MIN,
    OPT_CLIMATE_WARM_ABOVE,
    OPT_CLIMATE_WARM_MIN,
    OPT_CONFIRM_TIMEOUT_S,
    OPT_CP_FAILSAFE_VERIFIED,
    OPT_CP_FALLBACK_ENABLED,
    OPT_CP_MASK_GRACE_S,
    OPT_CP_PULSE_S,
    OPT_EFFICIENCY,
    OPT_EVENT_RETENTION_DAYS,
    OPT_EXTERNAL_DETECTION,
    OPT_EXTERNAL_MIN_KWH,
    OPT_EXTERNAL_PRICE,
    OPT_EXTERNAL_SOC_JUMP,
    OPT_FINISHED_STATUSES,
    OPT_GRID_LIMIT_KW,
    OPT_HV_CYCLES_WARN_PER_DAY,
    OPT_INTERVAL_MIN,
    OPT_LOSS_TIMEOUT_S,
    OPT_MAX_AGE_HALO_ENERGY_S,
    OPT_MAX_AGE_HALO_POWER_S,
    OPT_MAX_AGE_ODOMETER_S,
    OPT_MAX_AGE_SOC_S,
    OPT_MAX_AGE_TEMPERATURE_S,
    OPT_MAX_AGE_VEHICLE_CHARGING_S,
    OPT_MAX_CP_ATTEMPTS,
    OPT_MAX_OVMS_ATTEMPTS,
    OPT_MAX_POWER_KW,
    OPT_MIN_GAP_WAKEUPS_S,
    OPT_MIN_SWITCH_INTERVAL_S,
    OPT_MODE,
    OPT_NOTIFY_CP,
    OPT_NOTIFY_EXTERNAL,
    OPT_NOTIFY_HEALTH,
    OPT_NOTIFY_HV_CYCLES,
    OPT_NOTIFY_PLAN_INFEASIBLE,
    OPT_NOTIFY_PLUG_IN,
    OPT_NOTIFY_PLUG_REMINDER,
    OPT_NOTIFY_REPORT,
    OPT_NOTIFY_START_FAILED,
    OPT_ODOMETER_SOURCE,
    OPT_OVMS_CLIMATE_COMMAND,
    OPT_OVMS_CLIMATE_STOP_COMMAND,
    OPT_OVMS_ENABLED,
    OPT_OVMS_WAIT_S,
    OPT_OVMS_WAKEUP_COMMAND,
    OPT_PLUG_REMINDER_TIME,
    OPT_POST_CP_WAIT_S,
    OPT_POWER_THRESHOLD_W,
    OPT_PRICE_BLOCKS,
    OPT_PRICE_ENTITY,
    OPT_PRICE_HISTORY,
    OPT_PRICE_OPTIMIZATION,
    OPT_PRICE_SOURCE,
    OPT_REPORT_AUTO,
    OPT_STABLE_MIN_S,
    OPT_STABLE_SAMPLES,
    OPT_START_DETECTION_WAIT_S,
    OPT_TRIP_MERGE_GAP_MIN,
    OPT_VEHICLE_CHARGER_KW,
    ClimateAfterTarget,
    OdometerSource,
    PriceSource,
    RunMode,
)
from .discovery import async_discover

OPT_PRICE = "price_eur_kwh"
OPT_PRICE_VALID_FROM = "price_valid_from"
OPTION_STEPS = ["charging", "wakeup", "planning", "prices", "climate", "quality",
                "notifications", "monitor", "external", "ovms_commands"]
OVMS_KEYS = (*(i.value for i in OVMS_INPUTS), Inp.OUTSIDE_TEMP.value, Inp.WEATHER.value,
             CONF_OVMS_COMMAND_TOPIC, CONF_OVMS_COMMAND_SCRIPT)

BOOL = selector.BooleanSelector()
TEXT = selector.TextSelector()


def _entity(domain: str | list[str]) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


def _number(minimum: float, maximum: float, step: float = 1, unit: str | None = None):
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _select(options: list[str], key: str) -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(
        options=options, translation_key=key, mode=selector.SelectSelectorMode.DROPDOWN))


def _optional(key: str, current: dict[str, Any]) -> vol.Optional:
    """Optional field that keeps its current value as suggestion (and can be cleared)."""
    value = current.get(key)
    return vol.Optional(key, description={"suggested_value": value} if value else None)


def _required(key: str, current: dict[str, Any]) -> vol.Required:
    return vol.Required(key, default=current.get(key, vol.UNDEFINED))


def _domain(inp: Inp) -> str | list[str]:
    return INPUT_DOMAINS.get(inp, "sensor")


def halo_schema(c: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {_required(i.value, c): _entity(_domain(i)) for i in HALO_REQUIRED}
    fields |= {_optional(i.value, c): _entity(_domain(i)) for i in HALO_OPTIONAL}
    return vol.Schema(fields)


def shelly_schema(c: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        _optional(Inp.CP_RELAY.value, c): _entity("switch"),
        _optional(CONF_SHELLY_HOST, c): TEXT,
    })


def notify_schema(c: dict[str, Any], services: list[str]) -> vol.Schema:
    return vol.Schema({
        _optional(CONF_NOTIFY_SERVICE, c): selector.SelectSelector(selector.SelectSelectorConfig(
            options=services, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
    })


def ovms_schema(c: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {_optional(i.value, c): _entity(_domain(i)) for i in OVMS_INPUTS}
    fields |= {
        _optional(Inp.OUTSIDE_TEMP.value, c): _entity("sensor"),
        _optional(Inp.WEATHER.value, c): _entity("weather"),
        _optional(CONF_OVMS_COMMAND_TOPIC, c): TEXT,
        _optional(CONF_OVMS_COMMAND_SCRIPT, c): _entity("script"),
    }
    return vol.Schema(fields)


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v not in (None, "")}


class EvChargingPilotConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._reconfigure = False
        self._found: dict[str, Any] = {}

    def _placeholders(self, keys) -> dict[str, str]:
        hits = [k for k in keys if k in self._found]
        text = (f"{len(hits)} von {len(list(keys))} Feldern wurden automatisch erkannt – "
                "bitte kurz prüfen." if hits else
                "Nichts automatisch erkannt – bitte die Entitäten auswählen.")
        return {"found": text}

    def _notify_services(self) -> list[str]:
        services = self.hass.services.async_services().get("notify", {})
        return sorted(f"notify.{name}" for name in services
                      if name not in ("notify", "persistent_notification", "send_message"))

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            vehicle = str(user_input[CONF_VEHICLE_NAME]).strip()[:40] or DEFAULT_VEHICLE_NAME
            self._options[CONF_VEHICLE_NAME] = vehicle
            dry = user_input.get("dry_run", True)
            self._options[OPT_MODE] = (RunMode.DRY_RUN if dry else RunMode.LIVE).value
            # Pre-fill every field the discovery found; the user confirms them.
            self._found = async_discover(self.hass)
            self._data = {**self._found, **self._data}
            return await self.async_step_halo()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_VEHICLE_NAME, default=DEFAULT_VEHICLE_NAME): TEXT,
            vol.Required("dry_run", default=True): BOOL,
        }))

    async def async_step_halo(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._merge(user_input, (i.value for i in (*HALO_REQUIRED, *HALO_OPTIONAL)))
            return await self.async_step_shelly()
        return self.async_show_form(
            step_id="halo", data_schema=halo_schema(self._data),
            description_placeholders=self._placeholders(
                [i.value for i in (*HALO_REQUIRED, *HALO_OPTIONAL)]))

    async def async_step_shelly(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_SHELLY_HOST) and not user_input.get(Inp.CP_RELAY.value):
                errors["base"] = "host_without_relay"
            else:
                self._merge(user_input, (Inp.CP_RELAY.value, CONF_SHELLY_HOST))
                return await self.async_step_notify()
        return self.async_show_form(step_id="shelly", data_schema=shelly_schema(self._data),
                                    errors=errors, description_placeholders=self._placeholders(
                                        [Inp.CP_RELAY.value, CONF_SHELLY_HOST]))

    async def async_step_notify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._merge(user_input, (CONF_NOTIFY_SERVICE,))
            return await self.async_step_ovms()
        return self.async_show_form(
            step_id="notify", data_schema=notify_schema(self._data, self._notify_services()),
            description_placeholders=self._placeholders([CONF_NOTIFY_SERVICE]))

    async def async_step_ovms(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._merge(user_input, OVMS_KEYS)
            data = _clean(self._data)
            if self._reconfigure:
                entry = self._get_reconfigure_entry()
                return self.async_update_reload_and_abort(
                    entry, data=data, title=title_for(entry.options.get(CONF_VEHICLE_NAME)))
            return self.async_create_entry(
                title=title_for(self._options.get(CONF_VEHICLE_NAME)), data=data,
                options=self._options)
        return self.async_show_form(step_id="ovms", data_schema=ovms_schema(self._data),
                                    description_placeholders=self._placeholders(OVMS_KEYS))

    def _merge(self, user_input: dict[str, Any], keys) -> None:
        """Cleared optional fields must be removed, not kept from before."""
        for key in keys:
            self._data.pop(key, None)
        self._data.update(_clean(user_input))

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._reconfigure = True
        self._data = dict(self._get_reconfigure_entry().data)
        # Reconfigure keeps what is set and only fills empty fields (e.g. OVMS added later).
        self._found = async_discover(self.hass)
        self._data = {**self._found, **self._data}
        return await self.async_step_halo()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EvChargingPilotOptionsFlow()


class EvChargingPilotOptionsFlow(OptionsFlow):
    """A menu of the §13.2 groups; each page saves on its own."""

    def _current(self) -> dict[str, Any]:
        return {**DEFAULT_OPTIONS, **self.config_entry.options}

    def _save(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **user_input})

    def _form(self, step_id: str, fields: dict[Any, Any]) -> ConfigFlowResult:
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema(fields))

    def _d(self, key: str) -> vol.Required:
        return vol.Required(key, default=self._current()[key])

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=OPTION_STEPS)

    async def async_step_charging(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = self._d
        return self._form("charging", {
            d(OPT_MODE): _select([m.value for m in RunMode], OPT_MODE),
            d(OPT_POWER_THRESHOLD_W): _number(50, 3000, 10, "W"),
            d(OPT_STABLE_SAMPLES): _number(1, 10),
            d(OPT_STABLE_MIN_S): _number(0, 600, unit="s"),
            d(OPT_LOSS_TIMEOUT_S): _number(30, 1800, unit="s"),
            d(OPT_MIN_SWITCH_INTERVAL_S): _number(30, 900, unit="s"),
            d(OPT_CONFIRM_TIMEOUT_S): _number(15, 600, unit="s"),
            vol.Optional(OPT_FINISHED_STATUSES,
                         default=self._current()[OPT_FINISHED_STATUSES]): TEXT,
        })

    async def async_step_wakeup(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = self._d
        return self._form("wakeup", {
            d(OPT_START_DETECTION_WAIT_S): _number(15, 900, unit="s"),
            d(OPT_OVMS_ENABLED): BOOL,
            d(OPT_OVMS_WAIT_S): _number(10, 600, unit="s"),
            d(OPT_CP_FALLBACK_ENABLED): BOOL,
            d(OPT_POST_CP_WAIT_S): _number(15, 900, unit="s"),
            d(OPT_MAX_OVMS_ATTEMPTS): _number(0, 3),
            d(OPT_MAX_CP_ATTEMPTS): _number(0, 3),
            d(OPT_MIN_GAP_WAKEUPS_S): _number(30, 1800, unit="s"),
            d(OPT_CP_PULSE_S): _number(5, 15, unit="s"),
            d(OPT_CP_MASK_GRACE_S): _number(0, 300, unit="s"),
            d(OPT_CP_FAILSAFE_VERIFIED): BOOL,
        })

    async def async_step_planning(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = self._d
        return self._form("planning", {
            d(OPT_CAPACITY_KWH): _number(5, 30, 0.1, "kWh"),
            d(OPT_EFFICIENCY): _number(0.5, 1, 0.01),
            d(OPT_MAX_POWER_KW): _number(1, 22, 0.1, "kW"),
            d(OPT_VEHICLE_CHARGER_KW): _number(1, 22, 0.1, "kW"),
            d(OPT_GRID_LIMIT_KW): _number(0, 22, 0.1, "kW"),
        })

    async def async_step_climate(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = self._d
        return self._form("climate", {
            d(OPT_CLIMATE_ENABLED): BOOL,
            d(OPT_CLIMATE_MIN_SOC): _number(20, 100, unit="%"),
            d(OPT_CLIMATE_AFTER_TARGET): _select([c.value for c in ClimateAfterTarget],
                                                 OPT_CLIMATE_AFTER_TARGET),
            d(OPT_CLIMATE_VERY_COLD_BELOW): _number(-20, 30, 0.5, "°C"),
            d(OPT_CLIMATE_VERY_COLD_MIN): _number(0, 15, unit="min"),
            d(OPT_CLIMATE_COLD_BELOW): _number(-20, 30, 0.5, "°C"),
            d(OPT_CLIMATE_COLD_MIN): _number(0, 15, unit="min"),
            d(OPT_CLIMATE_COOL_BELOW): _number(-20, 30, 0.5, "°C"),
            d(OPT_CLIMATE_COOL_MIN): _number(0, 15, unit="min"),
            d(OPT_CLIMATE_WARM_ABOVE): _number(10, 45, 0.5, "°C"),
            d(OPT_CLIMATE_WARM_MIN): _number(0, 15, unit="min"),
        })

    async def async_step_quality(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = self._d
        return self._form("quality", {
            d(OPT_MAX_AGE_HALO_POWER_S): _number(30, 3600, unit="s"),
            d(OPT_MAX_AGE_HALO_ENERGY_S): _number(60, 7200, unit="s"),
            d(OPT_MAX_AGE_VEHICLE_CHARGING_S): _number(30, 3600, unit="s"),
            d(OPT_MAX_AGE_SOC_S): _number(60, 7200, unit="s"),
            d(OPT_MAX_AGE_ODOMETER_S): _number(60, 86400, unit="s"),
            d(OPT_MAX_AGE_TEMPERATURE_S): _number(60, 7200, unit="s"),
        })

    async def async_step_notifications(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = self._d
        return self._form("notifications", {
            d(OPT_PLUG_REMINDER_TIME): selector.TimeSelector(),
            d(OPT_NOTIFY_START_FAILED): BOOL,
            d(OPT_NOTIFY_CP): BOOL,
            d(OPT_NOTIFY_PLAN_INFEASIBLE): BOOL,
            d(OPT_NOTIFY_PLUG_REMINDER): BOOL,
            d(OPT_NOTIFY_HEALTH): BOOL,
            d(OPT_NOTIFY_HV_CYCLES): BOOL,
            d(OPT_NOTIFY_PLUG_IN): BOOL,
            d(OPT_NOTIFY_EXTERNAL): BOOL,
            d(OPT_REPORT_AUTO): BOOL,
            d(OPT_NOTIFY_REPORT): BOOL,
        })

    async def async_step_prices(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input.setdefault(OPT_PRICE_ENTITY, "")
            if user_input[OPT_PRICE_SOURCE] == PriceSource.ENTITY and \
                    not user_input[OPT_PRICE_ENTITY]:
                errors["base"] = "price_entity_missing"
            elif user_input[OPT_PRICE_SOURCE] == PriceSource.TIBBER and \
                    not self.hass.services.has_service("tibber", "get_prices"):
                errors["base"] = "tibber_missing"
            else:
                return self._save(user_input)
        d = self._d
        c = self._current()
        return self.async_show_form(step_id="prices", errors=errors, data_schema=vol.Schema({
            d(OPT_PRICE_SOURCE): _select([p.value for p in PriceSource], OPT_PRICE_SOURCE),
            _optional(OPT_PRICE_ENTITY, c): _entity("sensor"),
            d(OPT_PRICE_OPTIMIZATION): BOOL,
            d(OPT_PRICE_BLOCKS): _number(1, 2),
        }))

    async def async_step_external(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        d = self._d
        return self._form("external", {
            d(OPT_EXTERNAL_DETECTION): BOOL,
            d(OPT_EXTERNAL_MIN_KWH): _number(0.2, 20, 0.1, "kWh"),
            d(OPT_EXTERNAL_SOC_JUMP): _number(2, 50, unit="%"),
            d(OPT_EXTERNAL_PRICE): _number(0, 2, 0.01, "€/kWh"),
        })

    async def async_step_monitor(self, user_input=None) -> ConfigFlowResult:
        history = list(self._current()[OPT_PRICE_HISTORY])
        if user_input is not None:
            price = float(user_input.pop(OPT_PRICE))
            valid_from = str(user_input.pop(OPT_PRICE_VALID_FROM))
            last = history[-1]
            if price != float(last["eur_per_kwh"]) or valid_from != str(last["valid_from"]):
                # A new price never rewrites old months (§11): add an entry, keep the rest.
                history = [p for p in history if str(p["valid_from"]) != valid_from]
                history.append({"valid_from": valid_from, "eur_per_kwh": price})
                history.sort(key=lambda p: str(p["valid_from"]))
            return self._save({**user_input, OPT_PRICE_HISTORY: history})
        d = self._d
        return self._form("monitor", {
            d(OPT_ODOMETER_SOURCE): _select([o.value for o in OdometerSource],
                                            OPT_ODOMETER_SOURCE),
            d(OPT_TRIP_MERGE_GAP_MIN): _number(1, 120, unit="min"),
            d(OPT_EVENT_RETENTION_DAYS): _number(7, 730, unit="d"),
            d(OPT_HV_CYCLES_WARN_PER_DAY): _number(1, 100),
            d(OPT_INTERVAL_MIN): _number(5, 60, 5, "min"),
            vol.Required(OPT_PRICE, default=float(history[-1]["eur_per_kwh"])):
                _number(0, 2, 0.001, "€/kWh"),
            vol.Required(OPT_PRICE_VALID_FROM,
                         default=str(history[-1]["valid_from"] or date.today().isoformat())):
                selector.DateSelector(),
        })

    async def async_step_ovms_commands(self, user_input=None) -> ConfigFlowResult:
        keys = (OPT_OVMS_WAKEUP_COMMAND, OPT_OVMS_CLIMATE_COMMAND, OPT_OVMS_CLIMATE_STOP_COMMAND)
        if user_input is not None:
            return self._save({k: user_input.get(k, "") for k in keys})
        c = self._current()
        return self._form("ovms_commands", {_optional(k, c): TEXT for k in keys})
