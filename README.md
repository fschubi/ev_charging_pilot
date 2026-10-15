# EV Charging Pilot

Home-Assistant-Integration, die das Laden deines **Elektroautos an deiner Wallbox**
als einziges Steuerungssystem übernimmt – mit jeder Wallbox und jedem Fahrzeug, die
Home Assistant als Entitäten kennt. Du gibst deinem Auto einen Namen, und die
Oberfläche heißt dann z. B. **„Smarty Charging Pilot“**.

Funktionen: abfahrtsbasierte Ladeplanung, Laden in den günstigsten Stunden (Tibber oder
andere dynamische Tarife), Wakeup-Kaskade (Fahrzeug → CP-Puls über Shelly), Ziel-SOC,
Vorklimatisierung, System-Health mit Push, Lade-Sessions mit Kosten, Fahrten,
Monatsbilanz mit SOC-Ausgleich, automatische Fremdladeerkennung,
PDF-Monatsberichte und ein eigenes Sidebar-Panel.

Entwickelt und erprobt mit einem smart EQ fortwo 453, einer Charge Amps Halo, einem
Shelly 1 Mini Gen3 in der CP-Leitung und OVMS v3.
Spezifikation: [Masterplan v1.3](docs/masterplan-v1.3.md) · Stand: [Roadmap](docs/ROADMAP.md)

> **Sicherheit zuerst.** Die Integration startet immer im **Dry-Run** und
> protokolliert nur, was sie schalten würde. Live geht sie erst nach Messphase,
> Dry-Run-Abgleich und Einzeltest (Grundsatz 11). Der CP-Wakeup bleibt gesperrt,
> bis die Failsafe-Checkliste (§3.6) abgehakt und die Verdrahtung von einer
> Elektrofachkraft abgenommen ist. Fahrzeugbefehle (OVMS) sind leer, bis sie am
> Fahrzeug getestet wurden.

## Was die Integration beantwortet

- Ist der Smart angeschlossen und lädt er stabil?
- Erreicht er bis zur Abfahrt den Mindest-SOC?
- Musste er geweckt werden – und kostete das HV-Kontaktorzyklen?
- Wie viele kWh wurden diesen Monat zuhause geladen, was hat das gekostet?
- Ist das System gesund?

## Voraussetzungen

| Komponente | Zweck | Pflicht |
| --- | --- | --- |
| Home Assistant ≥ 2025.6 | | ja |
| Wallbox-Integration (z. B. Chargeamps, go-e, Easee, Wallbox, Zaptec, KEBA) mit Freigabe-Schalter, Kabelstatus, Leistung und Energiezähler | Laden schalten und messen | ja |
| Shelly 1 Mini Gen3 in der CP-Leitung | Wakeup per CP-Puls | nein |
| Fahrzeugdaten: OVMS v3 (MQTT) oder Hersteller-Integration | SOC, Fahrten, Klima, Wakeup | nein |
| Companion-App | Push und Rückfrage beim Einstecken | empfohlen |
| Tibber-Integration oder Preis-Sensor (Nordpool, EPEX …) | dynamischer Strompreis | nein |

## Installation

1. HACS → ⋮ (oben rechts) → *Benutzerdefinierte Repositories* →
   Repository `https://github.com/fschubi/ev_charging_pilot`,
   Typ *Integration* → *Hinzufügen*.
2. „EV Charging Pilot“ installieren, Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → *EV Charging Pilot* hinzufügen.
   Fünf kurze Schritte: Fahrzeugname/Dry-Run → Wallbox → CP-Relais (optional) → Push-Ziel →
   Fahrzeug (überspringbar).
   Die Entitäten werden **automatisch erkannt und vorbelegt** – nur prüfen und bestätigen.
4. In der Seitenleiste erscheint **„<Fahrzeugname> Charging Pilot“**.

Vor dem Live-Betrieb: [Phase 0](phase0/README.md) – einfache Automation und
Messphase, deren Ergebnisse die vorläufigen Zeitkonstanten ersetzen.

## Bedienung

**Panel (Seitenleiste „<Fahrzeugname> Charging Pilot“)** mit sechs Ansichten:

| Ansicht | Inhalt |
| --- | --- |
| Cockpit | Status, SOC, Leistung, nächste Abfahrt, Prognose, Health, Schnellaktionen |
| Ladeplan | Wochenpläne bearbeiten (mehrere), kommende Ladefenster, Klima je Plan |
| Hausstrom → Fahrzeug | Heim-kWh und Kosten je Monat, Monatsvergleich, Sessions |
| Drive & Energy | Strecke, Verbrauch, Temperatur-/Saisonstatistik, Fahrten, Fremdladen |
| Diagnose | Health, CP/Failsafe (inkl. „Shelly konfigurieren“), Datenqualität je Wert, Event Log, Replay |
| Einstellungen | Alle Optionen als Formular, Strompreis mit Historie, eigenes Fahrzeugfoto |

**Push beim Einstecken:** *Normaler Plan* · *Heute Nacht laden* · *Jetzt laden*.

**Strompreis:** Optionen → *Strompreis*. Mit Tibber (offizielle Integration) oder
einer Preis-Entität lädt ein abfahrtsbasierter Plan in den günstigsten Stunden
vor der Abfahrt – standardmäßig in einem zusammenhängenden Block, damit das Auto
nicht mehrfach geweckt werden muss. Ohne SOC oder ohne Preise für die ganze Nacht
wird wie gewohnt geladen; Kosten werden je 15 Minuten mit dem echten Preis berechnet.

**PDF-Berichte:** Panel → Hausstrom → *PDF Monat* / *PDF Jahr*, automatisch am
Monatsersten um 06:00. Ablage in `/config/ev_charging_pilot/reports`, Download nur
für angemeldete Benutzer.

**Fremdladen:** Ladungen außer Haus werden aus den Fahrzeugdaten erkannt (ohne das Auto
zu wecken) und als *geschätzt* eingetragen; Kosten und Anbieter im Panel ergänzen.

**Standard-Dashboard** ohne Panel: [dashboards/ev_pilot_dashboard.yaml](dashboards/ev_pilot_dashboard.yaml).

## Entitäten (Auszug, §12)

| Entität | Bedeutung |
| --- | --- |
| `sensor.ev_pilot_executor_state` | Ladezustand (Bereit, Lädt, Wakeup CP, Start fehlgeschlagen …) |
| `sensor.ev_pilot_desired_reason` | Warum die Wallbox an/aus sein soll |
| `sensor.ev_pilot_system_health` | Gesund / Eingeschränkt / Fehler mit Gründen |
| `sensor.ev_pilot_next_charge_start`, `_next_departure`, `_estimated_finish` | Plan |
| `sensor.ev_pilot_expected_departure_soc` | Prognose (Schätzung) |
| `sensor.ev_pilot_month_home_energy`, `_month_cost`, `_year_*` … | Hausabrechnung und Kosten |
| `sensor.ev_pilot_soc`, `_soh`, `_range`, `_odometer`, `_hv_contactor_cycles` | Fahrzeug (mit Fahrzeugdaten) |
| `binary_sensor.ev_charging_pilot`, `_charge_problem`, `_cp_failsafe_ok`, `_data_conflict` … | Status |
| `switch.ev_pilot_automation`, `switch.ev_pilot_dry_run` | Automatik, Dry-Run |
| `select.ev_pilot_override_mode`, `number.ev_pilot_*_departure_soc`, `time.ev_pilot_departure` | Plan bedienen |
| Buttons | Jetzt laden · Stopp · Heute Nacht · Fahrzeug wecken · CP-Wakeup · Klima 5/10/15 · Klima stopp · Fehler zurücksetzen |

## Services (`ev_charging_pilot.*`)

`start_charging`, `stop_charging`, `set_override`, `clear_override`,
`start_one_shot`, `cancel_one_shot`, `vehicle_wakeup`, `cp_wakeup`,
`reset_error`, `start_climate`, `stop_climate`, `add_external_charge`,
`delete_external_charge`, `add_manual_odometer`, `set_plans`,
`export` (CSV/JSON nach `/config/ev_charging_pilot/export`),
`create_report` (PDF), `refresh_prices`,
`create_replay_dataset`, `start_replay`, `stop_replay`.

Alle Services laufen durch Arbiter und Executor – nie direkt auf die Hardware.

## Replay

Aufgezeichnete Nächte lassen sich ohne Hardware nachspielen (Gate v0.1):

```yaml
action: ev_charging_pilot.create_replay_dataset
data: {start: "2026-10-14 02:30", end: "2026-10-14 06:30", name: nacht-2026-10-14}
```

Danach im Panel (Diagnose → Replay) oder per `start_replay` ausführen. Das
Ergebnis zeigt, ob die Entscheidungen der Engine mit dem realen Schalten
übereinstimmen.

## Architektur

```
custom_components/ev_charging_pilot/
  core/          HA-freier Kern (nur stdlib): Engine, Planner, Arbiter, Executor,
                 Health, Datenqualität, Sessions, Trips, Statistik, Kosten, Replay
  coordinator.py Liest Entitäten, ruft Engine.tick(), führt Befehle aus (nur live)
  …              Entitäten, Services, WebSocket-API, Config-/Options-Flow, Panel
```

Der Kern ist ohne Home Assistant testbar; ein Test stellt sicher, dass er
keine `homeassistant`-Imports enthält.

## Entwicklung

```bash
uv venv -p 3.13 .venv
uv pip install -p .venv/bin/python -r requirements-test.txt
.venv/bin/python -m pytest
uvx ruff check custom_components tests tools
python3 tools/gen_translations.py custom_components/ev_charging_pilot
```

Lizenz: MIT
