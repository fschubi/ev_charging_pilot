"""Buttons: charge now, stop, charge tonight, clear override, reset (§5.2, §5.3, §8.1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .coordinator import ChargingCenter
from .entity import ChargingEntity


@dataclass(frozen=True, kw_only=True)
class ChargingButtonDescription(ButtonEntityDescription):
    press: Callable[[ChargingCenter], Awaitable[None]]


BUTTONS: tuple[ChargingButtonDescription, ...] = (
    ChargingButtonDescription(key="charge_now", press=lambda c: c.async_charge_now()),
    ChargingButtonDescription(key="stop_charging", press=lambda c: c.async_stop_charging()),
    ChargingButtonDescription(key="charge_tonight", press=lambda c: c.async_charge_tonight()),
    ChargingButtonDescription(key="clear_override", press=lambda c: c.async_clear_override()),
    ChargingButtonDescription(key="reset", press=lambda c: c.async_reset()),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities(ChargingButton(center, d) for d in BUTTONS)


class ChargingButton(ChargingEntity, ButtonEntity):
    entity_description: ChargingButtonDescription

    def __init__(self, center: ChargingCenter, description: ChargingButtonDescription) -> None:
        super().__init__(center, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press(self.center)
