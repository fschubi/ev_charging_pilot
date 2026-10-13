"""Push delivery via notify.mobile_app_* incl. actionable notification (§8.3, §8.4)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback

from .const import ACTION_NOW, ACTION_PLAN, ACTION_TONIGHT, CONF_NOTIFY_SERVICE
from .core.engine import Notification

_LOGGER = logging.getLogger(__name__)

INTERRUPTION = {"critical": "critical", "high": "time-sensitive", "normal": "active"}
ACTIONS = (
    {"action": ACTION_PLAN, "title": "Normaler Plan"},
    {"action": ACTION_TONIGHT, "title": "Heute Nacht laden"},
    {"action": ACTION_NOW, "title": "Jetzt laden"},
)
MOBILE_ACTION_EVENT = "mobile_app_notification_action"


class Notifier:
    def __init__(self, hass: HomeAssistant, conf: dict[str, Any]) -> None:
        self.hass = hass
        target = conf.get(CONF_NOTIFY_SERVICE) or ""
        self.service = target.removeprefix("notify.") or None

    async def async_send(self, notification: Notification) -> None:
        if not self.service:
            return
        data: dict[str, Any] = {
            "push": {"interruption-level": INTERRUPTION.get(notification.priority, "active")},
            "tag": f"smart_eq_{notification.category}",
        }
        if notification.priority == "critical":
            data["push"]["sound"] = {"name": "default", "critical": 1, "volume": 1.0}
            data["ttl"] = 0
            data["priority"] = "high"
        if notification.actionable:
            data["actions"] = list(ACTIONS)
        try:
            await self.hass.services.async_call(
                "notify", self.service,
                {"title": f"Smart EQ: {notification.title}", "message": notification.message,
                 "data": data},
                blocking=False,
            )
        except Exception:  # noqa: BLE001 – a broken notifier must not break charging
            _LOGGER.exception("Push über notify.%s fehlgeschlagen", self.service)

    @callback
    def async_listen_actions(
        self, handler: Callable[[str], Awaitable[None]]
    ) -> CALLBACK_TYPE:
        @callback
        def on_action(event: Event) -> None:
            action = event.data.get("action")
            if action in (ACTION_PLAN, ACTION_TONIGHT, ACTION_NOW):
                self.hass.async_create_task(handler(action))

        return self.hass.bus.async_listen(MOBILE_ACTION_EVENT, on_action)
