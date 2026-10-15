"""Shared base for all entities. Entity IDs follow masterplan §12 (ev_pilot_*)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, ENTITY_PREFIX
from .coordinator import ChargingCenter


class ChargingEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    platform_domain: str = ""

    def __init__(self, center: ChargingCenter, key: str) -> None:
        self.center = center
        self._attr_translation_key = key
        self._attr_unique_id = f"{center.entry.entry_id}_{key}"
        # Suggested ID from §12; the registry keeps it stable afterwards.
        self.entity_id = f"{self.platform_domain}.{ENTITY_PREFIX}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, center.entry.entry_id)},
            name=center.name,
            manufacturer="fschubi",
            model="EV Charging Pilot",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def engine(self):
        return self.center.engine

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.center.async_add_listener(self.async_write_ha_state))
