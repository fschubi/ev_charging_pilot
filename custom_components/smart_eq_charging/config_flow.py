"""Config flow (entities) and options flow (plan, vehicle, executor, costs)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
    CONF_PRICE_EUR_KWH,
    CONF_READY_BUFFER_MIN,
    CONF_SHELLY_HOST,
    CONF_START_DETECTION_WAIT_S,
    CONF_TOTAL_ENERGY,
    CONF_VEHICLE_CHARGER_KW,
    CONF_WEEKDAYS,
    CP_PULSE_MAX_S,
    CP_PULSE_MIN_S,
    DEFAULTS,
    DOMAIN,
    NAME,
)
from .core.planner import WEEKDAYS


def _entity(domain: str | list[str]) -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


def _number(minimum: float, maximum: float, step: float = 1, unit: str | None = None):
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _optional(key: str, current: dict[str, Any]) -> vol.Optional:
    """Optional field that keeps its current value as suggestion (and can be cleared)."""
    value = current.get(key)
    return vol.Optional(key, description={"suggested_value": value} if value else None)


def _devices_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_CHARGER_ENABLE, default=current.get(CONF_CHARGER_ENABLE, vol.UNDEFINED)):
            _entity("switch"),
        vol.Required(CONF_CABLE_CONNECTED,
                     default=current.get(CONF_CABLE_CONNECTED, vol.UNDEFINED)):
            _entity("binary_sensor"),
        vol.Required(CONF_CHARGE_POWER, default=current.get(CONF_CHARGE_POWER, vol.UNDEFINED)):
            _entity("sensor"),
        vol.Required(CONF_TOTAL_ENERGY, default=current.get(CONF_TOTAL_ENERGY, vol.UNDEFINED)):
            _entity("sensor"),
        _optional(CONF_CHARGER_STATUS, current): _entity("sensor"),
        _optional(CONF_INTERNAL_SCHEDULE, current): _entity("switch"),
        _optional(CONF_CP_RELAY, current): _entity("switch"),
        _optional(CONF_SHELLY_HOST, current): selector.TextSelector(),
        _optional(CONF_OVMS_SOC, current): _entity("sensor"),
        _optional(CONF_OVMS_CHARGING, current): _entity("binary_sensor"),
        _optional(CONF_NOTIFY_SERVICE, current): selector.TextSelector(),
    })


class SmartEqChargingConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(step_id="user", data_schema=_devices_schema({}))

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data=user_input)
        return self.async_show_form(step_id="reconfigure",
                                    data_schema=_devices_schema(dict(entry.data)))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SmartEqChargingOptionsFlow()


class SmartEqChargingOptionsFlow(OptionsFlow):
    """Two pages: the plan, then technical parameters."""

    def __init__(self) -> None:
        self._collected: dict[str, Any] = {}

    def _current(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._collected.update(user_input)
            return await self.async_step_technical()
        c = self._current()
        schema = vol.Schema({
            vol.Required(CONF_PLAN_ENABLED, default=c[CONF_PLAN_ENABLED]):
                selector.BooleanSelector(),
            vol.Required(CONF_WEEKDAYS, default=c[CONF_WEEKDAYS]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=list(WEEKDAYS), multiple=True,
                                              translation_key=CONF_WEEKDAYS)),
            vol.Required(CONF_MODE, default=c[CONF_MODE]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=["departure_based", "fixed_start"],
                                              translation_key=CONF_MODE)),
            vol.Required(CONF_DEPARTURE_TIME, default=c[CONF_DEPARTURE_TIME]):
                selector.TimeSelector(),
            vol.Required(CONF_CHARGE_START_TIME, default=c[CONF_CHARGE_START_TIME]):
                selector.TimeSelector(),
            vol.Required(CONF_READY_BUFFER_MIN, default=c[CONF_READY_BUFFER_MIN]):
                _number(0, 180, unit="min"),
            vol.Required(CONF_MIN_SOC, default=c[CONF_MIN_SOC]): _number(10, 100, unit="%"),
            vol.Required(CONF_PREFERRED_SOC, default=c[CONF_PREFERRED_SOC]):
                _number(10, 100, unit="%"),
        })
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_technical(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if self._collected[CONF_PREFERRED_SOC] < self._collected[CONF_MIN_SOC]:
                errors["base"] = "preferred_below_minimum"
            else:
                return self.async_create_entry(data={**self._collected, **user_input})
        c = {**self._current(), **(user_input or {})}
        schema = vol.Schema({
            vol.Required(CONF_CAPACITY_KWH, default=c[CONF_CAPACITY_KWH]):
                _number(5, 30, 0.1, "kWh"),
            vol.Required(CONF_EFFICIENCY, default=c[CONF_EFFICIENCY]): _number(0.5, 1, 0.01),
            vol.Required(CONF_VEHICLE_CHARGER_KW, default=c[CONF_VEHICLE_CHARGER_KW]):
                _number(1, 22, 0.1, "kW"),
            vol.Required(CONF_GRID_LIMIT_KW, default=c[CONF_GRID_LIMIT_KW]):
                _number(0, 22, 0.1, "kW"),
            vol.Required(CONF_POWER_THRESHOLD_W, default=c[CONF_POWER_THRESHOLD_W]):
                _number(50, 3000, 10, "W"),
            vol.Required(CONF_START_DETECTION_WAIT_S, default=c[CONF_START_DETECTION_WAIT_S]):
                _number(15, 600, unit="s"),
            vol.Required(CONF_MIN_SWITCH_INTERVAL_S, default=c[CONF_MIN_SWITCH_INTERVAL_S]):
                _number(30, 900, unit="s"),
            vol.Required(CONF_CP_PULSE_S, default=c[CONF_CP_PULSE_S]):
                _number(CP_PULSE_MIN_S, CP_PULSE_MAX_S, unit="s"),
            vol.Required(CONF_CP_FAILSAFE_VERIFIED, default=c[CONF_CP_FAILSAFE_VERIFIED]):
                selector.BooleanSelector(),
            vol.Optional(CONF_FINISHED_STATUSES, default=c[CONF_FINISHED_STATUSES]):
                selector.TextSelector(),
            vol.Required(CONF_PRICE_EUR_KWH, default=c[CONF_PRICE_EUR_KWH]):
                _number(0, 2, 0.001, "€/kWh"),
        })
        return self.async_show_form(step_id="technical", data_schema=schema, errors=errors)
