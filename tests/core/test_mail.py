"""Monthly report e-mail: text, provider presets, message."""

from custom_components.ev_charging_pilot.core.mail import (
    build_message,
    mail_config,
    monthly_mail,
)
from custom_components.ev_charging_pilot.core.settings import Settings


def test_gmail_preset_and_missing_parts():
    config = mail_config("gmail", "", 0, "", "frank@gmail.com", "app-pass", "",
                         ["melanie@example.org", "", "kein-mail"])
    assert (config.host, config.port, config.security) == ("smtp.gmail.com", 587, "starttls")
    assert config.sender == "frank@gmail.com"
    assert config.recipients == ("melanie@example.org",)
    assert config.missing() is None
    assert "Empfänger" in mail_config("gmail", "", 0, "", "a@b.de", "x", "", []).missing()
    assert Settings.from_options({}).mail.missing() is not None


def test_monthly_text_names_kwh_and_cost():
    summary = {"home_energy_kwh": 40.2, "home_cost_eur": 16.48, "external_energy_kwh": 12.5,
               "external_cost_eur": 7.35, "distance_km": 612.4}
    subject, body = monthly_mail(summary, "Smarty", 2026, 9, external_count=2)
    assert subject == "Smarty – Ladebericht September 2026: 40,2 kWh = 16,48 €"
    assert "zu Hause mit 40,2 kWh geladen" in body
    assert "Stromkosten von 16,48 € (Ø 0,41 €/kWh)." in body
    assert "2 Fremdladungen mit 12,5 kWh, 7,35 €" in body
    assert "612 km" in body


def test_message_carries_the_pdf():
    config = mail_config("gmail", "", 0, "", "frank@gmail.com", "x", "",
                         ["a@example.org", "b@example.org"])
    message = build_message(config, "Betreff", "Text", ("ev-pilot-2026-09.pdf", b"%PDF-1.4"),
                            sender_name="Smarty Charging Pilot")
    assert message["To"] == "a@example.org, b@example.org"
    assert "Smarty Charging Pilot" in message["From"]
    attachments = list(message.iter_attachments())
    assert attachments[0].get_filename() == "ev-pilot-2026-09.pdf"
    assert attachments[0].get_content_type() == "application/pdf"
