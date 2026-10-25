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

- **2026-10-25 – v0.27.16 SOC-Ausreißer.** `Engine._track_soc_jumps`: GOOD-SOC-Sprung >
  `SOC_JUMP_PCT` (5) → `_confirmed` hält die Ziel-Abschaltung `TARGET_CONFIRM` (3 min) zurück;
  `_topping_up` (gespeichert): nach `fresh_below` kein „held“ mehr bis Ziel erreicht. Tests mit
  synthetischen SOC-Sprüngen aufs Ziel laufen jetzt über einen Zwischenschritt. Prüfbericht M3.
- **2026-10-25 – v0.27.17 enforce_target.** `_arbitrate`: `enforce` (Klima läuft +
  ENFORCE_TARGET) überspringt den Ziel-Hold-Zweig („held“); abgeschaltet wird nur über
  `target_soc_wish` bei Ziel + `ENFORCE_TARGET_MARGIN_PCT`. Prüfbericht M4.
- **2026-10-25 – v0.27.18 Pause gespeichert.** Engine `pause_hold` (Ziel + Desired ohne Klima,
  `held_key`) und Executor `pause_since`/`pause_woken` im Store; `_initial_state`: Halo an +
  Pause → PAUSED (bei Leistung CHARGING + `_clear_pause`). Prüfbericht M5.
- **2026-10-25 – v0.27.19 Zweiter Preisblock.** `WindowAttempts.charged` (gespeichert) bei
  `_charging_started`; `_escalate` ohne Versuche + `charged` → `_later_block_not_started`
  (Event `BLOCK_NOT_STARTED` WARNING, IDLE, kein Fehlstart-Zähler), Push „Ladeblock nicht
  gestartet“ mit `retry`. Prüfbericht M6.
- **2026-10-25 – v0.27.20 Rechte.** `ChargingEntity.async_require_admin` (Kontext-User, ohne
  User = Automation erlaubt): `DryRunSwitch.turn_off`, Button `reset_error` (`admin=True`);
  Dienst `reset_error` in `ADMIN_SERVICES`. `Notifier._offered` (Aktion → gültig bis, Push-ID,
  `OFFER_VALID` 12 h): Aktionen nur, wenn angeboten, eine Antwort je Push. Prüfbericht M8.
