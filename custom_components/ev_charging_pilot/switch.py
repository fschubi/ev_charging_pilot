"""Switches (§12.2): automation on/off and dry-run."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .core.settings import RunMode
from .entity import ChargingEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    center = entry.runtime_data
    async_add_entities([AutomationSwitch(center, "automation"), DryRunSwitch(center, "dry_run")])


class AutomationSwitch(ChargingEntity, SwitchEntity):
    """Off: plans, target SOC and climate are ignored; the Halo is left alone."""

    platform_domain = "switch"

    @property
    def is_on(self) -> bool:
        return self.engine.automation_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.center.async_run(lambda now: self.engine.set_automation(now, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.center.async_run(lambda now: self.engine.set_automation(now, False))


class DryRunSwitch(ChargingEntity, SwitchEntity):
    """On: the executor runs fully but only logs what it would do (§6.1)."""

    platform_domain = "switch"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.center.mode is not RunMode.LIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"mode": str(self.center.mode)}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.center.async_set_mode(RunMode.DRY_RUN)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_require_admin()
        await self.center.async_set_mode(RunMode.LIVE)
