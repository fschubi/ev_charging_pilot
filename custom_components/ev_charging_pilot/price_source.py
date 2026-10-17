"""Fetch dynamic prices from Tibber or any price entity and hand them to the engine."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CALLBACK_TYPE, CoreState, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .core.prices import (
    PriceSlot,
    describe_prices,
    parse_price_attributes,
    parse_tibber_response,
)
from .core.settings import PriceSource, Settings

_LOGGER = logging.getLogger(__name__)

REFRESH = timedelta(minutes=30)
# Right after a restart the price integration often answers empty (Tibber loads its
# prices lazily). Retry quickly and only report a problem once these are used up.
RETRY_DELAYS_S = (60, 120, 300)


class PriceFetcher:
    def __init__(self, hass: HomeAssistant, tz: ZoneInfo,
                 on_prices: Callable[[list[PriceSlot]], None],
                 on_problem: Callable[[str], None]) -> None:
        self.hass = hass
        self.tz = tz
        self._on_prices = on_prices
        self._on_problem = on_problem
        self._unsubs: list[CALLBACK_TYPE] = []
        self.settings: Settings | None = None
        self.last_update: datetime | None = None
        self.last_error: str | None = None
        self._failures = 0
        self._retry: CALLBACK_TYPE | None = None

    def start(self, settings: Settings) -> None:
        self.stop()
        self.settings = settings
        self._failures = 0
        if settings.price_source is PriceSource.FIXED:
            return
        self._unsubs.append(async_track_time_interval(self.hass, self._interval, REFRESH))
        if settings.price_source is PriceSource.ENTITY and settings.price_entity:
            self._unsubs.append(async_track_state_change_event(
                self.hass, [settings.price_entity], self._entity_changed))
        if self.hass.state is CoreState.running:
            self.hass.async_create_task(self.async_refresh())
        else:
            # Other integrations (Tibber, Nordpool) are not ready before HA has started.
            self._unsubs.append(self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._started))

    def stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_retry()

    def _cancel_retry(self) -> None:
        if self._retry is not None:
            self._retry()
            self._retry = None

    @callback
    def _started(self, _event) -> None:
        self.hass.async_create_task(self.async_refresh())

    @callback
    def _retry_now(self, _now: datetime) -> None:
        self._retry = None
        self.hass.async_create_task(self.async_refresh())

    @callback
    def _interval(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_refresh())

    @callback
    def _entity_changed(self, _event) -> None:
        self.hass.async_create_task(self.async_refresh())

    async def async_refresh(self) -> list[PriceSlot]:
        settings = self.settings
        if settings is None or settings.price_source is PriceSource.FIXED:
            return []
        try:
            if settings.price_source is PriceSource.TIBBER:
                slots = await self._tibber()
            else:
                slots = self._entity(settings.price_entity)
        except (HomeAssistantError, ValueError, KeyError) as err:
            self._failed(f"Preise nicht abrufbar: {err}")
            return []
        if not slots:
            self._failed("Preisquelle liefert keine Preise")
            return []
        self._cancel_retry()
        self._failures = 0
        self.last_error = None
        self.last_update = dt_util.utcnow()
        self._on_prices(slots)
        return slots

    def _failed(self, message: str) -> None:
        self._cancel_retry()
        if self._failures < len(RETRY_DELAYS_S):
            delay = RETRY_DELAYS_S[self._failures]
            self._failures += 1
            _LOGGER.debug("%s – neuer Versuch in %s s", message, delay)
            self._retry = async_call_later(self.hass, delay, self._retry_now)
            return
        self._problem(message)

    async def async_check(self, source: PriceSource, entity_id: str | None) -> dict[str, Any]:
        """Settings check: what a source delivers right now – nothing is stored."""
        try:
            if source is PriceSource.FIXED:
                return {"ok": True, "slots": 0, "note": "Festpreis – keine dynamischen Preise"}
            if source is PriceSource.TIBBER:
                slots = await self._tibber()
            else:
                if not entity_id:
                    raise HomeAssistantError("keine Preis-Entität gewählt")
                slots = self._entity(entity_id)
        except (HomeAssistantError, ValueError, KeyError) as err:
            return {"ok": False, "error": str(err)}
        if len(slots) <= 1:
            return {"ok": False, **describe_prices(slots, self.tz),
                    "error": "nur der aktuelle Preis, keine Preisliste – günstige Zeiten "
                             "lassen sich damit nicht planen"}
        return {"ok": True, **describe_prices(slots, self.tz)}

    def _problem(self, message: str) -> None:
        if message != self.last_error:
            self.last_error = message
            self._on_problem(message)

    async def _tibber(self) -> list[PriceSlot]:
        if not self.hass.services.has_service("tibber", "get_prices"):
            raise HomeAssistantError("Tibber-Integration nicht eingerichtet")
        start = dt_util.start_of_local_day()
        response: Any = await self.hass.services.async_call(
            "tibber", "get_prices",
            {"start": start.isoformat(), "end": (start + timedelta(days=2)).isoformat()},
            blocking=True, return_response=True)
        return parse_tibber_response(response, self.tz)

    def _entity(self, entity_id: str) -> list[PriceSlot]:
        state = self.hass.states.get(entity_id)
        if state is None:
            raise HomeAssistantError(f"{entity_id} existiert nicht")
        today = dt_util.now(self.tz).date()
        slots = parse_price_attributes(dict(state.attributes), self.tz, today)
        if slots:
            return slots
        # A sensor with only the current price: price the current hour.
        try:
            price = float(state.state)
        except ValueError:
            return []
        if price > 5:
            price /= 100
        hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        return [PriceSlot(hour, hour + timedelta(hours=1), price)]
