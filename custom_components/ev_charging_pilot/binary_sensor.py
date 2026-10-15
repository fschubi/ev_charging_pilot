"""Binary sensors (§12.2)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .coordinator import ChargingCenter
from .core.executor import ExecState
from .core.health import HealthStatus
from .core.inputs import Inp
from .core.model import Quality
from .entity import ChargingEntity

CP_REASONS = ("CP_NOT_RESTORED", "CP_STATE_UNKNOWN", "CP_OPEN")


def _flag(c: ChargingCenter, inp: Inp) -> bool | None:
    value = c.engine.values.get(inp)
    if value is None or not value.available or value.normalized is None:
        return None
    return bool(value.normalized)


def _cp_ok(c: ChargingCenter) -> bool:
    return (
        c.settings.cp_failsafe_verified
        and not any(r in CP_REASONS for r in c.engine.health.reasons)
        and c.engine.shelly_config_ok is not False
    )


def _feasible(c: ChargingCenter) -> bool | None:
    window = c.engine.next_window
    return window.estimate.minimum_reachable if window else None


@dataclass(frozen=True, kw_only=True)
class ChargingBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[ChargingCenter], bool | None]
    attributes: Callable[[ChargingCenter], dict[str, Any]] | None = None
    requires: Inp | None = None


BINARY_SENSORS: tuple[ChargingBinaryDescription, ...] = (
    ChargingBinaryDescription(
        key="vehicle_connected", device_class=BinarySensorDeviceClass.PLUG,
        value=lambda c: c.engine.executor.state not in (None, ExecState.DISCONNECTED),
    ),
    ChargingBinaryDescription(
        key="charging", device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value=lambda c: c.engine.executor.state is ExecState.CHARGING,
    ),
    ChargingBinaryDescription(
        key="charge_problem", device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda c: c.engine.executor.failure_code is not None
        or c.engine.health.status is HealthStatus.ERROR,
        attributes=lambda c: {"failure_code": c.engine.executor.failure_code,
                              "health": list(c.engine.health.reasons)},
    ),
    ChargingBinaryDescription(
        key="cp_failsafe_ok", requires=Inp.CP_RELAY, entity_category=EntityCategory.DIAGNOSTIC,
        value=_cp_ok,
        attributes=lambda c: {"failsafe_verified": c.settings.cp_failsafe_verified,
                              "shelly_config_ok": c.engine.shelly_config_ok},
    ),
    ChargingBinaryDescription(
        key="charger_available", device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: c.engine.values.get(Inp.CHARGER_ENABLE) is not None
        and c.engine.values[Inp.CHARGER_ENABLE].available,
    ),
    ChargingBinaryDescription(
        key="vehicle_available", device_class=BinarySensorDeviceClass.CONNECTIVITY,
        requires=Inp.OVMS_SOC, entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: c.engine.soc.quality is Quality.GOOD,
        attributes=lambda c: {"soc_quality": str(c.engine.soc.quality)},
    ),
    ChargingBinaryDescription(
        key="data_conflict", device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda c: c.engine.data_conflict,
    ),
    ChargingBinaryDescription(
        key="soc_stale", device_class=BinarySensorDeviceClass.PROBLEM, requires=Inp.OVMS_SOC,
        value=lambda c: c.engine.soc.quality is Quality.STALE,
    ),
    ChargingBinaryDescription(
        key="charge_plan_feasible", value=_feasible,
        attributes=lambda c: {
            "expected_soc": c.engine.next_window.estimate.expected_soc_at_departure
            if c.engine.next_window else None,
            "minimum_soc": c.engine.next_window.minimum_soc_pct if c.engine.next_window else None,
        },
    ),
    ChargingBinaryDescription(
        key="manual_override",
        value=lambda c: c.engine.override is not None or c.engine.one_shot is not None,
        attributes=lambda c: {
            "override": c.engine.override.as_dict() if c.engine.override else None,
            "one_shot": c.engine.one_shot.as_dict() if c.engine.one_shot else None,
        },
    ),
    ChargingBinaryDescription(
        key="hvcycle_warning", device_class=BinarySensorDeviceClass.PROBLEM,
        requires=Inp.OVMS_HV_CYCLES,
        value=lambda c: c.engine.hv.warned_day is not None
        and c.engine.hv.warned_day == c.engine.hv.day,
        attributes=lambda c: {"today": c.engine.hv.today},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities(
        ChargingBinarySensor(center, d) for d in BINARY_SENSORS
        if d.requires is None or d.requires in center.entity_ids
    )


class ChargingBinarySensor(ChargingEntity, BinarySensorEntity):
    platform_domain = "binary_sensor"
    entity_description: ChargingBinaryDescription

    def __init__(self, center: ChargingCenter, description: ChargingBinaryDescription) -> None:
        self.entity_description = description
        super().__init__(center, description.key)

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.center)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.center)
