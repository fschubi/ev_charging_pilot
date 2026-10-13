"""Binary sensors: override active, data conflict, problem."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .coordinator import ChargingCenter
from .core.health import HealthStatus
from .entity import ChargingEntity


@dataclass(frozen=True, kw_only=True)
class ChargingBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[ChargingCenter], bool]


BINARY_SENSORS: tuple[ChargingBinaryDescription, ...] = (
    ChargingBinaryDescription(
        key="override_active",
        value=lambda c: c.override is not None or c.one_shot is not None,
    ),
    ChargingBinaryDescription(
        key="data_conflict",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda c: c.data_conflict,
    ),
    ChargingBinaryDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda c: c.health.status is not HealthStatus.HEALTHY
        or c.executor.failure_code is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities(ChargingBinarySensor(center, d) for d in BINARY_SENSORS)


class ChargingBinarySensor(ChargingEntity, BinarySensorEntity):
    entity_description: ChargingBinaryDescription

    def __init__(self, center: ChargingCenter, description: ChargingBinaryDescription) -> None:
        super().__init__(center, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value(self.center)
