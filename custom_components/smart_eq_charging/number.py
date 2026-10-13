"""Minimum / preferred departure SOC of the primary plan (§12.2)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .entity import ChargingEntity

FIELDS = {
    "minimum_departure_soc": "minimum_departure_soc_pct",
    "preferred_departure_soc": "preferred_departure_soc_pct",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities(DepartureSocNumber(center, key) for key in FIELDS)


class DepartureSocNumber(ChargingEntity, NumberEntity):
    platform_domain = "number"
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        plans = self.engine.plans
        return getattr(plans[0], FIELDS[self._attr_translation_key]) if plans else None

    async def async_set_native_value(self, value: float) -> None:
        field = FIELDS[self._attr_translation_key]
        changes = {field: int(value)}
        plan = self.engine.plans[0]
        # Keep minimum ≤ preferred whichever side is moved.
        if field == "minimum_departure_soc_pct" and value > plan.preferred_departure_soc_pct:
            changes["preferred_departure_soc_pct"] = int(value)
        if field == "preferred_departure_soc_pct" and value < plan.minimum_departure_soc_pct:
            changes["minimum_departure_soc_pct"] = int(value)
        await self.center.async_run(lambda now: self.engine.update_primary_plan(now, **changes))
