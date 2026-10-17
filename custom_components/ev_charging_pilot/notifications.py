"""Push delivery via notify.mobile_app_* incl. actionable notification (§8.3, §8.4)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback

from .const import (
    ACTION_EXT_PRICE,
    ACTION_NOW,
    ACTION_PLAN,
    ACTION_RETRY,
    ACTION_TONIGHT,
    CONF_NOTIFY_SERVICE,
)
from .core.engine import Notification

_LOGGER = logging.getLogger(__name__)

INTERRUPTION = {"critical": "critical", "high": "time-sensitive", "normal": "active"}
ACTIONS = (
    {"action": ACTION_PLAN, "title": "Normaler Plan"},
    {"action": ACTION_TONIGHT, "title": "Heute Nacht laden"},
    {"action": ACTION_NOW, "title": "Jetzt laden"},
)
EXTRA_ACTIONS = {"retry": {"action": ACTION_RETRY, "title": "Erneut versuchen"}}
MOBILE_ACTION_EVENT = "mobile_app_notification_action"


def _action(name: str) -> dict[str, Any] | None:
    if name.startswith("ext_price:"):
        # The companion app shows a text field (iOS and Android: behavior textInput).
        return {"action": f"{ACTION_EXT_PRICE}|{name.removeprefix('ext_price:')}",
                "title": "Preis eingeben", "behavior": "textInput",
                "textInputButtonTitle": "Speichern",
                "textInputPlaceholder": "€ pro kWh, z. B. 0,59"}
    return EXTRA_ACTIONS.get(name)


class Notifier:
    def __init__(self, hass: HomeAssistant, conf: dict[str, Any], vehicle_name: str) -> None:
        self.hass = hass
        self.vehicle_name = vehicle_name
        target = conf.get(CONF_NOTIFY_SERVICE) or ""
        self.service = target.removeprefix("notify.") or None

    async def async_send(self, notification: Notification) -> None:
        if not self.service:
            return
        data: dict[str, Any] = {
            "push": {"interruption-level": INTERRUPTION.get(notification.priority, "active")},
            "tag": f"ev_pilot_{notification.category}",
        }
        if notification.priority == "critical":
            data["push"]["sound"] = {"name": "default", "critical": 1, "volume": 1.0}
            data["ttl"] = 0
            data["priority"] = "high"
        if notification.actionable:
            data["actions"] = list(ACTIONS)
        elif notification.actions:
            data["actions"] = [action for a in notification.actions
                               if (action := _action(a)) is not None]
        # Tapping a push opens the panel (iOS: url, Android: clickAction).
        data["url"] = data["clickAction"] = "/ev-pilot"
        try:
            await self.hass.services.async_call(
                "notify", self.service,
                {"title": f"{self.vehicle_name}: {notification.title}",
                 "message": notification.message,
                 "data": data},
                blocking=False,
            )
        except Exception:  # noqa: BLE001 – a broken notifier must not break charging
            _LOGGER.exception("Push über notify.%s fehlgeschlagen", self.service)

    @callback
    def async_listen_actions(
        self, handler: Callable[[str, str | None], Awaitable[None]]
    ) -> CALLBACK_TYPE:
        @callback
        def on_action(event: Event) -> None:
            action = str(event.data.get("action") or "")
            if action in (ACTION_PLAN, ACTION_TONIGHT, ACTION_NOW, ACTION_RETRY) \
                    or action.startswith(f"{ACTION_EXT_PRICE}|"):
                self.hass.async_create_task(handler(action, event.data.get("reply_text")))

        return self.hass.bus.async_listen(MOBILE_ACTION_EVENT, on_action)
