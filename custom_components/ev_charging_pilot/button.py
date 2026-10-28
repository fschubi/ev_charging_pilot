"""Buttons (§12.2). Every press goes through the engine – never straight to hardware."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .core.engine import Engine, TickResult
from .core.inputs import Inp
from .core.ports import CommandKind
from .entity import ChargingEntity


@dataclass(frozen=True, kw_only=True)
class ChargingButtonDescription(ButtonEntityDescription):
    press: Callable[[Engine, datetime], TickResult]
    requires: Inp | None = None
    admin: bool = False


BUTTONS: tuple[ChargingButtonDescription, ...] = (
    ChargingButtonDescription(
        key="start_charge",
        press=lambda e, now: e.charge_now(now)),
    ChargingButtonDescription(
        key="stop_charge", press=lambda e, now: e.stop_charging(now)),
    ChargingButtonDescription(
        key="vehicle_wakeup", requires=Inp.OVMS_SOC,
        press=lambda e, now: e.wakeup(now, CommandKind.OVMS_WAKEUP)),
    ChargingButtonDescription(
        key="cp_wakeup", requires=Inp.CP_RELAY,
        press=lambda e, now: e.wakeup(now, CommandKind.CP_PULSE)),
    # Resetting also clears the wakeup counters of the window (rule 3): admins only.
    ChargingButtonDescription(key="reset_error", admin=True, press=lambda e, now: e.reset(now)),
    ChargingButtonDescription(
        key="climate_5min", requires=Inp.OVMS_SOC, press=lambda e, now: e.start_climate(now, 5)),
    ChargingButtonDescription(
        key="climate_10min", requires=Inp.OVMS_SOC,
        press=lambda e, now: e.start_climate(now, 10)),
    ChargingButtonDescription(
        key="climate_15min", requires=Inp.OVMS_SOC,
        press=lambda e, now: e.start_climate(now, 15)),
    ChargingButtonDescription(
        key="climate_stop", requires=Inp.OVMS_SOC, press=lambda e, now: e.stop_climate(now)),
    ChargingButtonDescription(
        key="one_shot_tonight", press=lambda e, now: e.start_one_shot(now)),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities(
        ChargingButton(center, d) for d in BUTTONS
        if d.requires is None or d.requires in center.entity_ids
    )


class ChargingButton(ChargingEntity, ButtonEntity):
    platform_domain = "button"
    entity_description: ChargingButtonDescription

    def __init__(self, center, description: ChargingButtonDescription) -> None:
        self.entity_description = description
        super().__init__(center, description.key)

    async def async_press(self) -> None:
        if self.entity_description.admin:
            await self.async_require_admin()
        try:
            await self.center.async_run(
                lambda now: self.entity_description.press(self.engine, now))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
