"""Dry-run switch: on = the executor only logs what it would do (§6.1)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .entity import ChargingEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DryRunSwitch(entry.runtime_data, "dry_run")])


class DryRunSwitch(ChargingEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.center.dry_run

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.center.async_set_dry_run(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.center.async_set_dry_run(False)
