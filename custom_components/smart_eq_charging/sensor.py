"""Sensors: executor state, desired state, health, plan and estimate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .coordinator import ChargingCenter
from .core.executor import ExecState
from .core.health import HealthStatus
from .core.model import Reason
from .entity import ChargingEntity


def _active_window(c: ChargingCenter):
    return c.one_shot_window or c.window


@dataclass(frozen=True, kw_only=True)
class ChargingSensorDescription(SensorEntityDescription):
    value: Callable[[ChargingCenter], Any]
    attributes: Callable[[ChargingCenter], dict[str, Any]] | None = None


SENSORS: tuple[ChargingSensorDescription, ...] = (
    ChargingSensorDescription(
        key="state",
        device_class=SensorDeviceClass.ENUM,
        options=[s.lower() for s in ExecState],
        value=lambda c: c.executor.state.lower() if c.executor.state else None,
        attributes=lambda c: {
            "since": c.executor.state_since.isoformat() if c.executor.state_since else None,
            "failure_code": c.executor.failure_code,
            "session_id": c.executor.session_id,
            "dry_run": c.dry_run,
        },
    ),
    ChargingSensorDescription(
        key="desired_reason",
        device_class=SensorDeviceClass.ENUM,
        options=[r.value for r in Reason],
        value=lambda c: c.desired.reason.value if c.desired else None,
        attributes=lambda c: {
            "charger_enabled": c.desired.charger_enabled if c.desired else None,
            "source_id": c.desired.source_id if c.desired else None,
            "valid_until": c.desired.valid_until.isoformat()
            if c.desired and c.desired.valid_until else None,
        },
    ),
    ChargingSensorDescription(
        key="health",
        device_class=SensorDeviceClass.ENUM,
        options=[h.lower() for h in HealthStatus],
        value=lambda c: c.health.status.lower(),
        attributes=lambda c: {
            "reasons": list(c.health.reasons),
            "shelly_config_ok": c.shelly_config_ok,
        },
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ChargingSensorDescription(
        key="next_charge_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda c: _active_window(c).start if _active_window(c) else None,
        attributes=lambda c: {
            "departure": _active_window(c).departure.isoformat() if _active_window(c) else None,
            "fallback_without_soc": _active_window(c).fallback_without_soc
            if _active_window(c) else None,
            "source": _active_window(c).source_id if _active_window(c) else None,
        },
    ),
    ChargingSensorDescription(
        key="expected_departure_soc",
        native_unit_of_measurement=PERCENTAGE,
        value=lambda c: _active_window(c).estimate.expected_soc_at_departure
        if _active_window(c) else None,
        attributes=lambda c: {
            "estimate": True,
            "minimum_reachable": _active_window(c).estimate.minimum_reachable
            if _active_window(c) else None,
            "preferred_reachable": _active_window(c).estimate.preferred_reachable
            if _active_window(c) else None,
            "soc_quality": c.soc.quality.value if c.soc else None,
        },
    ),
    ChargingSensorDescription(
        key="last_event",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda c: c.events[-1]["code"] if c.events else None,
        attributes=lambda c: dict(c.events[-1]) if c.events else {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities(ChargingSensor(center, d) for d in SENSORS)


class ChargingSensor(ChargingEntity, SensorEntity):
    entity_description: ChargingSensorDescription

    def __init__(self, center: ChargingCenter, description: ChargingSensorDescription) -> None:
        super().__init__(center, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.center)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.center)
