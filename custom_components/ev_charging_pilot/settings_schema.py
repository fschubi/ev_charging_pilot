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
    {"id": "general", "title": "Allgemein", "fields": [
        _f("vehicle_name", "Name deines Fahrzeugs", "text",
           help="Erscheint als „<Name> Charging Pilot“ in Seitenleiste, Panel, Gerät, "
                "Push und PDF."),
        _b("ovms_enabled", "Fahrzeug: Lesen & Schreiben (aus = nur lesen)",
           help="Aus: Fahrzeugdaten werden nur gelesen. An: Wakeup und Vorklimatisierung "
                "werden ans Auto gesendet – der Befehlsweg (OVMS-Integration) wird "
                "automatisch erkannt. Erst einschalten, wenn du es testen willst."),
    ]},
    {"id": "charging", "title": "Laden", "fields": [
        _n("manual_target_soc", "Ziel bei „Jetzt laden“ (100 = voll)", 20, 100, 5, "%"),
        _s("mode", "Betriebsmodus", {RunMode.DRY_RUN: "Dry-Run (nur protokollieren)",
                                     RunMode.LIVE: "Live (schaltet Hardware)",
                                     RunMode.REPLAY: "Replay (keine Hardware)"},
           help="Live erst nach Messphase und Einzeltest."),
        _n("power_threshold_w", "Leistungsschwelle „lädt“", 50, 3000, 10, "W"),
        _n("stable_samples", "Stabile Messwerte (N)", 1, 10),
        _n("stable_min_s", "Mindestdauer stabil", 0, 600, 1, "s"),
        _n("loss_timeout_s", "Ladeverlust-Timeout", 30, 1800, 10, "s"),
        _n("min_switch_interval_s", "Mindestpause zwischen Wallbox-Schaltungen", 30, 900, 10, "s"),
        _n("confirm_timeout_s", "Wartezeit auf Wallbox-Bestätigung", 15, 600, 5, "s"),
        _f("finished_statuses", "Wallbox-Status „fertig“ (kommagetrennt)", "text",
           help="Nach Messung M3 eintragen, z. B. Finished"),
    ]},
    {"id": "wakeup", "title": "Wakeup und CP", "fields": [
        _n("start_detection_wait_s", "Wartezeit bis Wakeup", 15, 900, 5, "s"),
        _n("ovms_wait_s", "Wartezeit nach OVMS-Wakeup", 10, 600, 5, "s"),
        _b("cp_fallback_enabled", "CP-Puls als Rückfall"),
        _n("post_cp_wait_s", "Wartezeit nach CP-Puls", 15, 900, 5, "s"),
        _n("max_ovms_attempts_per_window", "Max. OVMS-Versuche je Nacht", 0, 3),
        _n("max_cp_attempts_per_window", "Max. CP-Versuche je Nacht", 0, 3),
        _n("min_gap_between_wakeups_s", "Mindestabstand zwischen Wakeups", 30, 1800, 10, "s"),
        _n("cp_pulse_s", "CP-Pulsdauer", 5, 15, 1, "s",
           help="Wird als toggle_after gesendet und muss der Auto-On-Verzögerung entsprechen."),
        _n("cp_mask_grace_s", "Maskierung nach dem Puls", 0, 300, 5, "s"),
        _b("cp_failsafe_verified", "CP-Failsafe-Checkliste §3.6 vollständig erledigt",
           help="Erst danach ist der CP-Wakeup freigegeben."),
    ]},
    {"id": "planning", "title": "Planung", "fields": [
        _n("usable_capacity_kwh", "Nutzbare Akkukapazität", 5, 30, 0.1, "kWh"),
        _n("charge_efficiency", "Ladewirkungsgrad", 0.5, 1, 0.01),
        _n("max_power_kw", "Wallbox-Limit", 1, 22, 0.1, "kW"),
        _n("vehicle_charger_kw", "Fahrzeuglader", 1, 22, 0.1, "kW"),
        _n("grid_limit_kw", "Netzlimit §14a (0 = keins)", 0, 22, 0.1, "kW"),
        _n("safety_margin_min", "Sicherheitsreserve", 0, 180, 5, "min"),
    ]},
    {"id": "prices", "title": "Strompreis", "fields": [
        _n(PRICE_FIELD, "Arbeitspreis (Festpreis)", 0, 2, 0.001, "€/kWh",
           help="Gilt ohne dynamischen Tarif und als Rückfall."),
        _f(PRICE_VALID_FROM, "Preis gültig ab", "date",
           help="Ein neuer Preis ändert keine alten Monate."),
        _s("price_source", "Preisquelle", {PriceSource.FIXED: "Festpreis",
                                           PriceSource.ENTITY: "Preis-Entität",
                                           PriceSource.TIBBER: "Tibber"}),
        _f("price_entity", "Preis-Entität (Nordpool, EPEX …)", "entity", domain="sensor"),
        _b("price_optimization", "In den günstigsten Stunden laden"),
        _n("price_blocks", "Max. Ladeblöcke pro Nacht", 1, 2),
    ]},
    {"id": "climate", "title": "Vorklimatisierung", "fields": [
        _b("climate_enabled", "Vorklimatisierung aktiv"),
        _n("climate_min_soc_pct", "Mindest-SOC für Klima", 20, 100, 1, "%"),
        _s("climate_after_target_soc", "Nach erreichtem Ziel-SOC",
           {ClimateAfterTarget.ALLOW_TOPUP: "Nachladen erlauben",
            ClimateAfterTarget.BATTERY_ONLY: "Nur aus dem Akku",
            ClimateAfterTarget.ENFORCE_TARGET: "Ziel-SOC durchsetzen"}),
        _n("climate_very_cold_below_c", "Sehr kalt unter", -20, 30, 0.5, "°C"),
        _n("climate_very_cold_min", "Dauer sehr kalt", 0, 15, 5, "min"),
        _n("climate_cold_below_c", "Kalt unter", -20, 30, 0.5, "°C"),
        _n("climate_cold_min", "Dauer kalt", 0, 15, 5, "min"),
        _n("climate_cool_below_c", "Kühl unter", -20, 30, 0.5, "°C"),
        _n("climate_cool_min", "Dauer kühl", 0, 15, 5, "min"),
        _n("climate_warm_above_c", "Warm über", 10, 45, 0.5, "°C"),
        _n("climate_warm_min", "Dauer warm", 0, 15, 5, "min"),
    ]},
    {"id": "quality", "title": "Datenqualität", "fields": [
        _n("max_age_halo_power_s", "Max. Alter Wallbox-Leistung", 30, 3600, 10, "s"),
        _n("max_age_halo_energy_s", "Max. Alter Wallbox-Zähler", 60, 7200, 10, "s"),
        _n("max_age_vehicle_charging_s", "Max. Alter Ladezustand Fahrzeug", 30, 3600, 10, "s"),
        _n("max_age_soc_s", "Max. Alter SOC beim Laden", 60, 7200, 10, "s"),
        _n("max_age_odometer_s", "Max. Alter Kilometerstand", 60, 86400, 60, "s"),
        _n("max_age_temperature_s", "Max. Alter Temperaturen", 60, 7200, 10, "s"),
    ]},
    {"id": "notifications", "title": "Benachrichtigungen", "fields": [
        _f("plug_reminder_time", "Uhrzeit Abend-Erinnerung", "time"),
        _b("notify_start_failed", "Ladestart fehlgeschlagen / Abbruch"),
        _b("notify_cp", "CP-Probleme (kritisch)"),
        _b("notify_plan_infeasible", "Mindest-SOC nicht erreichbar"),
        _b("notify_plug_reminder", "Abends nicht eingesteckt"),
        _b("notify_health", "Health-Wechsel"),
        _b("notify_hv_cycles", "HV-Kontaktor auffällig"),
        _b("notify_plug_in_action", "Rückfrage beim Einstecken"),
        _b("notify_external", "Fremdladung erkannt"),
        _b("report_auto_monthly", "Monatsbericht (PDF) am 1. erstellen"),
        _b("notify_report", "Monatsbericht erstellt"),
    ]},
    {"id": "monitor", "title": "Statistik", "fields": [
        _s("odometer_source", "Kilometerquelle", {OdometerSource.MANUAL: "Manuell",
                                                  OdometerSource.OVMS: "OVMS"}),
        _n("trip_merge_gap_min", "Fahrten zusammenfassen bis", 1, 120, 1, "min"),
        _n("event_retention_days", "Ereignisse aufbewahren", 7, 730, 1, "Tage"),
        _n("hv_cycles_warn_per_day", "HV-Zyklen-Warnschwelle pro Tag", 1, 100),
        _n("interval_min", "Energie-Intervall", 5, 60, 5, "min"),
    ]},
    {"id": "external", "title": "Fremdladen", "fields": [
        _b("external_detection", "Fremdladungen automatisch erkennen"),
        _n("external_min_kwh", "Mindestmenge", 0.2, 20, 0.1, "kWh"),
        _n("external_soc_jump_pct", "SOC-Sprung ohne Heimladen ab", 2, 50, 1, "%"),
        _n("external_price_eur_kwh", "Angenommener Preis für erkannte Ladungen", 0, 2, 0.01,
           "€/kWh", help="Wird bei automatisch erkannten Ladungen vorgeschlagen."),
    ]},
    {"id": "ovms", "title": "OVMS-Befehle (nur für Experten)", "fields": [
        _f("ovms_wakeup_command", "Wakeup-Befehl", "text",
           help="Vorbelegt mit den OVMS-v3-Standardbefehlen – normalerweise nichts ändern."),
        _f("ovms_climate_command", "Klimabefehl ({level} = 1/2/3)", "text"),
        _f("ovms_climate_stop_command", "Klima-Stopp-Befehl", "text"),
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
