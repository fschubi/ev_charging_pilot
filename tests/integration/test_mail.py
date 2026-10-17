"""Monthly report by e-mail and the amount push to another phone."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.ev_charging_pilot.const import CONF_NOTIFY_SERVICE, DOMAIN
from custom_components.ev_charging_pilot.settings_schema import apply_changes, current_values

MAIL = {"mail_enabled": True, "mail_provider": "gmail", "mail_user": "frank@gmail.com",
        "mail_password": "app-pass", "mail_to_1": "melanie@example.org",
        "mail_to_2": "frank@gmail.com",
        "report_push_targets": "notify.mobile_app_iphone_von_melanie"}


async def _setup(hass, entry, options):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data=dict(entry.data),
                            options={"mode": "dry_run", **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_test_mail_goes_out_with_pdf(hass, entry, halo):
    entry = await _setup(hass, entry, MAIL)
    smtp = MagicMock()
    with patch("custom_components.ev_charging_pilot.core.mail.smtplib.SMTP") as factory:
        factory.return_value.__enter__.return_value = smtp
        response = await hass.services.async_call(DOMAIN, "send_report_mail", {},
                                                  blocking=True, return_response=True)
    assert response["ok"] and response["subject"].startswith("[Test] ")
    factory.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("frank@gmail.com", "app-pass")
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "melanie@example.org, frank@gmail.com"
    assert next(message.iter_attachments()).get_filename().endswith(".pdf")
    assert entry.runtime_data.mail_result["ok"]


async def test_wrong_password_is_reported(hass, entry, halo):
    import smtplib

    await _setup(hass, entry, MAIL)
    with patch("custom_components.ev_charging_pilot.core.mail.smtplib.SMTP") as factory:
        factory.return_value.__enter__.return_value.login.side_effect = \
            smtplib.SMTPAuthenticationError(535, b"bad")
        with pytest.raises(ServiceValidationError, match="App-Passwort"):
            await hass.services.async_call(DOMAIN, "send_report_mail", {}, blocking=True)


async def test_unconfigured_mail_is_refused(hass, entry, halo):
    await _setup(hass, entry, {})
    with pytest.raises(ServiceValidationError, match="nicht eingerichtet"):
        await hass.services.async_call(DOMAIN, "send_report_mail", {}, blocking=True)


async def test_first_of_month_mails_and_pushes_the_amount(hass, entry, halo):
    entry = MockConfigEntry(domain=DOMAIN, version=2, options={"mode": "dry_run", **MAIL},
                            data={**entry.data, CONF_NOTIFY_SERVICE: "notify.mobile_app_frank"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    melanie = async_mock_service(hass, "notify", "mobile_app_iphone_von_melanie")
    async_mock_service(hass, "notify", "mobile_app_frank")
    with patch("custom_components.ev_charging_pilot.core.mail.smtplib.SMTP") as factory:
        await entry.runtime_data.async_monthly_report(
            datetime(2026, 11, 1, 6, 0, tzinfo=dt_util.get_default_time_zone()))
        await hass.async_block_till_done()
    assert factory.return_value.__enter__.return_value.send_message.called
    assert melanie and "Oktober 2026: zu Hause" in melanie[-1].data["message"]


def test_password_never_leaves_and_empty_keeps_it():
    values = current_values({"mail_password": "geheim"})
    assert values["mail_password"] == "" and values["mail_password_set"] is True
    kept = apply_changes({"mail_password": "geheim"}, {"mail_password": "", "mail_to_1": "x@y.z"})
    assert kept["mail_password"] == "geheim"
    changed = apply_changes({"mail_password": "geheim"}, {"mail_password": "neu"})
    assert changed["mail_password"] == "neu"
