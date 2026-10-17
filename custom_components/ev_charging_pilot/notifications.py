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


def _de(price: float) -> str:
    return f"{price:.2f}".replace(".", ",")


def _actions(name: str, price_buttons: tuple[float, ...]) -> list[dict[str, Any]]:
    if name.startswith("ext_price:"):
        # One button per quick-pick price; any other price is typed in the panel
        # (tap on the push), where iOS shows the numeric keypad.
        charge_id = name.removeprefix("ext_price:")
        return [{"action": f"{ACTION_EXT_PRICE}|{charge_id}|{price}",
                 "title": f"{_de(price)} €/kWh"} for price in price_buttons]
    return [EXTRA_ACTIONS[name]] if name in EXTRA_ACTIONS else []


class Notifier:
    def __init__(self, hass: HomeAssistant, conf: dict[str, Any], vehicle_name: str) -> None:
        self.hass = hass
        self.vehicle_name = vehicle_name
        target = conf.get(CONF_NOTIFY_SERVICE) or ""
        self.service = target.removeprefix("notify.") or None
        # Quick-pick prices of the external charge push (from the settings).
        self.price_buttons: tuple[float, ...] = ()

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
                               for action in _actions(a, self.price_buttons)]
        # Tapping a push opens the panel (iOS: url, Android: clickAction).
        data["url"] = data["clickAction"] = notification.url or "/ev-pilot"
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
