# Smart EQ 453 Charging Center

Home-Assistant-Integration, die das Laden eines **smart EQ fortwo 453** an einer
**Charge Amps Halo** als einziges Steuerungssystem übernimmt (ersetzt evcc):
abfahrtsbasierte Ladeplanung, Wakeup-Kaskade (OVMS → CP-Puls über Shelly),
Ziel-SOC, Vorklimatisierung, System-Health mit Push, Lade-Sessions mit Kosten,
Fahrten, Monatsbilanz mit SOC-Ausgleich und ein eigenes Sidebar-Panel.

Spezifikation: [Masterplan v1.3](docs/masterplan-v1.3.md) · Stand: [Roadmap](docs/ROADMAP.md)

> **Sicherheit zuerst.** Die Integration startet immer im **Dry-Run** und
> protokolliert nur, was sie schalten würde. Live geht sie erst nach Messphase,
> Dry-Run-Abgleich und Einzeltest (Grundsatz 11). Der CP-Wakeup bleibt gesperrt,
> bis die Failsafe-Checkliste (§3.6) abgehakt und die Verdrahtung von einer
> Elektrofachkraft abgenommen ist. OVMS-Befehle sind leer, bis sie am Fahrzeug
> getestet wurden.

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
| HACS-Integration **Chargeamps** | Halo schalten und messen | ja |
| Shelly 1 Mini Gen3 in der CP-Leitung | Wakeup per CP-Puls | nein |
| OVMS v3 (z. B. per MQTT) | SOC, Fahrten, Klima, Software-Wakeup | nein |
| Companion-App | Push und Rückfrage beim Einstecken | empfohlen |

## Installation

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories* →
   `https://github.com/fschubi/smart453_charging_center`, Kategorie *Integration*.
2. „Smart EQ Charging Center“ installieren, Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → *Smart EQ Charging Center* hinzufügen.
   Fünf kurze Schritte: Name/Dry-Run → Halo → Shelly → Push-Ziel → OVMS (überspringbar).
4. In der Seitenleiste erscheint **Smart EQ**.

Vor dem Live-Betrieb: [Phase 0](phase0/README.md) – einfache Automation und
Messphase, deren Ergebnisse die vorläufigen Zeitkonstanten ersetzen.

## Bedienung

**Panel (Seitenleiste „Smart EQ“)** mit fünf Ansichten:

| Ansicht | Inhalt |
| --- | --- |
| Cockpit | Status, SOC, Leistung, nächste Abfahrt, Prognose, Health, Schnellaktionen |
| Ladeplan | Wochenpläne bearbeiten (mehrere), kommende Ladefenster, Klima je Plan |
| Hausstrom → Smart EQ | Heim-kWh und Kosten je Monat, Monatsvergleich, Sessions |
| Drive & Energy | Strecke, Verbrauch, Temperatur-/Saisonstatistik, Fahrten, Fremdladen |
| Diagnose | Health, CP/Failsafe, Datenqualität je Wert, Event Log, Replay |

**Push beim Einstecken:** *Normaler Plan* · *Heute Nacht laden* · *Jetzt laden*.

**Standard-Dashboard** ohne Panel: [dashboards/smart_eq_dashboard.yaml](dashboards/smart_eq_dashboard.yaml).

## Entitäten (Auszug, §12)

| Entität | Bedeutung |
| --- | --- |
| `sensor.smart_eq_executor_state` | Ladezustand (Bereit, Lädt, Wakeup CP, Start fehlgeschlagen …) |
| `sensor.smart_eq_desired_reason` | Warum die Halo an/aus sein soll |
| `sensor.smart_eq_system_health` | Gesund / Eingeschränkt / Fehler mit Gründen |
| `sensor.smart_eq_next_charge_start`, `_next_departure`, `_estimated_finish` | Plan |
| `sensor.smart_eq_expected_departure_soc` | Prognose (Schätzung) |
| `sensor.smart_eq_month_home_energy`, `_month_cost`, `_year_*` … | Hausabrechnung und Kosten |
| `sensor.smart_eq_soc`, `_soh`, `_range`, `_odometer`, `_hv_contactor_cycles` | Fahrzeug (mit OVMS) |
| `binary_sensor.smart_eq_charging`, `_charge_problem`, `_cp_failsafe_ok`, `_data_conflict` … | Status |
| `switch.smart_eq_automation`, `switch.smart_eq_dry_run` | Automatik, Dry-Run |
| `select.smart_eq_override_mode`, `number.smart_eq_*_departure_soc`, `time.smart_eq_departure` | Plan bedienen |
| Buttons | Jetzt laden · Stopp · Heute Nacht · Fahrzeug wecken · CP-Wakeup · Klima 5/10/15 · Klima stopp · Fehler zurücksetzen |

## Services (`smart_eq_charging.*`)

`start_charging`, `stop_charging`, `set_override`, `clear_override`,
`start_one_shot`, `cancel_one_shot`, `vehicle_wakeup`, `cp_wakeup`,
`reset_error`, `start_climate`, `stop_climate`, `add_external_charge`,
`delete_external_charge`, `add_manual_odometer`, `set_plans`,
`export` (CSV/JSON nach `/config/smart_eq_charging/export`),
`create_replay_dataset`, `start_replay`, `stop_replay`.

Alle Services laufen durch Arbiter und Executor – nie direkt auf die Hardware.

## Replay

Aufgezeichnete Nächte lassen sich ohne Hardware nachspielen (Gate v0.1):

```yaml
action: smart_eq_charging.create_replay_dataset
data: {start: "2026-10-14 02:30", end: "2026-10-14 06:30", name: nacht-2026-10-14}
```

Danach im Panel (Diagnose → Replay) oder per `start_replay` ausführen. Das
Ergebnis zeigt, ob die Entscheidungen der Engine mit dem realen Schalten
übereinstimmen.

## Architektur

```
custom_components/smart_eq_charging/
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
python3 tools/gen_translations.py custom_components/smart_eq_charging
```

Lizenz: MIT
