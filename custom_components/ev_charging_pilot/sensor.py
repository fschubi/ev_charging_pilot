"""Sensors (§12.1): status, charging, vehicle, energy & costs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import ChargingConfigEntry
from .coordinator import ChargingCenter
from .core.executor import ExecState
from .core.health import HealthStatus
from .core.inputs import Inp
from .core.model import Quality, Reason
from .core.settings import RunMode
from .core.summary import summary
from .entity import ChargingEntity

EUR = "EUR"
KWH_100KM = "kWh/100 km"
EUR_100KM = "EUR/100 km"


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _num(c: ChargingCenter, inp: Inp) -> float | None:
    value = c.engine.values.get(inp)
    if value is None or value.normalized is None or value.quality in (
            Quality.UNAVAILABLE, Quality.INVALID):
        return None
    return round(float(value.normalized), 2)


def _quality(c: ChargingCenter, inp: Inp) -> dict[str, Any]:
    value = c.engine.values.get(inp)
    if value is None:
        return {}
    return {"quality": str(value.quality), "source": value.source,
            "updated_at": _iso(value.updated_at)}


def _window(c: ChargingCenter):
    return c.engine.next_window


def _next_start(c: ChargingCenter) -> datetime | None:
    """The next moment charging begins – never one that already passed.

    A started window keeps its (locked) start; once its last price block is over
    nothing more is planned for it (field 18.10.2026: "charges from 06:00" at 15:50).
    """
    window, now = _window(c), dt_util.utcnow()
    if window is None:
        return None
    if window.start > now:
        return window.start
    return next((a if a > now else now for a, b in window.blocks if b > now), None)


def _status(c: ChargingCenter) -> dict[str, Any]:
    return summary(c.engine, dt_util.utcnow(), c.mode is RunMode.LIVE)


def _climate_attributes(c: ChargingCenter) -> dict[str, Any]:
    plan = c.engine.climate_plan
    return {
        "climate_start": _iso(plan.start_at) if plan else None,
        "climate_minutes": plan.duration_min if plan else None,
        "climate_phase": c.engine.climate_phase,
        "climate_blocked": c.engine.climate_blocked,
    }


def _stat(period: str, key: str) -> Callable[[ChargingCenter], Any]:
    return lambda c: (c.statistics.get(period) or {}).get(key)


@dataclass(frozen=True, kw_only=True)
class ChargingSensorDescription(SensorEntityDescription):
    value: Callable[[ChargingCenter], Any]
    attributes: Callable[[ChargingCenter], dict[str, Any]] | None = None
    requires: Inp | None = None
    reset: str | None = None  # "month" | "year" | "session"


def _vehicle(key: str, inp: Inp, **kwargs: Any) -> ChargingSensorDescription:
    return ChargingSensorDescription(
        key=key, requires=inp, value=lambda c: _num(c, inp),
        attributes=lambda c: _quality(c, inp), **kwargs)


def _period(period: str, key: str, stat: str, **kwargs: Any) -> ChargingSensorDescription:
    # last_reset is only valid for state_class "total" (ratios have none).
    reset = period if kwargs.get("state_class") is SensorStateClass.TOTAL else None
    return ChargingSensorDescription(
        key=f"{period}_{key}", reset=reset, value=_stat(period, stat),
        attributes=lambda c: {"quality": (c.statistics.get(period) or {}).get("quality"),
                              "complete": (c.statistics.get(period) or {}).get("complete")},
        **kwargs)


SENSORS: tuple[ChargingSensorDescription, ...] = (
    # --- Status
    ChargingSensorDescription(
        key="status",
        value=lambda c: _status(c)["headline"][:255],
        attributes=lambda c: {
            "detail": (status := _status(c))["detail"], "tone": status["tone"],
            **_climate_attributes(c)},
    ),
    ChargingSensorDescription(
        key="executor_state",
        device_class=SensorDeviceClass.ENUM,
        options=[s.lower() for s in ExecState],
        value=lambda c: c.engine.executor.state.lower() if c.engine.executor.state else None,
        attributes=lambda c: {
            "since": _iso(c.engine.executor.state_since),
            "failure_code": c.engine.executor.failure_code,
            "session_id": c.engine.executor.session_id,
            "mode": str(c.mode),
        },
    ),
    ChargingSensorDescription(
        key="desired_reason",
        device_class=SensorDeviceClass.ENUM,
        options=[r.value for r in Reason],
        value=lambda c: c.engine.desired.reason.value if c.engine.desired else None,
        attributes=lambda c: {
            "charger_enabled": c.engine.desired.charger_enabled if c.engine.desired else None,
            "source_id": c.engine.desired.source_id if c.engine.desired else None,
            "valid_until": _iso(c.engine.desired.valid_until) if c.engine.desired else None,
            "climate": c.engine.desired.climate.duration_min
            if c.engine.desired and c.engine.desired.climate else None,
        },
    ),
    ChargingSensorDescription(
        key="system_health",
        device_class=SensorDeviceClass.ENUM,
        options=[h.lower() for h in HealthStatus],
        value=lambda c: c.engine.health.status.lower(),
        attributes=lambda c: {
            "reasons": list(c.engine.health.reasons),
            "shelly_config_ok": c.engine.shelly_config_ok,
        },
    ),
    ChargingSensorDescription(
        key="last_event",
        entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False,
        value=lambda c: c.events[-1]["code"] if c.events else None,
        attributes=lambda c: dict(c.events[-1]) if c.events else {},
    ),
    ChargingSensorDescription(
        key="last_charge_result",
        value=lambda c: ("ok" if c.engine.last_result["success"]
                         else c.engine.last_result["failure_code"])
        if c.engine.last_result else None,
        attributes=lambda c: dict(c.engine.last_result or {}),
    ),
    # --- Laden
    ChargingSensorDescription(
        key="charge_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value=lambda c: _num(c, Inp.CHARGE_POWER),
        attributes=lambda c: _quality(c, Inp.CHARGE_POWER),
    ),
    ChargingSensorDescription(
        key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        reset="session",
        value=lambda c: round(c.engine.sessions.session_energy_kwh, 3)
        if c.engine.sessions.session_energy_kwh is not None else None,
        attributes=lambda c: {"session_id": c.engine.sessions.open.session_id}
        if c.engine.sessions.open else {},
    ),
    ChargingSensorDescription(
        key="next_charge_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=_next_start,
        attributes=lambda c: {
            "plan": _window(c).name if _window(c) else None,
            "fallback_without_soc": _window(c).fallback_without_soc if _window(c) else None,
        },
    ),
    ChargingSensorDescription(
        key="next_departure",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda c: _window(c).departure if _window(c) else None,
    ),
    ChargingSensorDescription(
        key="expected_departure_soc",
        native_unit_of_measurement=PERCENTAGE,
        value=lambda c: _window(c).estimate.expected_soc_at_departure if _window(c) else None,
        attributes=lambda c: {
            "estimate": True,
            "minimum_reachable": _window(c).estimate.minimum_reachable if _window(c) else None,
            "preferred_reachable": _window(c).estimate.preferred_reachable
            if _window(c) else None,
            "needed_kwh": _window(c).estimate.needed_kwh if _window(c) else None,
        },
    ),
    ChargingSensorDescription(
        key="estimated_finish",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda c: _window(c).estimate.finish_at if _window(c) else None,
        attributes=lambda c: {"estimate": True},
    ),
    ChargingSensorDescription(
        key="current_price",
        native_unit_of_measurement="EUR/kWh",
        suggested_display_precision=3,
        value=lambda c: round(c.engine.price_at(dt_util.utcnow()), 4),
        attributes=lambda c: {
            "source": str(c.settings.price_source),
            "dynamic": c.engine.dynamic_prices,
            "last_update": _iso(c.price_fetcher.last_update),
            "error": c.price_fetcher.last_error,
        },
    ),
    ChargingSensorDescription(
        key="next_charge_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=EUR,
        value=lambda c: _window(c).estimate.cost_eur if _window(c) else None,
        attributes=lambda c: {
            "estimate": True,
            "price_optimized": _window(c).price_optimized if _window(c) else None,
            "blocks": [[_iso(a), _iso(b)] for a, b in _window(c).blocks] if _window(c) else [],
        },
    ),
    # --- Fahrzeug (ab v0.4, nur wenn gemappt)
    _vehicle("soc", Inp.OVMS_SOC, device_class=SensorDeviceClass.BATTERY,
             state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=PERCENTAGE),
    _vehicle("soh", Inp.OVMS_SOH, state_class=SensorStateClass.MEASUREMENT,
             native_unit_of_measurement=PERCENTAGE),
    _vehicle("range", Inp.OVMS_RANGE, device_class=SensorDeviceClass.DISTANCE,
             state_class=SensorStateClass.MEASUREMENT,
             native_unit_of_measurement=UnitOfLength.KILOMETERS),
    _vehicle("odometer", Inp.OVMS_ODOMETER, device_class=SensorDeviceClass.DISTANCE,
             state_class=SensorStateClass.TOTAL_INCREASING,
             native_unit_of_measurement=UnitOfLength.KILOMETERS),
    _vehicle("battery_temperature", Inp.OVMS_BATTERY_TEMP,
             device_class=SensorDeviceClass.TEMPERATURE,
             state_class=SensorStateClass.MEASUREMENT,
             native_unit_of_measurement=UnitOfTemperature.CELSIUS),
    ChargingSensorDescription(
        key="hv_contactor_cycles",
        requires=Inp.OVMS_HV_CYCLES,
        # The OVMS integration exposes consumed (rising) or remaining (falling) cycles –
        # TOTAL_INCREASING would read every falling step as a meter reset.
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda c: _num(c, Inp.OVMS_HV_CYCLES),
        attributes=lambda c: {**_quality(c, Inp.OVMS_HV_CYCLES), "today": c.engine.hv.today},
    ),
    # --- Energie & Kosten
    ChargingSensorDescription(
        key="home_energy_total",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value=lambda c: _num(c, Inp.TOTAL_ENERGY),
        attributes=lambda c: _quality(c, Inp.TOTAL_ENERGY),
    ),
    *(
        item
        for period in ("month", "year")
        for item in (
            _period(period, "home_energy", "home_energy_kwh",
                    device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL,
                    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR),
            _period(period, "external_energy", "external_energy_kwh",
                    device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL,
                    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR),
            _period(period, "distance", "distance_km",
                    device_class=SensorDeviceClass.DISTANCE, state_class=SensorStateClass.TOTAL,
                    native_unit_of_measurement=UnitOfLength.KILOMETERS),
            _period(period, "cost", "cost_eur", device_class=SensorDeviceClass.MONETARY,
                    state_class=SensorStateClass.TOTAL, native_unit_of_measurement=EUR),
            _period(period, "cost_per_100km", "cost_per_100km_eur",
                    native_unit_of_measurement=EUR_100KM),
            _period(period, "grid_consumption", "grid_consumption_kwh_100km",
                    native_unit_of_measurement=KWH_100KM),
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities(
        ChargingSensor(center, d) for d in SENSORS
        if d.requires is None or d.requires in center.entity_ids
    )


class ChargingSensor(ChargingEntity, SensorEntity):
    platform_domain = "sensor"
    entity_description: ChargingSensorDescription
    # Changes with every poll of an identical value – recording it bloats the database.
    _unrecorded_attributes = frozenset({"updated_at"})

    def __init__(self, center: ChargingCenter, description: ChargingSensorDescription) -> None:
        self.entity_description = description
        super().__init__(center, description.key)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.center)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.center)

    @property
    def last_reset(self) -> datetime | None:
        reset = self.entity_description.reset
        if reset is None:
            return None
        if reset == "session":
            session = self.center.engine.sessions.open
            return session.started_at if session else None
        # The period the published figures were computed for – never the bare clock,
        # or the new month would start with last month's total (negative LTS sum).
        start = self.center.statistics_month_start
        if start is None:
            return None
        return start.replace(month=1) if reset == "year" else start
