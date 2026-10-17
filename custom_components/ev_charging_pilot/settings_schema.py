"""Settings as a schema for the panel's "Einstellungen" tab (same groups as the options flow).

The panel renders a form from this list and writes changes through the
``set_settings`` WebSocket command, which stores them as config-entry options
– exactly what the options flow does.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .core.settings import (
    DEFAULT_OPTIONS,
    OPT_PRICE_HISTORY,
    ClimateAfterTarget,
    OdometerSource,
    PriceSource,
    RunMode,
)

PRICE_FIELD = "price_eur_kwh"
PRICE_VALID_FROM = "price_valid_from"


def _f(key: str, label: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "type": kind, **extra}


def _n(key: str, label: str, minimum: float, maximum: float, step: float = 1,
       unit: str = "", **extra: Any) -> dict[str, Any]:
    return _f(key, label, "number", min=minimum, max=maximum, step=step, unit=unit, **extra)


def _b(key: str, label: str, **extra: Any) -> dict[str, Any]:
    return _f(key, label, "bool", **extra)


def _s(key: str, label: str, options: dict[str, str], **extra: Any) -> dict[str, Any]:
    return _f(key, label, "select", options=[{"value": k, "label": v}
                                             for k, v in options.items()], **extra)


GROUPS: list[dict[str, Any]] = [
    {"id": "general", "title": "Allgemein", "icon": "mdi:car-cog",
     "description": "Name, Betriebsmodus und ob die Integration Befehle ans Auto senden darf.",
     "fields": [
        _f("vehicle_name", "Name deines Fahrzeugs", "text",
           help="Erscheint als „<Name> Charging Pilot“ in Seitenleiste, Panel, Push und PDF."),
        _s("mode", "Betriebsmodus", {RunMode.DRY_RUN: "Probebetrieb (nur protokollieren)",
                                     RunMode.LIVE: "Live (schaltet die Wallbox)",
                                     RunMode.REPLAY: "Replay (keine Hardware)"},
           help="Im Probebetrieb siehst du im Ereignisprotokoll, was die Integration tun würde."),
        _b("ovms_enabled", "Fahrzeug: Lesen & Schreiben",
           help="Aus = Fahrzeugdaten nur lesen. An = Wecken und Vorklimatisierung werden ans "
                "Auto gesendet (Befehlsweg wird automatisch erkannt)."),
    ]},
    {"id": "prices", "title": "Strompreis", "icon": "mdi:currency-eur",
     "description": "Was eine kWh kostet – fest oder dynamisch (Tibber).",
     "fields": [
        _s("price_source", "Preisquelle", {PriceSource.FIXED: "Festpreis",
                                           PriceSource.TIBBER: "Tibber",
                                           PriceSource.ENTITY: "Preis-Sensor (Nordpool, EPEX …)"}),
        _n(PRICE_FIELD, "Arbeitspreis", 0, 2, 0.001, "€/kWh",
           help="Festpreis; bei dynamischem Tarif der Rückfall, falls keine Preise kommen."),
        _f(PRICE_VALID_FROM, "Gültig ab", "date",
           help="Ein neuer Preis ändert keine vergangenen Monate."),
        _f("price_entity", "Preis-Sensor", "entity", domain="sensor",
           show_if={"price_source": PriceSource.ENTITY}),
        _b("price_optimization", "In den günstigsten Stunden laden",
           help="Zeitpläne mit Abfahrtszeit laden dann, wenn der Strom am billigsten ist.",
           show_if={"price_source": [PriceSource.TIBBER, PriceSource.ENTITY]}),
        _n("price_blocks", "Max. Ladeblöcke pro Nacht", 1, 2, advanced=True,
           help="Jeder zusätzliche Block kann das Auto erneut wecken.",
           show_if={"price_source": [PriceSource.TIBBER, PriceSource.ENTITY]}),
        _n("full_soc_pct", "Hoher Ladestand ab", 50, 100, 5, "%",
           help="Ladeziele über diesem Wert werden erst kurz vor der Abfahrt erreicht – "
                "auch wenn der Strom früher billiger wäre. Ein voller Akku soll nicht "
                "stundenlang stehen.",
           show_if={"price_source": [PriceSource.TIBBER, PriceSource.ENTITY]}),
        _n("full_hold_max_h", "… höchstens so lange vor Abfahrt voll", 0, 12, 0.5, "h",
           help="Gerechnet ab „Fertig vor Abfahrt“. 0 = keine Begrenzung.",
           show_if={"price_source": [PriceSource.TIBBER, PriceSource.ENTITY]}),
    ]},
    {"id": "notifications", "title": "Benachrichtigungen", "icon": "mdi:bell-outline",
     "description": "Wann du eine Push-Nachricht aufs Handy bekommst.",
     "fields": [
        _b("notify_plug_in_action", "Beim Einstecken fragen, wie geladen werden soll"),
        _b("notify_start_failed", "Ladestart fehlgeschlagen oder abgebrochen"),
        _b("notify_plug_reminder", "Abends erinnern, wenn nicht eingesteckt"),
        _f("plug_reminder_time", "Uhrzeit der Abend-Erinnerung", "time",
           show_if={"notify_plug_reminder": True}),
        _b("notify_plan_infeasible", "Mindest-SOC bis zur Abfahrt nicht erreichbar"),
        _b("notify_cp", "Problem mit der CP-Unterbrechung (Shelly)"),
        _b("notify_health", "Systemzustand verschlechtert sich"),
        _b("notify_hv_cycles", "HV-Kontaktorzähler auffällig"),
        _b("notify_external", "Fremdladung erkannt"),
        _b("report_auto_monthly", "Monatsbericht (PDF) am 1. erstellen"),
        _b("notify_report", "Benachrichtigen, wenn der Monatsbericht fertig ist",
           show_if={"report_auto_monthly": True}),
        _b("notify_weekly", "Wochenrückblick am Sonntagabend",
           help="kWh, Kosten, Ladungen, Weckvorgänge und Kilometer der letzten 7 Tage."),
    ]},
    {"id": "mail", "title": "Monatsbericht per E-Mail", "icon": "mdi:email-outline",
     "description": "Am 1. des Monats den PDF-Bericht des Vormonats mit kWh und Kosten "
                    "verschicken – z. B. an die Person, die den Hausstrom bezahlt.",
     "fields": [
        _b("mail_enabled", "Monatsbericht am 1. per E-Mail senden",
           help="Braucht „Monatsbericht (PDF) am 1. erstellen“ unter Benachrichtigungen."),
        _s("mail_provider", "Mail-Anbieter", {
            "gmail": "Gmail", "gmx": "GMX", "webde": "web.de", "tonline": "T-Online",
            "icloud": "iCloud", "outlook": "Outlook / Hotmail", "custom": "eigener Server"}),
        _f("mail_host", "Mailserver (SMTP)", "text", show_if={"mail_provider": "custom"}),
        _n("mail_port", "Port", 1, 65535, 1, show_if={"mail_provider": "custom"}),
        _s("mail_security", "Verschlüsselung", {"starttls": "STARTTLS (meist Port 587)",
                                                "ssl": "SSL/TLS (meist Port 465)",
                                                "none": "keine"},
           show_if={"mail_provider": "custom"}),
        _f("mail_user", "Benutzername (deine Mailadresse)", "text"),
        _f("mail_password", "Passwort", "password",
           help="Gmail und iCloud: ein App-Passwort, nicht das normale Passwort "
                "(Gmail: myaccount.google.com/apppasswords, 2-Faktor-Anmeldung nötig)."),
        _f("mail_from", "Absender (leer = Benutzername)", "text", advanced=True),
        _f("mail_to_1", "Empfänger 1", "text"),
        _f("mail_to_2", "Empfänger 2 (optional)", "text"),
        _f("report_push_targets", "Betrag zusätzlich per Push an", "text", suggest="notify",
           help="Push-Ziele, kommagetrennt, z. B. notify.mobile_app_iphone_von_melanie. "
                "Sie bekommen am 1. die kWh und den Betrag des Vormonats."),
    ]},
    {"id": "climate", "title": "Vorklimatisierung", "icon": "mdi:fan",
     "description": "Das Auto vor der Abfahrt heizen oder kühlen (braucht „Lesen & Schreiben“).",
     "fields": [
        _b("climate_enabled", "Vorklimatisierung vor der Abfahrt"),
        _n("climate_min_soc_pct", "Nur ab einem Akkustand von", 20, 100, 1, "%",
           show_if={"climate_enabled": True}),
        _s("climate_after_target_soc", "Wenn das Ladeziel schon erreicht ist",
           {ClimateAfterTarget.ALLOW_TOPUP: "Wallbox freigeben (Strom aus dem Netz)",
            ClimateAfterTarget.BATTERY_ONLY: "Nur aus dem Akku",
            ClimateAfterTarget.ENFORCE_TARGET: "Ziel-SOC strikt einhalten"},
           show_if={"climate_enabled": True}),
        _n("climate_very_cold_below_c", "Sehr kalt unter", -20, 30, 0.5, "°C", advanced=True,
           show_if={"climate_enabled": True}),
        _n("climate_very_cold_min", "… dann klimatisieren für", 0, 15, 5, "min",
           advanced=True, show_if={"climate_enabled": True}),
        _n("climate_cold_below_c", "Kalt unter", -20, 30, 0.5, "°C", advanced=True,
           show_if={"climate_enabled": True}),
        _n("climate_cold_min", "… dann klimatisieren für", 0, 15, 5, "min", advanced=True,
           show_if={"climate_enabled": True}),
        _n("climate_cool_below_c", "Kühl unter", -20, 30, 0.5, "°C", advanced=True,
           show_if={"climate_enabled": True}),
        _n("climate_cool_min", "… dann klimatisieren für", 0, 15, 5, "min", advanced=True,
           show_if={"climate_enabled": True}),
        _n("climate_warm_above_c", "Warm über", 10, 45, 0.5, "°C", advanced=True,
           show_if={"climate_enabled": True}),
        _n("climate_warm_min", "… dann klimatisieren für", 0, 15, 5, "min", advanced=True,
           show_if={"climate_enabled": True}),
    ]},
    {"id": "vehicle", "title": "Fahrzeug und Wallbox", "icon": "mdi:ev-station",
     "description": "Für die Ladeprognose: Akkugröße und Ladegeschwindigkeit.",
     "fields": [
        _n("usable_capacity_kwh", "Nutzbare Akkukapazität", 5, 150, 0.1, "kWh"),
        _n("vehicle_charger_kw", "Ladeleistung des Fahrzeugs (AC)", 1, 22, 0.1, "kW",
           help="Bordlader des Autos – smart 453: 4,6 kW Serie, 22 kW mit Schnelllader. "
                "Zuhause begrenzt die Wallbox (z. B. 11 kW dreiphasig)."),
        _n("max_power_kw", "Leistung der Wallbox", 1, 22, 0.1, "kW"),
        _n("default_current_a", "Standard-Ladestrom (0 = Wallbox-Einstellung lassen)", 0, 32, 1,
           "A", help="Gilt für Pläne ohne eigenen Ladestrom. 12 A ≈ 8 kW, 16 A ≈ 11 kW "
                     "(dreiphasig). Weniger Strom ist schonender für den Akku."),
        _n("phases", "Phasen der Wallbox", 1, 3, 1, advanced=True,
           help="Zum Umrechnen von Ampere in kW (Halo 11 kW: 3 Phasen)."),
        _n("grid_limit_kw", "Netzbetreiber-Limit §14a (0 = keins)", 0, 22, 0.1, "kW",
           help="Nur falls der Netzbetreiber die Wallbox dimmen darf (z. B. 4,2 kW)."),
        _n("charge_efficiency", "Ladewirkungsgrad", 0.5, 1, 0.01, advanced=True),
        _n("taper_from_pct", "Lädt langsamer ab Ladestand", 50, 100, 5, "%",
           help="Kurz vor voll nimmt jedes Auto weniger Leistung auf (smart 453: ab ca. 80 %). "
                "Der Plan startet dann entsprechend früher."),
        _b("learn_charging", "Aus eigenen Ladungen lernen",
           help="Nach drei Ladungen ersetzen gemessene Werte (kWh je % und echte Ladeleistung) "
                "die Nennwerte – die Startzeit wird genauer."),
    ]},
    {"id": "external", "title": "Fremdladen", "icon": "mdi:map-marker-radius",
     "description": "Ladungen außer Haus, z. B. an öffentlichen Säulen.",
     "fields": [
        _b("external_detection", "Fremdladungen automatisch erkennen",
           help="Erkennung aus den Fahrzeugdaten – das Auto wird dafür nie geweckt."),
        _n("external_price_eur_kwh", "Angenommener Preis für erkannte Ladungen", 0, 2, 0.01,
           "€/kWh", show_if={"external_detection": True}),
        _f("external_price_buttons", "Preis-Knöpfe in der Push-Nachricht", "text",
           help="Bis zu vier Preise in €/kWh, getrennt mit Semikolon, z. B. 0,39; 0,49; 0,59; "
                "0,69. Ein Tipp auf einen Knopf speichert den Preis.",
           show_if={"external_detection": True}),
        _n("external_min_kwh", "Mindestmenge", 0.2, 20, 0.1, "kWh", advanced=True,
           show_if={"external_detection": True}),
        _n("external_soc_jump_pct", "SOC-Sprung ohne Heimladen ab", 2, 50, 1, "%",
           advanced=True, show_if={"external_detection": True}),
    ]},
    {"id": "monitor", "title": "Statistik", "icon": "mdi:chart-line",
     "description": "Woher die Kilometer kommen und wie lange Daten aufbewahrt werden.",
     "fields": [
        _s("odometer_source", "Kilometerstand", {
            OdometerSource.AUTO: "automatisch (Fahrzeugdaten, sonst manuell)",
            OdometerSource.OVMS: "aus den Fahrzeugdaten",
            OdometerSource.MANUAL: "manuell eintragen"}),
        _n("trip_merge_gap_min", "Kurze Stopps zu einer Fahrt zusammenfassen bis", 1, 120, 1,
           "min", advanced=True),
        _n("event_retention_days", "Ereignisse aufbewahren", 7, 730, 1, "Tage", advanced=True),
        _n("interval_min", "Energie-Intervall für Kosten", 5, 60, 5, "min", advanced=True),
    ]},
    {"id": "wakeup", "title": "Wecken und CP-Unterbrechung", "icon": "mdi:sleep-off",
     "description": "Wie ein schlafendes Auto zum Laden geweckt wird.",
     "fields": [
        _b("cp_failsafe_verified", "Sicherheits-Checkliste der CP-Unterbrechung erledigt",
           help="Erst danach darf der Shelly die CP-Leitung kurz unterbrechen (Masterplan §3.6)."),
        _b("cp_fallback_enabled", "CP-Puls nutzen, wenn das Auto nicht anders aufwacht",
           advanced=True),
        _n("start_detection_wait_s", "Warten auf Ladebeginn, bevor geweckt wird", 15, 900, 5,
           "s", advanced=True),
        _n("ovms_wait_s", "Warten nach dem Wecken über das Fahrzeug", 10, 600, 5, "s",
           advanced=True),
        _n("post_cp_wait_s", "Warten nach dem CP-Puls", 15, 900, 5, "s", advanced=True),
        _n("max_ovms_attempts_per_window", "Weckversuche über das Fahrzeug pro Nacht", 0, 3,
           advanced=True),
        _n("max_cp_attempts_per_window", "CP-Pulse pro Nacht", 0, 3, advanced=True),
        _n("min_gap_between_wakeups_s", "Mindestabstand zwischen zwei Weckversuchen", 30, 1800,
           10, "s", advanced=True),
        _n("cp_pulse_s", "Dauer des CP-Pulses", 5, 15, 1, "s", advanced=True,
           help="Muss der Auto-On-Verzögerung im Shelly entsprechen."),
        _n("cp_mask_grace_s", "Wallbox-Meldungen nach dem Puls ignorieren", 0, 300, 5, "s",
           advanced=True),
    ]},
    {"id": "charging", "title": "Ladeerkennung", "icon": "mdi:flash-outline",
     "description": "Ab wann die Integration „lädt“ erkennt – nur nach der Messphase anpassen.",
     "advanced": True,
     "fields": [
        _n("manual_target_soc", "Ziel bei „Jetzt laden“", 20, 100, 5, "%", hidden=True),
        _n("power_threshold_w", "Ab dieser Leistung gilt „lädt“", 50, 3000, 10, "W",
           advanced=True),
        _n("stable_samples", "Messwerte, bis eine Ladung als stabil gilt", 1, 10,
           advanced=True),
        _n("stable_min_s", "Mindestdauer bis stabil", 0, 600, 1, "s", advanced=True),
        _n("loss_timeout_s", "Ladung gilt als abgebrochen nach", 30, 1800, 10, "s",
           advanced=True),
        _n("min_switch_interval_s", "Mindestpause zwischen Wallbox-Schaltungen", 30, 900, 10,
           "s", advanced=True),
        _n("confirm_timeout_s", "Warten auf Bestätigung der Wallbox", 15, 600, 5, "s",
           advanced=True),
        _f("finished_statuses", "Wallbox-Status für „voll“ (kommagetrennt)", "text",
           advanced=True, help="Aus der Messphase, z. B. Finished"),
    ]},
    {"id": "quality", "title": "Datenqualität", "icon": "mdi:database-check-outline",
     "description": "Wie alt Messwerte sein dürfen, bevor sie als veraltet gelten.",
     "advanced": True,
     "fields": [
        _n("max_age_halo_power_s", "Wallbox-Leistung", 30, 3600, 10, "s", advanced=True),
        _n("max_age_halo_energy_s", "Wallbox-Zähler", 60, 7200, 10, "s", advanced=True),
        _n("max_age_vehicle_charging_s", "Ladezustand des Fahrzeugs", 30, 3600, 10, "s",
           advanced=True),
        _n("max_age_soc_s", "SOC beim Laden", 60, 7200, 10, "s", advanced=True),
        _n("max_age_odometer_s", "Kilometerstand", 60, 86400, 60, "s", advanced=True),
        _n("max_age_temperature_s", "Temperaturen", 60, 7200, 10, "s", advanced=True),
        _n("hv_cycles_warn_per_day", "Warnung ab HV-Zyklen pro Tag", 1, 100, advanced=True),
    ]},
    {"id": "ovms", "title": "OVMS-Befehle", "icon": "mdi:console",
     "description": "Die Befehle, die ans Fahrzeug gehen – vorbelegt, normalerweise nichts ändern.",
     "advanced": True,
     "fields": [
        _f("ovms_wakeup_command", "Wecken", "text", advanced=True,
           help="„auto“ = xsq wakeup beim smart 453, sonst wakeup."),
        _f("ovms_climate_command", "Klima starten ({level} = 1/2/3 für 5/10/15 min)", "text",
           advanced=True),
        _f("ovms_climate_stop_command", "Klima stoppen", "text", advanced=True),
    ]},
]

FIELDS = {f["key"]: f for g in GROUPS for f in g["fields"]}


def current_values(options: dict[str, Any]) -> dict[str, Any]:
    values = {**DEFAULT_OPTIONS, **options}
    history = values[OPT_PRICE_HISTORY]
    out = {key: values.get(key) for key in FIELDS if key in values}
    out["vehicle_name"] = options.get("vehicle_name") or "Mein EV"
    out[PRICE_FIELD] = float(history[-1]["eur_per_kwh"])
    out[PRICE_VALID_FROM] = str(history[-1]["valid_from"])
    for key, field in FIELDS.items():
        if field["type"] == "password":
            # A stored secret never travels back to the browser.
            out[f"{key}_set"] = bool(out.get(key))
            out[key] = ""
    return out


def _coerce(field: dict[str, Any], value: Any) -> Any:
    kind = field["type"]
    if kind == "bool":
        return bool(value)
    if kind == "number":
        number = float(value)
        if not field["min"] <= number <= field["max"]:
            raise ValueError(f"{field['label']}: {number} liegt nicht zwischen "
                             f"{field['min']} und {field['max']}")
        return int(number) if float(field["step"]).is_integer() and number.is_integer() \
            else number
    if kind == "select":
        allowed = {o["value"] for o in field["options"]}
        if value not in allowed:
            raise ValueError(f"{field['label']}: ungültige Auswahl {value}")
        return value
    if field["key"] == "vehicle_name":
        return str(value or "").strip()[:40]
    if kind == "date":
        return date.fromisoformat(str(value)).isoformat()
    if kind == "time":
        text = str(value)
        return text if len(text) == 8 else f"{text}:00"
    return "" if value is None else str(value)


def apply_changes(options: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Validate ``changes`` and return the new options dict."""
    new = dict(options)
    price = changes.pop(PRICE_FIELD, None)
    valid_from = changes.pop(PRICE_VALID_FROM, None)
    for key, value in changes.items():
        if key not in FIELDS:
            raise ValueError(f"Unbekannte Einstellung {key}")
        if FIELDS[key]["type"] == "password" and not value:
            continue  # empty = keep the stored password
        new[key] = _coerce(FIELDS[key], value)
    if price is not None or valid_from is not None:
        history = list(new.get(OPT_PRICE_HISTORY) or DEFAULT_OPTIONS[OPT_PRICE_HISTORY])
        last = history[-1]
        price = float(price) if price is not None else float(last["eur_per_kwh"])
        _coerce(FIELDS[PRICE_FIELD], price)
        valid_from = _coerce(FIELDS[PRICE_VALID_FROM], valid_from or last["valid_from"])
        if price != float(last["eur_per_kwh"]) or valid_from != str(last["valid_from"]):
            # A new price never rewrites old months (§11): add an entry, keep the rest.
            history = [p for p in history if str(p["valid_from"]) != valid_from]
            history.append({"valid_from": valid_from, "eur_per_kwh": price})
            history.sort(key=lambda p: str(p["valid_from"]))
            new[OPT_PRICE_HISTORY] = history
    if new.get("price_source") == PriceSource.ENTITY and not new.get("price_entity"):
        raise ValueError("Für die Preisquelle „Preis-Entität“ bitte eine Entität wählen.")
    return new
