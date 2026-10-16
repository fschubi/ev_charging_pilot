"""Systemtest: check every link step by step – without switching anything and
without waking the car (review stage 3).

Meant before switching to live and whenever something seems off. Each step
reports ``ok``, ``info``, ``warn`` or ``bad`` with a sentence that says what to do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from .core.engine import Notification
from .core.inputs import Inp
from .core.model import Category, Event, Quality, Severity
from .core.settings import PriceSource, RunMode
from .ha_ports import (
    OVMS_PATH_MQTT,
    OVMS_PATH_SCRIPT,
    OVMS_PATH_SERVICE,
    ovms_vehicle_id,
    shelly_deviations,
)

if TYPE_CHECKING:
    from .coordinator import ChargingCenter

PATH_LABELS = {OVMS_PATH_SERVICE: "OVMS-Integration", OVMS_PATH_MQTT: "MQTT-Topic",
               OVMS_PATH_SCRIPT: "Script"}
UNUSABLE = ("unavailable", "unknown")


def _age(value) -> str:
    seconds = value.age_s(dt_util.utcnow())
    if seconds is None:
        return ""
    if seconds < 120:
        return f"vor {seconds:.0f} s"
    if seconds < 7200:
        return f"vor {seconds / 60:.0f} min"
    return f"vor {seconds / 3600:.0f} h"


async def async_system_check(center: ChargingCenter, *,
                             send_test_push: bool = False) -> list[dict[str, Any]]:
    hass = center.hass
    engine = center.engine
    settings = center.settings
    results: list[dict[str, Any]] = []

    def add(step: str, title: str, status: str, detail: str) -> None:
        results.append({"step": step, "title": title, "status": status, "detail": detail})

    # 1. wallbox release switch
    charger = center.entity_ids[Inp.CHARGER_ENABLE]
    state = hass.states.get(charger)
    if state is None or state.state in UNUSABLE:
        add("charger", "Wallbox-Freigabe", "bad",
            f"{charger} ist nicht erreichbar – ist die Wallbox online und ihre Integration "
            "geladen?")
    else:
        add("charger", "Wallbox-Freigabe", "ok",
            f"{charger} meldet „{'an' if state.state == 'on' else 'aus'}“.")

    # 2. wallbox measurements
    for inp, title in ((Inp.CABLE_CONNECTED, "Kabelstatus"),
                       (Inp.CHARGE_POWER, "Ladeleistung"),
                       (Inp.TOTAL_ENERGY, "Energiezähler")):
        value = engine.values.get(inp)
        if inp not in center.entity_ids or value is None:
            add(inp.value, title, "bad", "nicht eingerichtet")
        elif not value.available:
            add(inp.value, title, "bad", "keine Daten – Wallbox-Cloud oder Integration prüfen")
        elif inp is Inp.CABLE_CONNECTED:
            add(inp.value, title, "ok",
                "eingesteckt" if value.normalized else "nicht eingesteckt")
        elif value.quality is Quality.GOOD:
            add(inp.value, title, "ok", f"{value.normalized:g} {value.unit or ''} "
                f"({_age(value)})".replace("  ", " "))
        else:
            add(inp.value, title, "warn",
                f"letzter Wert {_age(value)} – die Wallbox meldet sich selten (Abfrageintervall?)")

    # 3. internal schedule of the wallbox
    schedule = engine.values.get(Inp.INTERNAL_SCHEDULE)
    if schedule is not None and Inp.INTERNAL_SCHEDULE in center.entity_ids \
            and schedule.available and schedule.normalized:
        add("schedule", "Interner Zeitplan der Wallbox", "bad",
            "ist an – bitte in der App der Wallbox ausschalten, sonst schalten zwei Systeme.")

    # 4. CP interruption (Shelly)
    if Inp.CP_RELAY in center.entity_ids:
        relay = engine.values.get(Inp.CP_RELAY)
        if relay is None or not relay.available:
            add("cp_relay", "CP-Relais", "bad",
                "nicht erreichbar – die Automatik ist gesperrt, solange der Zustand unbekannt ist.")
        elif relay.normalized:
            add("cp_relay", "CP-Relais", "ok", "geschlossen (Normalzustand).")
        else:
            add("cp_relay", "CP-Relais", "bad", "offen – das Auto kann so nicht laden.")
        if center.ports.shelly_host:
            config = await center.ports.shelly_switch_config()
            if config is None:
                add("shelly", "Shelly-Failsafe", "warn",
                    "Konfiguration nicht lesbar (offline oder Passwort).")
            else:
                deviations = shelly_deviations(config, settings.cp_pulse_s)
                add("shelly", "Shelly-Failsafe", "warn" if deviations else "ok",
                    "weicht ab – Diagnose → „Shelly konfigurieren“" if deviations else
                    f"schließt nach {settings.cp_pulse_s} s von selbst, Einschaltzustand an.")
        add("cp_failsafe", "CP-Wakeup", "ok" if settings.cp_failsafe_verified else "info",
            "freigegeben (Checkliste abgehakt)." if settings.cp_failsafe_verified else
            "gesperrt, bis die Failsafe-Checkliste abgehakt ist (Einstellungen → Wecken).")

    # 5. vehicle data
    if Inp.OVMS_SOC in center.entity_ids:
        soc = engine.soc
        if soc.quality in (Quality.GOOD, Quality.LAST_KNOWN_VALID):
            add("vehicle_data", "Fahrzeugdaten", "ok",
                f"Ladestand {soc.normalized:.0f} % ({_age(soc)}"
                f"{', Auto schläft' if soc.quality is Quality.LAST_KNOWN_VALID else ''}).")
        else:
            add("vehicle_data", "Fahrzeugdaten", "warn",
                f"Ladestand {str(soc.quality).lower()} – kommt Neues, sobald das Auto wach ist.")

        # 6. command path – checked, never used
        path = center.ports.ovms_path
        if path is None:
            add("vehicle_commands", "Befehle ans Fahrzeug",
                "bad" if settings.ovms_enabled else "info",
                "kein Befehlsweg gefunden – die OVMS-Integration (HACS) einrichten.")
        else:
            label = PATH_LABELS[path]
            if path == OVMS_PATH_SERVICE:
                label += f", Fahrzeug-ID {ovms_vehicle_id(hass, center.ports.ovms_entity)}"
            wake = center.ports.wakeup_command(settings.ovms_wakeup_command)
            if settings.ovms_enabled:
                add("vehicle_commands", "Befehle ans Fahrzeug", "ok",
                    f"bereit über {label}; Wecken mit „{wake}“ (nicht ausgeführt).")
            else:
                add("vehicle_commands", "Befehle ans Fahrzeug", "info",
                    f"Weg bereit ({label}), aber „Lesen & Schreiben“ ist aus.")

    # 7. push
    service = center.notifier.service
    if not service:
        add("push", "Push-Nachrichten", "warn", "kein Push-Ziel eingerichtet.")
    elif not hass.services.has_service("notify", service):
        add("push", "Push-Nachrichten", "bad", f"notify.{service} gibt es nicht (mehr).")
    else:
        if send_test_push:
            await center.notifier.async_send(Notification(
                "test", "normal", "Testnachricht",
                "Push funktioniert – so sehen Meldungen des Charging Pilot aus."))
        add("push", "Push-Nachrichten", "ok",
            f"notify.{service}" + (" – Testnachricht gesendet." if send_test_push else "."))

    # 8. prices
    if settings.price_source is PriceSource.FIXED:
        add("prices", "Strompreis", "ok",
            f"Festpreis {settings.price_history[-1].eur_per_kwh:.2f} €/kWh".replace(".", ","))
    elif center.price_fetcher.last_error:
        add("prices", "Strompreis", "warn",
            f"{center.price_fetcher.last_error} – bis dahin gilt der Festpreis.")
    elif engine.dynamic_prices:
        add("prices", "Strompreis", "ok", f"dynamisch, {len(engine.price_schedule.slots)} "
            "Preisintervalle bekannt.")
    else:
        add("prices", "Strompreis", "warn", "dynamisch gewählt, aber noch keine Preise.")

    # 9. mode and overall health
    if center.mode is RunMode.LIVE:
        add("mode", "Betriebsmodus", "ok", "Live – die Integration schaltet die Wallbox.")
    else:
        add("mode", "Betriebsmodus", "info",
            "Probebetrieb – es wird nichts geschaltet, nur protokolliert.")
    health = engine.health
    add("health", "Systemzustand", {"HEALTHY": "ok", "DEGRADED": "warn"}.get(
        str(health.status), "bad"), ", ".join(health.reasons) or "keine Auffälligkeiten")

    counts = {s: sum(r["status"] == s for r in results) for s in ("ok", "warn", "bad")}
    center.log_event(Event(dt_util.utcnow(), Category.CONFIG,
                           Severity.WARNING if counts["bad"] else Severity.INFO, "SYSTEM_CHECK",
                           f"Systemtest: {counts['ok']} ok, {counts['warn']} Hinweise, "
                           f"{counts['bad']} Fehler"))
    return results
