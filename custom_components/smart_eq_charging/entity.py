"""Shared base for all entities of the integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME
from .coordinator import ChargingCenter


class ChargingEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, center: ChargingCenter, key: str) -> None:
        self.center = center
        self._attr_translation_key = key
        self._attr_unique_id = f"{center.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, center.entry.entry_id)},
            name=NAME,
            manufacturer="fschubi",
            model="Smart EQ 453 Charging Center",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.center.async_add_listener(self.async_write_ha_state))
