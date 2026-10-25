"""Shared base for all entities. Entity IDs follow masterplan §12 (ev_pilot_*)."""

from __future__ import annotations

from homeassistant.exceptions import Unauthorized
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

    async def async_require_admin(self) -> None:
        """Going live or clearing the wakeup counters is for admins, like the settings.
        Calls without a user (automations, scripts) were set up by an admin."""
        context = self._context
        if context is None or not context.user_id:
            return
        user = await self.hass.auth.async_get_user(context.user_id)
        if user is None or not user.is_admin:
            raise Unauthorized(context=context)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.center.async_add_listener(self.async_write_ha_state))
