"""Departure time of the primary plan (§12.2)."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .entity import ChargingEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DepartureTime(entry.runtime_data, "departure")])


class DepartureTime(ChargingEntity, TimeEntity):
    platform_domain = "time"

    @property
    def native_value(self) -> time | None:
        return self.engine.plans[0].departure_time if self.engine.plans else None

    async def async_set_value(self, value: time) -> None:
        await self.center.async_run(lambda now: self.engine.update_primary_plan(
            now, departure_time=value.strftime("%H:%M")))
