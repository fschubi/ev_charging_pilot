"""HA-side regression tests for the medium findings of the review of 2026-10-24."""

from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass

from custom_components.ev_charging_pilot.sensor import SENSORS


def test_m1_hv_cycles_are_no_rising_meter():
    """Frank's OVMS exposes the *remaining* contactor cycles (194 754, falling):
    TOTAL_INCREASING made the long-term statistics see a meter reset at every step."""
    hv = next(d for d in SENSORS if d.key == "hv_contactor_cycles")
    assert hv.state_class is SensorStateClass.MEASUREMENT


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_m8_only_admins_go_live_or_reset_the_wakeup_counters(
        hass, entry, halo, hass_read_only_user, hass_admin_user):
    """The dry-run switch and "reset error" (which clears the wakeup counters) were
    open to every user, while the mode setting itself is admin-only."""
    import pytest
    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized

    from custom_components.ev_charging_pilot.const import DOMAIN
    from custom_components.ev_charging_pilot.core.settings import RunMode

    await _setup(hass, entry)
    center = entry.runtime_data
    user = Context(user_id=hass_read_only_user.id)
    with pytest.raises(Unauthorized):
        await hass.services.async_call("switch", "turn_off",
                                       {"entity_id": "switch.ev_pilot_dry_run"},
                                       blocking=True, context=user)
    assert center.mode is not RunMode.LIVE
    with pytest.raises(Unauthorized):
        await hass.services.async_call("button", "press",
                                       {"entity_id": "button.ev_pilot_reset_error"},
                                       blocking=True, context=user)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN, "reset_error", {}, blocking=True, context=user)
    # Dry run back on stays open: it only makes things safer.
    admin = Context(user_id=hass_admin_user.id)
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.ev_pilot_dry_run"},
                                   blocking=True, context=admin)
    assert center.mode is RunMode.LIVE


async def test_m8_push_buttons_work_once_and_only_when_offered(hass):
    """Any mobile_app_notification_action (another phone, an automation) started a charge."""
    from homeassistant.components.notify import DOMAIN as NOTIFY
    from pytest_homeassistant_custom_component.common import async_mock_service

    from custom_components.ev_charging_pilot.const import ACTION_RETRY, CONF_NOTIFY_SERVICE
    from custom_components.ev_charging_pilot.core.engine import Notification
    from custom_components.ev_charging_pilot.notifications import Notifier

    notifier = Notifier(hass, {CONF_NOTIFY_SERVICE: "notify.mobile_app_phone"}, "Smarty")
    handled: list[str] = []

    async def handler(action, reply):
        handled.append(action)

    unsub = notifier.async_listen_actions(handler)
    hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION_RETRY})
    await hass.async_block_till_done()
    assert handled == []
    async_mock_service(hass, NOTIFY, "mobile_app_phone")
    await notifier.async_send(Notification("start_failed", "high", "Ladestart fehlgeschlagen",
                                           "…", actions=("retry",)))
    for _ in range(2):
        hass.bus.async_fire("mobile_app_notification_action", {"action": ACTION_RETRY})
        await hass.async_block_till_done()
    assert handled == [ACTION_RETRY]
    unsub()
