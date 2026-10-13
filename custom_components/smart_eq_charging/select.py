"""Override mode select (§5.3, §12.2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ChargingConfigEntry
from .core.engine import TickResult
from .core.planner import OverrideMode
from .entity import ChargingEntity

NONE = "none"
OPTIONS = [NONE, *(m.value for m in OverrideMode)]
DEFAULT_DURATION = timedelta(hours=2)
FALLBACK_UNTIL = timedelta(hours=8)


async def async_setup_entry(
    hass: HomeAssistant, entry: ChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([OverrideModeSelect(entry.runtime_data, "override_mode")])


class OverrideModeSelect(ChargingEntity, SelectEntity):
    """Selecting a mode sets the override with sensible parameters:

    duration = 2 h, until_time = next departure, until_soc = preferred SOC
    of the primary plan. Finer control via the set_override service.
    """

    platform_domain = "select"
    _attr_options = OPTIONS

    @property
    def current_option(self) -> str:
        return self.engine.override.mode.value if self.engine.override else NONE

    async def async_select_option(self, option: str) -> None:
        engine = self.engine

        def apply(now: datetime) -> TickResult:
            if option == NONE:
                return engine.clear_override(now)
            mode = OverrideMode(option)
            expires_at = None
            target = None
            if mode is OverrideMode.DURATION:
                expires_at = now + DEFAULT_DURATION
            elif mode is OverrideMode.UNTIL_TIME:
                window = engine.next_window
                expires_at = window.departure if window else now + FALLBACK_UNTIL
            elif mode is OverrideMode.UNTIL_SOC:
                target = engine.plans[0].preferred_departure_soc_pct if engine.plans else 90
            return engine.set_override(now, mode, expires_at=expires_at, target_soc=target)

        await self.center.async_run(apply)
