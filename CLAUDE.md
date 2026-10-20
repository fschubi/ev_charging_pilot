# CLAUDE.md – Arbeitsgrundlage & Fortschritts-Doku

Projektgedächtnis für Claude. Wird bei jedem größeren Arbeitsschritt
aktualisiert und mit gepusht. Bewusst kompakt halten: das Fortschritts-Log
unten enthält nur die **letzten fünf Einträge**, ältere wandern unverändert an
den Anfang von `docs/CHANGELOG_DEV.md`.

## Projekt

**EV Charging Pilot** – Home-Assistant-Custom-Integration (HACS),
die Laden, Wakeup, Vorklimatisierung, Diagnose und Verbrauchsstatistik des
smart EQ fortwo 453 als **einziges** Steuerungssystem übernimmt.
**evcc ist kein Thema** – nicht erwähnen, nichts darauf ausrichten (Entscheidung Frank).

- Repo: https://github.com/fschubi/ev_charging_pilot (Branch `main`, **öffentlich**,
  HACS-Custom-Repo, Releases als Tags `vX.Y.Z`)
- Domain: `ev_charging_pilot` · Entitäten `*.ev_pilot_*` · Panel `/ev-pilot` ·
  `single_config_entry: true` · HA ≥ 2025.6 · Version in `manifest.json` (einzige Quelle,
  `const.VERSION` → Panel-Kopf und `?v=`-Cache-Buster)
- Lokaler Ordner heißt weiterhin `smart453_charging_center` (nur das Repo wurde umbenannt).
- **Spezifikation: [`docs/masterplan-v1.3.md`](docs/masterplan-v1.3.md)** (vollständig, §1–§16).
  Abschnittsverweise im Code (`§6.2`) beziehen sich darauf.
- Stand je Stufe und Gate: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Sprache: **Deutsch** für Commits, Doku, Changelog, UI-Texte, Event-Meldungen.
  Python-Bezeichner, Docstrings und Code-Kommentare englisch.
- Schwesterprojekt mit gleichen Konventionen: `../shutter_pilot`.

## Hardware (Masterplan §2)

| Gerät | Rolle | Anbindung |
| --- | --- | --- |
| Charge Amps Halo 11 kW | Ladefreigabe, Leistung, Zähler, Kabel | HACS „Chargeamps“, Cloud-Polling |
| Shelly 1 Mini Gen3 | CP-Unterbrechung (Wakeup) | lokal; `ON` = CP geschlossen = Normalzustand |
| OVMS v3 | SOC, Fahrdaten, Klima, SW-Wakeup | noch nicht geliefert; Mapping per Config Flow |

## Unverrückbare Regeln (Auszug §1.1)

1. Nur das Charging Center schaltet die Halo. Halo-interner Zeitplan aus.
2. **Auto nie nur zum Datenauffrischen wecken** (HV-Kontaktorzyklen).
3. Wakeup: OVMS vor CP, je max. 1× pro Ladefenster. CP nur mit
   `cp_failsafe_verified` und Health ≠ ERROR. Ziel-SOC **nie** über CP.
4. CP-Pulsdauer nur an einer Stelle (`cp_pulse_s` → `toggle_after`).
5. Laden gilt erst als gestartet, wenn stabil (N Messwerte, nicht Sekunden).
6. Abschaltung nur mit SOC-Qualität `GOOD`; im Zweifel weiterladen.
7. Keine hart codierten Entity-IDs – alles per Config-Flow-Selector.
8. **Keine produktive Automatik vor Messphase, Dry-Run und Einzeltest.**
   Default-Modus `dry_run`; OVMS-Befehle vorbelegt, gesendet nur mit `ovms_enabled`.
9. Was HA kann (`utility_meter`, LTS, Energy Dashboard, Notify), wird genutzt.

## Aufbau

```
custom_components/ev_charging_pilot/
  core/                HA-FREI (Test erzwingt das), nur stdlib
    engine.py          Herzstück: Engine.tick(now, raw) → Commands, Events, Sessions,
                       Trips, Notifications. Coordinator UND Replay treiben genau das.
    settings.py        Alle Optionen §13.2 (OPT_*-Keys, DEFAULT_OPTIONS, Settings.from_options)
    inputs.py          Inp-Enum (= Config-Entry-Keys), RawState, Parsing/Einheiten
    model.py           Value+Quality, Desired, Reason, ClimateRequest, Event
    quality.py / source_policy.py   Qualitätsstufen, Konflikte, Quellen, HV-Zyklen
    planner.py         Wochenpläne, One-Shot, Override, Ziel-SOC, Machbarkeit (UTC-Arithmetik)
    arbiter.py         Priorität §4.2; Lade- und Klima-Entscheidung getrennt
    executor.py        Soll/Ist-State-Machine §6, Kaskade, CP-Maskierung, manuelle Wakeups
    climate.py, health.py, costs.py, sessions.py, trips.py, statistics.py, monitor.py
    replay.py          Datensätze, Poll-Nachbildung, Abgleich mit realem Schalten
    mail.py            Monatsbericht-Mail: Text, Anbieter-Presets, SMTP mit PDF-Anhang
    prices.py          Preis-Parser (Tibber/Nordpool/EPEX/ENTSO-e/Paare, €/MWh), PriceSchedule, cheapest_blocks
    external.py        Automatische Fremdladeerkennung (OVMS live + SOC-Sprung)
    charge_test.py     Ladetest (Schritte, Ergebnis); learning.py Lernmodell; summary.py Texte
    pdf.py / report.py Eigener PDF-Writer (cp1252, Helvetica), Monats-/Jahresbericht
  coordinator.py       ChargingCenter: Tick 5 s + bei Zustandswechsel; live → HaPorts,
                       sonst nur Log „WOULD …“; Stores (state, events, monitor)
  ha_ports.py          Halo-Switch, Shelly-RPC, OVMS per MQTT-Topic oder Script
  notifications.py     Push + Actionable Notification (mobile_app_notification_action)
  price_source.py      PriceFetcher: Tibber-Service alle 30 min oder Preis-Entität
  reports.py           PDF erzeugen/listen, ReportView (/api/ev_charging_pilot/report, Login nötig)
  services.py (27), websocket_api.py, export.py, diagnostics.py, config_flow.py,
  system_check.py (Systemtest ohne Schalten)
  sensor/binary_sensor/switch/select/number/time/button.py   Entity-IDs ev_pilot_* (§12)
  frontend/ev-pilot-panel.js   Panel, Vanilla-JS, keine Steuerlogik (6 Reiter inkl. Einstellungen)
  settings_schema.py   Optionen als Formular-Schema für den Einstellungen-Reiter (get/set_settings)
  vehicle_image.py     Fahrzeugfoto: Upload (Admin), Auslieferung (Login), /api/ev_charging_pilot/vehicle_image
  discovery.py         Auto-Erkennung der Entitäten im Config Flow (Chargeamps-Plattform zuerst)
  brand/               Integrations-Icon (tools/make_brand.py)
phase0/                HA-Package Phase 0 + Messprotokoll
dashboards/            YAML-Standard-Dashboard
tools/gen_translations.py   erzeugt strings.json + translations/{de,en}.json – NICHT von Hand editieren
tests/core/            reine Kern-Tests inkl. world.py (simulierte Halo/Shelly/Auto)
tests/integration/     pytest-homeassistant-custom-component
```

Wichtige Details:
- Freshness/Samples über `state.last_reported` (Cloud-Polling meldet gleiche Werte erneut).
- Fensterstart **und Preisblöcke** werden verriegelt, sobald sie erreicht sind (sonst bricht
  steigender SOC die Ladung ab); nach Neustart aus dem Store wiederhergestellt.
- Die erste Kabelbeobachtung nach Neustart ist keine Aktivität (sonst SOC fälschlich STALE).
- Moduswechsel (Dry-Run-Switch) ändert nur `options["mode"]` ohne Reload; jede andere
  Optionsänderung lädt neu (Zustand kommt aus dem Store).
- Replay aus Recorder-Daten braucht `poll_interval_s` (Messung M1), weil der Recorder
  wiederholte Werte nicht speichert.

## Entwicklung

```bash
uv venv -p 3.13 .venv && uv pip install -p .venv/bin/python -r requirements-test.txt
.venv/bin/python -m pytest                       # ~250 Tests, < 1 min
uvx ruff check custom_components tests tools
node --check custom_components/ev_charging_pilot/frontend/ev-pilot-panel.js
python3 tools/gen_translations.py custom_components/ev_charging_pilot
```

Panel-Sichtprüfung: Testdaten per WS-Dump aus einer Testinstanz erzeugen und
`ev-pilot-panel` mit Fake-`hass` (callWS/callService) in einer HTML-Seite laden.

CI: `tests.yaml` (pytest, ruff, Panel-Syntax), `validate.yaml` (hassfest, HACS).

## Git-Workflow

- Branch `main`. Commits auf Deutsch, Attribution laut System-Vorgabe.
- Graphify-Regeln (`~/.claude/rules/graphify-git-workflow.md`) gelten erst, wenn
  `graphify-out/graph.json` existiert (aktuell nicht).
- Keine `git add .`/`-A`; Dateien gezielt stagen.

## Offene Punkte / Entscheidungen

- **Als Nächstes: [`docs/pruefliste-erste-nacht.md`](docs/pruefliste-erste-nacht.md)** – erste
  Nacht und Vorklimatisierung ausgewertet (Ergebnisse dort); offen: Wochenplan ab Mo mit
  Klima nach v0.20.1, SOC-Korrektur nach Ladeende beobachten, Shelly-WLAN.
- Gates §15 sind real zu erfüllen (Messungen, Dry-Run-Nächte, Feldtests) – Code ist fertig.
- `docs/messungen.md` ausfüllen → Defaults in `core/settings.py` anpassen.
- OVMS ist bei Frank eingebunden (HACS „OVMS“, Domain `ovms`). Befehlsweg wird automatisch
  erkannt (`ovms.send_command` + `vehicle_id` aus dem OVMS-Config-Eintrag, `ha_ports.ovms_path`);
  freigegeben nur mit Option `ovms_enabled` = „Lesen & Schreiben“ (Default aus).
- Ladeziele: je Plan (Ladeplan-Reiter) + `manual_target_soc` für „Jetzt laden“ (live, ohne Reload).
- RFID (§5.4): Variante C umgesetzt (Buttons/Push); Variante A nach Messung M6.
- Tibber, PDF-Berichte und Fremdladeerkennung wurden auf Franks Wunsch aus „Später“
  vorgezogen (v0.6) – entgegen §1.2 des Masterplans, bewusst.
- Preisoptimierung lädt standardmäßig in einem Block (Wakeup-Schonung); 2 Blöcke optional.
- Noch nicht gebaut: OCPP (Prüfauftrag §16 #9).
- Franks Mushroom-Karte (Dashboard „Smarthome“, Home) zeigt `sensor.ev_pilot_status`
  (Headline) – Texte dort also nur über `core/summary.py` ändern.

## Fortschritts-Log (letzte fünf)

- **2026-10-19 – v0.23.1 Temperaturquellen.** `outside_temperature`: HA-Sensor → Auto (GOOD)
  → Wetter; `Engine._changed` (Store `changed`) merkt echte Wertänderungen für
  `CHANGE_TRACKED`, unverändert > `UNCHANGED_STALE` (30 min) → LAST_KNOWN_VALID;
  `cabin_changed_at` daraus. OVMS-Außensensor 3–4 °C zu hoch (Feld 19.10.).
- **2026-10-19 – v0.23.2 Fahrten löschen.** Dienst `delete_trip` (`monitor.delete_trip`),
  Panel-Knopf in der Fahrt-Detailzeile; `monitor._repair_trips` (Verbrauch None < 1 km);
  `temperature_statistics` ohne Fahrten < `MIN_CONSUMPTION_KM`. Außentemperatur seit
  19.10. von der Gartenstation `sensor.hmip_swo_b_…_actual_temperature` (Reconfigure).
- **2026-10-20 – v0.23.3 Klima hält die Wallbox.** `executor._escalate` und Leistungsverlust in
  `_in_charging` ignorieren `Reason.CLIMATE` (kein `TOPUP_SKIPPED`/`INTERRUPTED`). Feld 20.10.:
  Wallbox aus 05:18:06, HVAC an 05:18:12 → Akku. Klima lief nur ~10 statt 15 min (homelink 3).
- **2026-10-20 – v0.24.0 Ladepause.** `ExecState.PAUSED`: Leistung weg bei SOC < Ziel →
  `CHARGE_PAUSED`, nach `PAUSE_WAIT` (15 min) einmal Weckkette (`_pause_recovery`, CP-Nachlauf
  `PAUSE_POST_CP_WAIT_S` 300 s), sonst `PAUSE_HOLD`; `Snapshot.below_target`; Engine
  `_pause_hold` hält den Wunsch über Fensterende bis Ziel/abgesteckt; `_full_charge_ended`
  nur bei SOC ≥ 99. Pushes `PAUSE_HOLD`/`PAUSE_RESUMED`. Pausen-Zustand übersteht keinen Neustart.
- **2026-10-20 – v0.24.1 Klima-Blöcke.** `AFTER_DEPARTURE_MIN` = 5; Phasen sent→running→gap
  →(Neustart `executor.request_climate_restart`, `homelink 1`, nach `CLIMATE_GAP` 30 s, max.
  `MAX_RESTARTS` 3, nur wenn ≥ 2 min übrig)→finished; Wunsch hält bis `until` (nur „done“ =
  manueller Stopp beendet früher). OVMS-Anleitung: smart nur 5-min-Blöcke, homelink 2/3
  mit Auto-Neustart – am 20.10. fehlte der 3. Block.
