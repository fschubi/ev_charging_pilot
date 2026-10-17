"""Monthly report by e-mail: text, message with PDF attachment, SMTP delivery.

Only the standard library – the HA side runs :func:`send` in the executor.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember")

# host, port, security – the user only picks the provider.
PROVIDERS: dict[str, tuple[str, int, str]] = {
    "gmail": ("smtp.gmail.com", 587, "starttls"),
    "gmx": ("mail.gmx.net", 587, "starttls"),
    "webde": ("smtp.web.de", 587, "starttls"),
    "tonline": ("securesmtp.t-online.de", 587, "starttls"),
    "icloud": ("smtp.mail.me.com", 587, "starttls"),
    "outlook": ("smtp-mail.outlook.com", 587, "starttls"),
}
TIMEOUT_S = 30


@dataclass(frozen=True, slots=True)
class MailConfig:
    host: str
    port: int
    security: str  # "starttls" | "ssl" | "none"
    user: str
    password: str = field(repr=False)  # never in logs or tracebacks
    sender: str
    recipients: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return bool(self.host and self.user and self.password and self.recipients)

    def missing(self) -> str | None:
        if not self.recipients:
            return "kein Empfänger eingetragen"
        if not self.user or not self.password:
            return "Benutzername oder Passwort fehlt"
        if not self.host:
            return "kein Mailserver eingetragen"
        return None


def mail_config(provider: str, host: str, port: int, security: str, user: str,
                password: str, sender: str, recipients: list[str]) -> MailConfig:
    if provider in PROVIDERS:
        host, port, security = PROVIDERS[provider]
    clean = tuple(r.strip() for r in recipients if r and "@" in r)
    return MailConfig(host.strip(), int(port), security, user.strip(), password,
                      (sender or user).strip(), clean)


def _eur(value: float | None) -> str:
    return f"{value or 0:.2f} €".replace(".", ",")


def _kwh(value: float | None) -> str:
    return f"{value or 0:.1f} kWh".replace(".", ",")


def monthly_mail(summary: dict[str, Any], vehicle: str, year: int, month: int,
                 external_count: int) -> tuple[str, str]:
    """Subject and plain-text body of the monthly report mail."""
    name = f"{MONTHS[month - 1]} {year}"
    home_kwh = summary.get("home_energy_kwh") or 0.0
    home_cost = summary.get("home_cost_eur") or 0.0
    lines = [
        "Hallo,",
        "",
        f"im {name} wurde {vehicle} zu Hause mit {_kwh(home_kwh)} geladen.",
        f"Das entspricht Stromkosten von {_eur(home_cost)}"
        + (f" (Ø {home_cost / home_kwh:.2f} €/kWh).".replace(".", ",", 1)
           if home_kwh >= 0.1 else "."),
    ]
    if external_count:
        lines += ["", f"Unterwegs: {external_count} Fremdladung"
                  f"{'en' if external_count != 1 else ''} mit "
                  f"{_kwh(summary.get('external_energy_kwh'))}, "
                  f"{_eur(summary.get('external_cost_eur'))} (unterwegs bezahlt, nicht Teil des "
                  "Hausstroms)."]
    if summary.get("distance_km"):
        lines += ["", f"Gefahren: {summary['distance_km']:.0f} km".replace(".", ",")]
    lines += ["", "Der vollständige Monatsbericht liegt als PDF im Anhang.", "",
              f"– {vehicle} Charging Pilot"]
    subject = f"{vehicle} – Ladebericht {name}: {_kwh(home_kwh)} = {_eur(home_cost)}"
    return subject, "\n".join(lines)


def build_message(config: MailConfig, subject: str, body: str,
                  attachment: tuple[str, bytes] | None = None,
                  sender_name: str = "") -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name, config.sender)) if sender_name else config.sender
    message["To"] = ", ".join(config.recipients)
    message["Message-ID"] = make_msgid(domain=config.sender.rsplit("@", 1)[-1] or None)
    message.set_content(body)
    if attachment is not None:
        name, data = attachment
        message.add_attachment(data, maintype="application", subtype="pdf", filename=name)
    return message


def send(config: MailConfig, message: EmailMessage) -> None:
    """Blocking SMTP delivery; raises on any error (the caller reports it)."""
    context = ssl.create_default_context()
    if config.security == "ssl":
        with smtplib.SMTP_SSL(config.host, config.port, timeout=TIMEOUT_S,
                              context=context) as smtp:
            smtp.login(config.user, config.password)
            smtp.send_message(message)
        return
    with smtplib.SMTP(config.host, config.port, timeout=TIMEOUT_S) as smtp:
        if config.security == "starttls":
            smtp.starttls(context=context)
        smtp.login(config.user, config.password)
        smtp.send_message(message)


def friendly_error(err: Exception) -> str:
    """German hint for the usual SMTP problems."""
    if isinstance(err, smtplib.SMTPAuthenticationError):
        return ("Anmeldung abgelehnt – bei Gmail/iCloud ein App-Passwort verwenden, "
                "nicht das normale Passwort")
    if isinstance(err, smtplib.SMTPRecipientsRefused):
        return "Empfängeradresse abgelehnt"
    if isinstance(err, smtplib.SMTPSenderRefused):
        return "Absenderadresse abgelehnt – Absender muss zum Konto passen"
    if isinstance(err, smtplib.SMTPResponseException):
        return f"Mailserver meldet {err.smtp_code}: {err.smtp_error.decode(errors='ignore')}"
    if isinstance(err, smtplib.SMTPException):  # subclass of OSError – check it first
        return str(err) or err.__class__.__name__
    if isinstance(err, (TimeoutError, ConnectionError, OSError)):
        return f"Mailserver nicht erreichbar ({err})"
    return str(err) or err.__class__.__name__
