"""Generate strings.json + translations/{de,en}.json from one table.

Usage: python3 tools/gen_translations.py custom_components/ev_charging_pilot
"""

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])

# (de, en)
def T(de, en):
    return {"de": de, "en": en}


INPUTS = {
    "charger_enable": T("Wallbox Ladefreigabe (Switch)", "Wallbox charging enable (switch)"),
    "cable_connected": T("Wallbox Kabel gesteckt", "Wallbox cable connected"),
    "charge_power": T("Wallbox Ladeleistung", "Wallbox charging power"),
    "total_energy": T("Wallbox Gesamtenergiezähler", "Wallbox total energy meter"),
    "charger_status": T("Wallbox Status", "Wallbox status"),
    "max_current": T("Wallbox Maximalstrom", "Wallbox max current"),
    "cable_lock": T("Wallbox Kabelverriegelung", "Wallbox cable lock"),
    "internal_schedule": T("Wallbox interner Zeitplan (muss aus bleiben)",
                           "Wallbox internal schedule (must stay off)"),
    "cp_relay": T("Shelly CP-Relais", "Shelly CP relay"),
    "shelly_host": T("Shelly IP/Hostname (für Puls und Drift-Check)",
                     "Shelly IP/hostname (pulse and drift check)"),
    "notify_service": T("Push-Ziel (notify.mobile_app_…)", "Push target (notify.mobile_app_…)"),
    "ovms_soc": T("Fahrzeug: SOC", "Vehicle: SOC"),
    "ovms_soh": T("Fahrzeug: SOH", "Vehicle: SOH"),
    "ovms_range": T("Fahrzeug: Reichweite", "Vehicle: range"),
    "ovms_odometer": T("Fahrzeug: Kilometerstand", "Vehicle: odometer"),
    "ovms_charging": T("Fahrzeug: lädt", "Vehicle: charging"),
    "ovms_charge_power": T("Fahrzeug: Ladeleistung (fahrzeugseitig)", "Vehicle: vehicle-side charge power"),
    "ovms_battery_temp": T("Fahrzeug: Batterietemperatur", "Vehicle: battery temperature"),
    "ovms_hv_cycles": T("Fahrzeug: HV-Kontaktorzyklen", "Vehicle: HV contactor cycles"),
    "ovms_vehicle_on": T("Fahrzeug: fahrbereit / eingeschaltet", "Vehicle: ready to drive"),
    "ovms_outside_temp": T("Fahrzeug: Außentemperatur", "Vehicle: outside temperature"),
    "ovms_energy_used": T("Fahrzeug: Fahrtenergie verbraucht", "Vehicle: trip energy used"),
    "ovms_energy_recd": T("Fahrzeug: Rekuperation", "Vehicle: energy recovered"),
    "ovms_aux_consumption": T("Fahrzeug: Nebenverbrauch", "Vehicle: auxiliary consumption"),
    "ovms_12v": T("Fahrzeug: 12-V-Spannung", "Vehicle: 12 V voltage"),
    "outside_temp": T("Außentemperatur (HA-Sensor)", "Outside temperature (HA sensor)"),
    "weather": T("Wetter (Rückfall Außentemperatur)", "Weather (fallback outside temperature)"),
    "ovms_command_topic": T("OVMS-Befehls-Topic (MQTT)", "OVMS command topic (MQTT)"),
    "ovms_command_script": T("Oder: Script für OVMS-Befehle (Variable command)",
                             "Or: script for OVMS commands (variable command)"),
}

FIELD_HELP = {
    "charger_enable": T("Der Schalter der Chargeamps-Integration, der das Laden freigibt "
                        "(meist switch.…_connector_1).",
                        "The Chargeamps switch that enables charging (usually …_connector_1)."),
    "cable_connected": T("Meldet, ob das Ladekabel am Auto steckt (binary_sensor.…_cable_connected).",
                         "Reports whether the cable is plugged in."),
    "charge_power": T("Aktuelle Ladeleistung des Anschlusses in W oder kW (nicht L1/L2/L3).",
                      "Current charging power of the connector (not a single phase)."),
    "total_energy": T("Gesamtzähler der Wallbox in kWh – Grundlage der Hausabrechnung.",
                      "Total energy meter of the wallbox in kWh."),
    "charger_status": T("Statustext des Anschlusses (z. B. Charging, Available). Optional.",
                        "Status text of the connector. Optional."),
    "max_current": T("Maximalstrom des Anschlusses. Optional, nur zur Anzeige.",
                     "Maximum current of the connector. Optional."),
    "cable_lock": T("Kabelverriegelung. Optional, nur zur Anzeige.", "Cable lock. Optional."),
    "internal_schedule": T("Interner Zeitplan der Wallbox. Optional – wird überwacht, damit er aus bleibt.",
                           "Internal Wallbox schedule. Optional – monitored so it stays off."),
    "cp_relay": T("Das Shelly-Relais in der CP-Leitung (ON = CP geschlossen). Leer lassen, "
                  "wenn kein Shelly verbaut ist.",
                  "The Shelly relay in the CP line. Leave empty without a Shelly."),
    "shelly_host": T("IP-Adresse des Shelly für den Puls mit Selbstrückstellung. Wird aus der "
                     "Shelly-Integration übernommen.",
                     "Shelly IP for the self-resetting pulse; taken from the Shelly integration."),
    "notify_service": T("Dein Handy aus der Companion-App (notify.mobile_app_…). Leer = keine Pushes.",
                        "Your phone from the companion app. Empty = no pushes."),
    "outside_temp": T("Außentemperatur-Sensor für die Klimaprofile. Optional.",
                      "Outside temperature sensor for climate profiles. Optional."),
    "weather": T("Wetter-Entität als Rückfall für die Außentemperatur. Optional.",
                 "Weather entity as fallback for the outside temperature. Optional."),
    "ovms_command_topic": T("MQTT-Topic, über das OVMS Befehle annimmt. Erst nach dem Test am "
                            "Auto eintragen.", "MQTT topic for OVMS commands; only after testing."),
    "ovms_command_script": T("Alternativ ein Script, das den OVMS-Befehl ausführt (Variable command).",
                             "Alternatively a script that runs the OVMS command."),
}

OPTIONS = {
    "mode": T("Betriebsmodus", "Run mode"),
    "power_threshold_w": T("Leistungsschwelle „lädt“", "Power threshold 'charging'"),
    "stable_samples": T("Stabile Messwerte (N)", "Stable samples (N)"),
    "stable_min_s": T("Mindestdauer stabil", "Minimum stable duration"),
    "loss_timeout_s": T("Ladeverlust-Timeout", "Charging loss timeout"),
    "min_switch_interval_s": T("Mindestpause zwischen Wallbox-Schaltungen",
                               "Minimum pause between Wallbox switches"),
    "confirm_timeout_s": T("Wartezeit auf Wallbox-Bestätigung", "Wait for Wallbox confirmation"),
    "finished_statuses": T("Wallbox-Status „fertig“ (kommagetrennt, nach Messung)",
                           "Wallbox status values meaning finished (comma separated)"),
    "start_detection_wait_s": T("Wartezeit bis Wakeup", "Wait before wakeup"),
    "ovms_enabled": T("Befehle ans Fahrzeug erlauben (OVMS-Wakeup, Klima) – erst nach Test",
                      "Allow commands to the vehicle (OVMS wakeup, climate) – only after testing"),
    "ovms_wait_s": T("Wartezeit nach OVMS-Wakeup", "Wait after OVMS wakeup"),
    "cp_fallback_enabled": T("CP-Puls als Rückfall", "CP pulse as fallback"),
    "post_cp_wait_s": T("Wartezeit nach CP-Puls", "Wait after CP pulse"),
    "max_ovms_attempts_per_window": T("Max. OVMS-Versuche je Fenster",
                                      "Max OVMS attempts per window"),
    "max_cp_attempts_per_window": T("Max. CP-Versuche je Fenster", "Max CP attempts per window"),
    "min_gap_between_wakeups_s": T("Mindestabstand zwischen Wakeups",
                                   "Minimum gap between wakeups"),
    "cp_pulse_s": T("CP-Pulsdauer (= toggle_after = auto_on_delay)",
                    "CP pulse length (= toggle_after = auto_on_delay)"),
    "cp_mask_grace_s": T("Maskierung nach dem Puls", "Masking after the pulse"),
    "cp_failsafe_verified": T("CP-Failsafe-Checkliste §3.6 vollständig erledigt",
                              "CP failsafe checklist §3.6 completed"),
    "usable_capacity_kwh": T("Nutzbare Akkukapazität", "Usable battery capacity"),
    "charge_efficiency": T("Ladewirkungsgrad", "Charging efficiency"),
    "max_power_kw": T("Wallbox-Limit", "Wallbox limit"),
    "vehicle_charger_kw": T("Fahrzeuglader", "On-board charger"),
    "grid_limit_kw": T("Netzlimit §14a (0 = keins)", "Grid limit §14a (0 = none)"),
    "safety_margin_min": T("Sicherheitsreserve", "Safety margin"),
    "climate_enabled": T("Vorklimatisierung aktiv", "Pre-climatisation enabled"),
    "climate_min_soc_pct": T("Mindest-SOC für Klima", "Minimum SOC for climate"),
    "climate_after_target_soc": T("Klima nach erreichtem Ziel-SOC", "Climate after target SOC"),
    "climate_very_cold_below_c": T("Sehr kalt unter", "Very cold below"),
    "climate_very_cold_min": T("Dauer sehr kalt", "Duration very cold"),
    "climate_cold_below_c": T("Kalt unter", "Cold below"),
    "climate_cold_min": T("Dauer kalt", "Duration cold"),
    "climate_cool_below_c": T("Kühl unter", "Cool below"),
    "climate_cool_min": T("Dauer kühl", "Duration cool"),
    "climate_warm_above_c": T("Warm über", "Warm above"),
    "climate_warm_min": T("Dauer warm", "Duration warm"),
    "max_age_halo_power_s": T("Max. Alter Wallbox-Leistung (3 × Poll-Intervall)",
                              "Max age Wallbox power (3 × poll interval)"),
    "max_age_halo_energy_s": T("Max. Alter Wallbox-Zähler", "Max age Wallbox meter"),
    "max_age_vehicle_charging_s": T("Max. Alter Ladezustand Fahrzeug",
                                    "Max age vehicle charging state"),
    "max_age_soc_s": T("Max. Alter SOC beim Laden", "Max age SOC while charging"),
    "max_age_odometer_s": T("Max. Alter Kilometerstand", "Max age odometer"),
    "max_age_temperature_s": T("Max. Alter Temperaturen", "Max age temperatures"),
    "plug_reminder_time": T("Uhrzeit Abend-Erinnerung", "Evening reminder time"),
    "notify_start_failed": T("Push: Ladestart fehlgeschlagen / Abbruch",
                             "Push: start failed / interrupted"),
    "notify_cp": T("Push: CP-Probleme (kritisch)", "Push: CP problems (critical)"),
    "notify_plan_infeasible": T("Push: Mindest-SOC nicht erreichbar",
                                "Push: minimum SOC not reachable"),
    "notify_plug_reminder": T("Push: abends nicht eingesteckt", "Push: not plugged in"),
    "notify_health": T("Push: Health-Wechsel", "Push: health changes"),
    "notify_hv_cycles": T("Push: HV-Kontaktor auffällig", "Push: HV contactor warning"),
    "notify_plug_in_action": T("Push mit Auswahl beim Einstecken",
                               "Actionable push when plugging in"),
    "odometer_source": T("Kilometerquelle", "Odometer source"),
    "trip_merge_gap_min": T("Fahrten zusammenfassen bis", "Merge trips within"),
    "event_retention_days": T("Ereignisse aufbewahren", "Keep events"),
    "hv_cycles_warn_per_day": T("HV-Zyklen-Warnschwelle pro Tag", "HV cycle warning per day"),
    "interval_min": T("Energie-Intervall", "Energy interval"),
    "price_eur_kwh": T("Arbeitspreis", "Energy price"),
    "price_valid_from": T("Preis gültig ab", "Price valid from"),
    "price_source": T("Preisquelle", "Price source"),
    "price_entity": T("Preis-Entität (Nordpool, EPEX, Tibber-Sensor …)",
                      "Price entity (Nordpool, EPEX, Tibber sensor …)"),
    "price_optimization": T("In den günstigsten Stunden laden", "Charge in the cheapest hours"),
    "price_blocks": T("Max. Ladeblöcke pro Nacht (jeder Block kann einen Wakeup kosten)",
                      "Max charging blocks per night (each may need a wakeup)"),
    "external_detection": T("Fremdladungen automatisch erkennen",
                            "Detect external charges automatically"),
    "external_min_kwh": T("Mindestmenge für eine Fremdladung",
                          "Minimum energy of an external charge"),
    "external_soc_jump_pct": T("SOC-Sprung ohne Heimladen ab",
                               "SOC jump without home charging from"),
    "external_price_eur_kwh": T("Angenommener Preis für erkannte Fremdladungen",
                                "Assumed price for detected external charges"),
    "notify_external": T("Push: Fremdladung erkannt", "Push: external charge detected"),
    "report_auto_monthly": T("Monatsbericht (PDF) automatisch am 1. erstellen",
                             "Create the monthly PDF report on the 1st"),
    "notify_report": T("Push: Monatsbericht erstellt", "Push: monthly report created"),
    "ovms_wakeup_command": T("OVMS-Wakeup-Befehl (leer = gesperrt)",
                             "OVMS wakeup command (empty = locked)"),
    "ovms_climate_command": T("OVMS-Klimabefehl ({level} = 1/2/3, {minutes})",
                              "OVMS climate command ({level} = 1/2/3, {minutes})"),
    "ovms_climate_stop_command": T("OVMS-Klima-Stopp-Befehl", "OVMS climate stop command"),
}

OPTION_STEPS = {
    "charging": (T("Laden", "Charging"), ["mode", "power_threshold_w", "stable_samples",
                 "stable_min_s", "loss_timeout_s", "min_switch_interval_s", "confirm_timeout_s",
                 "finished_statuses"]),
    "wakeup": (T("Wakeup und CP", "Wakeup and CP"), ["start_detection_wait_s", "ovms_enabled",
               "ovms_wait_s", "cp_fallback_enabled", "post_cp_wait_s",
               "max_ovms_attempts_per_window", "max_cp_attempts_per_window",
               "min_gap_between_wakeups_s", "cp_pulse_s", "cp_mask_grace_s",
               "cp_failsafe_verified"]),
    "planning": (T("Planung", "Planning"), ["usable_capacity_kwh", "charge_efficiency",
                 "max_power_kw", "vehicle_charger_kw", "grid_limit_kw", "safety_margin_min"]),
    "prices": (T("Strompreis (Tibber & dynamisch)", "Electricity price (Tibber & dynamic)"),
               ["price_source", "price_entity", "price_optimization", "price_blocks"]),
    "climate": (T("Vorklimatisierung", "Pre-climatisation"), ["climate_enabled",
                "climate_min_soc_pct", "climate_after_target_soc", "climate_very_cold_below_c",
                "climate_very_cold_min", "climate_cold_below_c", "climate_cold_min",
                "climate_cool_below_c", "climate_cool_min", "climate_warm_above_c",
                "climate_warm_min"]),
    "quality": (T("Datenqualität", "Data quality"), ["max_age_halo_power_s",
                "max_age_halo_energy_s", "max_age_vehicle_charging_s", "max_age_soc_s",
                "max_age_odometer_s", "max_age_temperature_s"]),
    "notifications": (T("Benachrichtigungen", "Notifications"), ["plug_reminder_time",
                      "notify_start_failed", "notify_cp", "notify_plan_infeasible",
                      "notify_plug_reminder", "notify_health", "notify_hv_cycles",
                      "notify_plug_in_action", "notify_external", "report_auto_monthly",
                      "notify_report"]),
    "monitor": (T("Statistik und Kosten", "Statistics and costs"), ["odometer_source",
                "trip_merge_gap_min", "event_retention_days", "hv_cycles_warn_per_day",
                "interval_min", "price_eur_kwh", "price_valid_from"]),
    "external": (T("Fremdladeerkennung", "External charge detection"), ["external_detection",
                 "external_min_kwh", "external_soc_jump_pct", "external_price_eur_kwh"]),
    "ovms_commands": (T("OVMS-Befehle", "OVMS commands"), ["ovms_wakeup_command",
                      "ovms_climate_command", "ovms_climate_stop_command"]),
}

STEP_DESC = {
    "charging": T("Vorläufige Werte bis zur Messphase (Phase 0). Live schaltet erst nach dem "
                  "Gate von v0.1.", "Provisional values until phase 0 measured them."),
    "wakeup": T("Der CP-Wakeup bleibt gesperrt, bis die Checkliste §3.6 abgehakt ist. "
                "Das Auto wird nie nur zur Datenauffrischung geweckt.",
                "The CP wakeup stays locked until checklist §3.6 is completed."),
    "ovms_commands": T("Nur Befehle eintragen, die am Fahrzeug getestet sind (§1.2). "
                       "Leer = Funktion gesperrt.",
                       "Only enter commands tested on the car (§1.2). Empty = locked."),
    "monitor": T("Festpreis: Ein neuer Preis mit Gültigkeitsdatum ändert keine alten Monate. "
                 "Er gilt auch als Rückfall, wenn die dynamische Preisquelle ausfällt.",
                 "Fixed price; also the fallback when the dynamic source fails."),
    "prices": T("Tibber: offizielle Tibber-Integration einrichten. Entität: jeder Sensor mit "
                "Preisliste in den Attributen (raw_today/raw_tomorrow, data, today/tomorrow). "
                "Ohne SOC oder ohne Preise für die ganze Nacht wird wie bisher geladen.",
                "Tibber: set up the official Tibber integration. Entity: any sensor with a "
                "price list in its attributes."),
    "external": T("Erkennung nur aus ohnehin vorhandenen OVMS-Daten – das Auto wird dafür nie "
                  "geweckt. Erkannte Ladungen sind Schätzungen und können im Panel ergänzt werden.",
                  "Detection only from data that arrives anyway – the car is never woken."),
}

STATES = {
    "executor_state": {
        "disconnected": T("Nicht gesteckt", "Disconnected"), "idle": T("Bereit", "Idle"),
        "enabling": T("Freigabe läuft", "Enabling"),
        "waiting_for_charge": T("Warte auf Ladung", "Waiting for charge"),
        "charge_stabilizing": T("Ladung stabilisiert", "Stabilizing"),
        "wakeup_ovms": T("Wakeup OVMS", "OVMS wakeup"), "wakeup_cp": T("Wakeup CP", "CP wakeup"),
        "charging": T("Lädt", "Charging"), "charge_ended": T("Ladung beendet", "Charge ended"),
        "interrupted": T("Unterbrochen", "Interrupted"),
        "disabling": T("Abschaltung läuft", "Disabling"), "cooldown": T("Pause", "Cooldown"),
        "start_failed": T("Start fehlgeschlagen", "Start failed"),
    },
    "desired_reason": {
        "safety_lock": T("Sicherheitssperre", "Safety lock"), "override": T("Override", "Override"),
        "rfid": T("RFID", "RFID"), "one_shot": T("Heute Nacht", "Tonight"),
        "target_soc_reached": T("Ziel-SOC erreicht", "Target SOC reached"),
        "climate": T("Vorklimatisierung", "Pre-climatisation"),
        "schedule": T("Wochenplan", "Weekly plan"), "default_off": T("Standard aus", "Default off"),
        "automation_off": T("Automatik aus", "Automation off"),
    },
    "system_health": {"healthy": T("Gesund", "Healthy"), "degraded": T("Eingeschränkt", "Degraded"),
                      "error": T("Fehler", "Error")},
}

SENSORS = {
    "executor_state": T("Ladezustand", "Executor state"),
    "desired_reason": T("Soll-Grund", "Desired reason"),
    "system_health": T("System-Health", "System health"),
    "last_event": T("Letztes Ereignis", "Last event"),
    "last_charge_result": T("Letztes Ladeergebnis", "Last charge result"),
    "charge_power": T("Ladeleistung", "Charge power"),
    "session_energy": T("Session-Energie", "Session energy"),
    "next_charge_start": T("Nächster Ladestart", "Next charge start"),
    "next_departure": T("Nächste Abfahrt", "Next departure"),
    "expected_departure_soc": T("Erwarteter SOC bei Abfahrt", "Expected SOC at departure"),
    "estimated_finish": T("Voraussichtlich fertig", "Estimated finish"),
    "soc": T("SOC", "SOC"), "soh": T("SOH", "SOH"), "range": T("Reichweite", "Range"),
    "odometer": T("Kilometerstand", "Odometer"),
    "battery_temperature": T("Batterietemperatur", "Battery temperature"),
    "hv_contactor_cycles": T("HV-Kontaktorzyklen", "HV contactor cycles"),
    "home_energy_total": T("Heimladen gesamt", "Home charging total"),
    "current_price": T("Aktueller Strompreis", "Current electricity price"),
    "next_charge_cost": T("Kosten nächste Ladung (Schätzung)", "Next charge cost (estimate)"),
}
for period, de, en in (("month", "Monat", "month"), ("year", "Jahr", "year")):
    SENSORS |= {
        f"{period}_home_energy": T(f"Heimladen {de}", f"Home energy {en}"),
        f"{period}_external_energy": T(f"Fremdladen {de}", f"External energy {en}"),
        f"{period}_distance": T(f"Strecke {de}", f"Distance {en}"),
        f"{period}_cost": T(f"Kosten {de}", f"Cost {en}"),
        f"{period}_cost_per_100km": T(f"Kosten pro 100 km {de}", f"Cost per 100 km {en}"),
        f"{period}_grid_consumption": T(f"Netzverbrauch {de}", f"Grid consumption {en}"),
    }

BINARY = {
    "vehicle_connected": T("Fahrzeug gesteckt", "Vehicle connected"),
    "charging": T("Lädt", "Charging"),
    "charge_problem": T("Ladeproblem", "Charge problem"),
    "cp_failsafe_ok": T("CP-Failsafe in Ordnung", "CP failsafe OK"),
    "charger_available": T("Wallbox erreichbar", "Charger available"),
    "vehicle_available": T("Fahrzeugdaten aktuell", "Vehicle data current"),
    "data_conflict": T("Datenkonflikt", "Data conflict"),
    "soc_stale": T("SOC veraltet", "SOC stale"),
    "charge_plan_feasible": T("Ladeplan erreichbar", "Charge plan feasible"),
    "manual_override": T("Manueller Override", "Manual override"),
    "hvcycle_warning": T("HV-Zyklen-Warnung", "HV cycle warning"),
}
SWITCHES = {"automation": T("Automatik", "Automation"), "dry_run": T("Dry-Run", "Dry run")}
BUTTONS = {
    "start_charge": T("Jetzt laden", "Start charging"),
    "stop_charge": T("Laden stoppen", "Stop charging"),
    "vehicle_wakeup": T("Fahrzeug wecken (OVMS)", "Wake vehicle (OVMS)"),
    "cp_wakeup": T("CP-Wakeup", "CP wakeup"),
    "reset_error": T("Fehler zurücksetzen", "Reset error"),
    "climate_5min": T("Klima 5 min", "Climate 5 min"),
    "climate_10min": T("Klima 10 min", "Climate 10 min"),
    "climate_15min": T("Klima 15 min", "Climate 15 min"),
    "climate_stop": T("Klima stoppen", "Stop climate"),
    "one_shot_tonight": T("Heute Nacht laden", "Charge tonight"),
}
OVERRIDE_MODES = {
    "none": T("Kein Override", "No override"),
    "until_unplugged": T("Bis Kabel ab", "Until unplugged"),
    "duration": T("Für 2 Stunden", "For 2 hours"),
    "until_time": T("Bis zur Abfahrt", "Until departure"),
    "until_soc": T("Bis Wunsch-SOC", "Until preferred SOC"),
    "stop": T("Laden stoppen", "Stop charging"),
}

SERVICES = {
    "start_charging": (T("Laden starten", "Start charging"),
                       T("Override „Jetzt laden“ setzen.", "Set a charge-now override.")),
    "stop_charging": (T("Laden stoppen", "Stop charging"),
                      T("Override „Laden stoppen“ bis Kabel ab.", "Stop until unplugged.")),
    "set_override": (T("Override setzen", "Set override"),
                     T("Manuellen Override mit Modus setzen.", "Set a manual override.")),
    "clear_override": (T("Override aufheben", "Clear override"), T("", "")),
    "start_one_shot": (T("Heute Nacht laden", "Charge tonight"),
                       T("One-Shot für die nächste Nacht.", "One-shot for the next night.")),
    "cancel_one_shot": (T("One-Shot löschen", "Cancel one-shot"), T("", "")),
    "vehicle_wakeup": (T("Fahrzeug wecken", "Wake vehicle"),
                       T("Software-Wakeup über OVMS (gleiche Sperren wie die Kaskade).",
                         "OVMS software wakeup (same guards as the cascade).")),
    "cp_wakeup": (T("CP-Wakeup", "CP wakeup"),
                  T("CP-Puls über den Shelly – nur mit verifiziertem Failsafe.",
                    "CP pulse via the Shelly – only with a verified failsafe.")),
    "reset_error": (T("Fehler zurücksetzen", "Reset error"), T("", "")),
    "start_climate": (T("Klimatisierung starten", "Start climate"), T("", "")),
    "stop_climate": (T("Klimatisierung stoppen", "Stop climate"), T("", "")),
    "add_external_charge": (T("Fremdladung erfassen", "Add external charge"),
                            T("Ladung außer Haus; fließt nicht in die Hausabrechnung.",
                              "Charge away from home; not part of the home bill.")),
    "delete_external_charge": (T("Fremdladung löschen", "Delete external charge"), T("", "")),
    "add_manual_odometer": (T("Kilometerstand erfassen", "Add odometer reading"), T("", "")),
    "set_plans": (T("Ladepläne setzen", "Set charge plans"),
                  T("Ersetzt alle Wochenpläne.", "Replaces all weekly plans.")),
    "export": (T("Export", "Export"),
               T("CSV/JSON nach /config/ev_charging_pilot/export.",
                 "CSV/JSON into /config/ev_charging_pilot/export.")),
    "start_replay": (T("Replay starten", "Start replay"),
                     T("Aufgezeichnete Nacht ohne Hardware durchspielen.",
                       "Run a recorded night without hardware.")),
    "stop_replay": (T("Replay beenden", "Stop replay"), T("", "")),
    "create_report": (T("PDF-Bericht erstellen", "Create PDF report"),
                      T("Monats- oder Jahresbericht nach /config/ev_charging_pilot/reports.",
                        "Monthly or yearly report into /config/ev_charging_pilot/reports.")),
    "configure_shelly": (T("Shelly konfigurieren", "Configure Shelly"),
                         T("Setzt am Shelly die Failsafe-Werte aus §3.1: Einschaltzustand an, "
                           "Auto-On nach der CP-Pulsdauer.",
                           "Writes the §3.1 failsafe settings to the Shelly.")),
    "refresh_prices": (T("Preise aktualisieren", "Refresh prices"),
                       T("Dynamische Preise sofort neu abrufen.", "Fetch dynamic prices now.")),
    "create_replay_dataset": (T("Replay-Datensatz erstellen", "Create replay dataset"),
                              T("Aus der Recorder-Historie.", "From the recorder history.")),
}
FIELDS = {
    "mode": T("Modus", "Mode"), "duration_min": T("Dauer", "Duration"),
    "until": T("Bis", "Until"), "target_soc": T("Ziel-SOC", "Target SOC"),
    "departure_time": T("Abfahrtszeit", "Departure time"), "minutes": T("Minuten", "Minutes"),
    "date": T("Datum", "Date"), "energy_kwh": T("Energie", "Energy"),
    "source": T("Ort", "Location"), "cost_eur": T("Kosten", "Cost"),
    "price_eur_kwh": T("Preis", "Price"), "odometer_km": T("Kilometerstand", "Odometer"),
    "soc_before": T("SOC vorher", "SOC before"), "soc_after": T("SOC nachher", "SOC after"),
    "provider": T("Anbieter", "Provider"), "note": T("Notiz", "Note"), "id": T("ID", "ID"),
    "at": T("Zeitpunkt", "Time"), "plans": T("Pläne", "Plans"),
    "dataset": T("Datensatz", "Dataset"), "format": T("Format", "Format"),
    "start": T("Start", "Start"), "end": T("Ende", "End"), "file": T("Datei", "File"),
    "tick_s": T("Takt", "Tick"), "name": T("Name", "Name"),
    "poll_interval_s": T("Wallbox-Poll-Intervall (Messung M1)", "Wallbox poll interval (M1)"),
    "period": T("Zeitraum", "Period"), "year": T("Jahr", "Year"), "month": T("Monat", "Month"),
}
SERVICE_FIELDS = {
    "start_charging": ["mode", "duration_min", "until", "target_soc"],
    "set_override": ["mode", "duration_min", "until", "target_soc"],
    "start_one_shot": ["departure_time"],
    "start_climate": ["minutes"],
    "add_external_charge": ["date", "energy_kwh", "source", "cost_eur", "price_eur_kwh",
                            "odometer_km", "soc_before", "soc_after", "provider", "note"],
    "delete_external_charge": ["id"],
    "add_manual_odometer": ["odometer_km", "at"],
    "set_plans": ["plans"],
    "export": ["dataset", "format", "start", "end"],
    "start_replay": ["file", "dataset", "tick_s"],
    "create_replay_dataset": ["start", "end", "name", "poll_interval_s"],
    "create_report": ["period", "year", "month"],
}


def build(lang: str) -> dict:
    def t(item):
        return item[lang]

    setup_desc = {
        "user": T("Gib deinem Fahrzeug einen Namen – daraus wird z. B. „Smarty Charging Pilot“. "
                  "Im Dry-Run protokolliert die Integration zunächst nur, was sie schalten würde.",
                  "Name your vehicle – it becomes e.g. 'Smarty Charging Pilot'. In dry-run the "
                  "integration only logs what it would do."),
        "halo": T("**{found}**\n\nDie Entitäten deiner Wallbox-Integration (z. B. Chargeamps, "
                  "go-e, Easee, Wallbox, Zaptec, KEBA …). Pflicht sind nur die vier oberen Felder.",
                  "**{found}**\n\nEntities of your wallbox integration (e.g. Chargeamps, go-e, "
                  "Easee, Wallbox, Zaptec, KEBA …). Only the first four fields are required."),
        "shelly": T("**{found}**\n\nOptional: ein Shelly-Relais in der CP-Leitung weckt "
                    "schlafende Fahrzeuge. Ohne einfach leer lassen und weiter.",
                    "**{found}**\n\nShelly in the CP line. Leave empty without a Shelly."),
        "notify": T("**{found}**\n\nPush-Ziel für Fehler und die Rückfrage beim Einstecken.",
                    "**{found}**\n\nPush target for errors and the plug-in question."),
        "ovms": T("**{found}**\n\nFahrzeugdaten aus OVMS oder der Integration deines "
                  "Herstellers. Komplett überspringbar – später über „Neu konfigurieren“ ergänzbar.",
                  "**{found}**\n\nOptional – OVMS can be added later via reconfigure."),
    }
    titles = {"user": T("EV Charging Pilot", "EV Charging Pilot"),
              "halo": T("Wallbox", "Charger"), "shelly": T("CP-Unterbrechung (optional)",
                                                          "CP interruption (optional)"),
              "notify": T("Benachrichtigungen", "Notifications"), "ovms": T("Fahrzeug",
                                                                           "Vehicle")}
    step_fields = {
        "user": {"vehicle_name": T("Name deines Fahrzeugs", "Name of your vehicle"),
                 "dry_run": T("Im Dry-Run starten", "Start in dry-run")},
        "halo": {k: t(INPUTS[k]) for k in ("charger_enable", "cable_connected", "charge_power",
                                           "total_energy", "charger_status", "max_current",
                                           "cable_lock", "internal_schedule")},
        "shelly": {k: t(INPUTS[k]) for k in ("cp_relay", "shelly_host")},
        "notify": {"notify_service": t(INPUTS["notify_service"])},
        "ovms": {k: t(v) for k, v in INPUTS.items() if k.startswith("ovms_") or k in (
            "outside_temp", "weather")},
    }

    def step(key):
        fields = step_fields[key]
        result = {"title": t(titles[key]), "description": t(setup_desc[key]),
                  "data": {k: (t(v) if isinstance(v, dict) else v) for k, v in fields.items()}}
        helps = {k: t(FIELD_HELP[k]) for k in fields if k in FIELD_HELP}
        if key == "user":
            helps = {"vehicle_name": t(T("z. B. Smarty – änderbar im Panel unter Einstellungen.",
                                         "e.g. Smarty – can be changed later.")),
                     "dry_run": t(T("Empfohlen: Die Integration protokolliert zunächst nur, was "
                                    "sie schalten würde.", "Recommended: only log at first."))}
        if helps:
            result["data_description"] = helps
        return result

    options_steps = {"init": {"title": t(T("Einstellungen", "Settings")),
                              "menu_options": {k: t(v[0]) for k, v in OPTION_STEPS.items()}}}
    for key, (title, fields) in OPTION_STEPS.items():
        options_steps[key] = {"title": t(title), "data": {f: t(OPTIONS[f]) for f in fields}}
        if key in STEP_DESC:
            options_steps[key]["description"] = t(STEP_DESC[key])

    entity = {
        "sensor": {k: {"name": t(v)} for k, v in SENSORS.items()},
        "binary_sensor": {k: {"name": t(v)} for k, v in BINARY.items()},
        "switch": {k: {"name": t(v)} for k, v in SWITCHES.items()},
        "button": {k: {"name": t(v)} for k, v in BUTTONS.items()},
        "select": {"override_mode": {"name": t(T("Override-Modus", "Override mode")),
                                     "state": {k: t(v) for k, v in OVERRIDE_MODES.items()}}},
        "number": {
            "minimum_departure_soc": {"name": t(T("Mindest-SOC bei Abfahrt",
                                                  "Minimum departure SOC"))},
            "preferred_departure_soc": {"name": t(T("Wunsch-SOC bei Abfahrt",
                                                    "Preferred departure SOC"))},
        },
        "time": {"departure": {"name": t(T("Abfahrt", "Departure"))}},
    }
    for key, states in STATES.items():
        entity["sensor"][key]["state"] = {k: t(v) for k, v in states.items()}

    services = {}
    for key, (name, desc) in SERVICES.items():
        services[key] = {"name": t(name), "description": t(desc) or t(name)}
        if key in SERVICE_FIELDS:
            services[key]["fields"] = {
                f: {"name": t(FIELDS[f]), "description": t(FIELDS[f])}
                for f in SERVICE_FIELDS[key]}

    return {
        "config": {
            "step": {**{k: step(k) for k in ("user", "halo", "shelly", "notify", "ovms")},
                     "reconfigure": step("halo") | {"title": t(T("Neu konfigurieren",
                                                                 "Reconfigure"))}},
            "error": {"host_without_relay": t(T(
                "Ein Shelly-Host braucht auch das CP-Relais.",
                "A Shelly host also needs the CP relay."))},
            "abort": {
                "single_instance_allowed": t(T("Bereits eingerichtet.", "Already configured.")),
                "reconfigure_successful": t(T("Neu konfiguriert.", "Reconfigured.")),
            },
        },
        "options": {"step": options_steps, "error": {
            "price_entity_missing": t(T("Bitte eine Preis-Entität wählen.",
                                        "Please choose a price entity.")),
            "tibber_missing": t(T("Die Tibber-Integration ist nicht eingerichtet.",
                                  "The Tibber integration is not set up.")),
        }},
        "selector": {
            "mode": {"options": {"dry_run": t(T("Dry-Run (nur protokollieren)", "Dry run")),
                                 "live": t(T("Live (schaltet Hardware)", "Live")),
                                 "replay": t(T("Replay (keine Hardware)", "Replay"))}},
            "climate_after_target_soc": {"options": {
                "allow_topup": t(T("Nachladen erlauben", "Allow top-up")),
                "battery_only": t(T("Nur aus dem Akku", "Battery only")),
                "enforce_target": t(T("Ziel-SOC durchsetzen", "Enforce target"))}},
            "odometer_source": {"options": {"manual": t(T("Manuell", "Manual")),
                                            "ovms": t(T("OVMS", "OVMS"))}},
            "override_mode": {"options": {k: t(v) for k, v in OVERRIDE_MODES.items()
                                          if k != "none"}},
            "external_source": {"options": {
                "public": t(T("Öffentlich", "Public")),
                "workplace": t(T("Arbeitgeber", "Workplace")),
                "other_home": t(T("Andere Wallbox", "Other home"))}},
            "price_source": {"options": {
                "fixed": t(T("Festpreis", "Fixed price")),
                "entity": t(T("Preis-Entität", "Price entity")),
                "tibber": t(T("Tibber", "Tibber"))}},
            "report_period": {"options": {"month": t(T("Monat", "Month")),
                                          "year": t(T("Jahr", "Year"))}},
            "export_dataset": {"options": {
                "sessions": t(T("Lade-Sessions", "Charge sessions")),
                "trips": t(T("Fahrten", "Trips")),
                "external": t(T("Fremdladungen", "External charges")),
                "months": t(T("Monatsbilanzen", "Monthly balances"))}},
        },
        "entity": entity,
        "services": services,
    }


for lang in ("de", "en"):
    (ROOT / "translations" / f"{lang}.json").write_text(
        json.dumps(build(lang), ensure_ascii=False, indent=2) + "\n")
(ROOT / "strings.json").write_text(json.dumps(build("en"), ensure_ascii=False, indent=2) + "\n")
print("ok")
