# CLAUDE.md – Arbeitsgrundlage & Fortschritts-Doku

Projektgedächtnis für Claude. Wird bei jedem größeren Arbeitsschritt
aktualisiert und mit gepusht. Bewusst kompakt halten: das Fortschritts-Log
unten enthält nur die **letzten fünf Einträge**, ältere wandern unverändert an
den Anfang von `docs/CHANGELOG_DEV.md`.

## Projekt

**Smart EQ 453 Charging Center** – Home-Assistant-Custom-Integration (HACS),
die Laden, Wakeup, Vorklimatisierung, Diagnose und Verbrauchsstatistik des
smart EQ fortwo 453 als **einziges** Steuerungssystem übernimmt (ersetzt evcc).

- Repo: https://github.com/fschubi/smart453_charging_center (Branch `main`)
- Domain: `smart_eq_charging` · `single_config_entry: true` · HA ≥ 2025.1
- **Spezifikation: [`docs/masterplan-v1.3.md`](docs/masterplan-v1.3.md)** –
  verbindlich. Abschnittsverweise im Code (`§6.2`) beziehen sich darauf.
- Sprache: **Deutsch** für Commits, Doku, Changelog, UI-Texte. Python-Bezeichner,
  Docstrings und Code-Kommentare englisch.
- Schwesterprojekt mit gleichen Konventionen: `../shutter_pilot`.

## Hardware (Masterplan §2)

| Gerät | Rolle | Anbindung |
| --- | --- | --- |
| Charge Amps Halo 11 kW | Ladefreigabe, Leistung, Zähler, Kabel | HACS „Chargeamps“, Cloud-Polling |
| Shelly 1 Mini Gen3 | CP-Unterbrechung (Wakeup) | lokal; `ON` = CP geschlossen = Normalzustand |
| OVMS v3 | SOC, Fahrdaten, Klima, SW-Wakeup | **noch nicht angebunden** (MQTT offen, §16) |

## Unverrückbare Regeln (Auszug Masterplan §1.1)

1. Nur das Charging Center schaltet die Halo. Kein evcc parallel, Halo-Zeitplan aus.
2. **Auto nie nur zum Datenauffrischen wecken** (HV-Kontaktorzyklen).
3. Wakeup: OVMS vor CP, je max. 1× pro Ladefenster. CP nur mit
   `cp_failsafe_verified` und Health ≠ ERROR. Ziel-SOC **nie** über CP.
4. CP-Pulsdauer nur an einer Stelle (`cp_pulse_s` → `toggle_after`).
5. Laden gilt erst als gestartet, wenn stabil (N Messwerte, nicht Sekunden).
6. Abschaltung nur mit SOC-Qualität `GOOD`; im Zweifel weiterladen.
7. Keine hart codierten Entity-IDs – alles per Config-Flow-Selector.
8. **Keine produktive Automatik vor Messphase, Dry-Run und Einzeltest.**
   Die Integration startet immer im Dry-Run (Switch `dry_run`).
9. Was HA kann (`utility_meter`, LTS, Energy Dashboard, Notify), wird genutzt.

## Aufbau

```
custom_components/smart_eq_charging/
  core/              HA-FREI (Test erzwingt das): nur stdlib
    model.py         Value+Quality, Desired, Reason, Event, Clock
    quality.py       Qualitätsstufen inkl. LAST_KNOWN_VALID, Konflikte
    planner.py       Wochenplan, One-Shot, Override, Ziel-SOC, Machbarkeit (DST-sicher, UTC-Arithmetik)
    arbiter.py       feste Priorität §4.2; Health ERROR → charger_enabled=None (einfrieren)
    executor.py      Soll/Ist-State-Machine §6, Wakeup-Kaskade, CP-Maskierung; reine step()-Funktion
    health.py        HEALTHY/DEGRADED/ERROR
    costs.py         Preis-Historie, 15-min-Intervalle, Session-Kosten
    ports.py         Command/CommandKind, Port-Protokolle
  coordinator.py     ChargingCenter: liest Entities → Values, Tick alle 5 s, Push, Stores
  ha_ports.py        Halo-Switch, Shelly-RPC (toggle_after), Config-Drift-Check
  config_flow.py     Entities (user/reconfigure) + Options (Plan, Technik/Kosten)
  sensor/binary_sensor/switch/button.py, diagnostics.py, entity.py
phase0/              HA-Package für Phase 0 (Zeitautomation, Messprotokoll, CP-Test)
docs/                Masterplan, Roadmap, Messergebnisse
tests/core/          reine Kern-Tests (Millisekunden)
tests/integration/   pytest-homeassistant-custom-component
```

Datenfluss pro Tick: Entities → `Value` (Qualität) → Planner-Wünsche →
`arbitrate()` → `Snapshot` → `Executor.step()` → `Command`s → `HaPorts.dispatch()`
(Dry-Run: nur Log + Event `DRY_RUN`). Leistungs-Samples werden über
`state.last_reported` unterschieden (Cloud-Polling liefert oft gleiche Werte).

## Entwicklung

```bash
uv venv -p 3.13 .venv && uv pip install -p .venv/bin/python -r requirements-test.txt
.venv/bin/python -m pytest            # alle Tests
uvx ruff check custom_components tests
```

CI: `.github/workflows/tests.yaml` (pytest + ruff), `validate.yaml` (hassfest, HACS).

## Git-Workflow

- Branch `main`. Commits auf Deutsch, Attribution laut System-Vorgabe.
- Graphify-Regeln aus `~/.claude/rules/graphify-git-workflow.md` gelten, sobald
  `graphify-out/graph.json` existiert (aktuell noch nicht angelegt).
- Keine `git add .`/`-A`; Dateien gezielt stagen.

## Offene Punkte / Entscheidungen

- **Masterplan v1.3 endet bei §11.** §12 (WebSocket-API/Frontend), §16
  (offene Prüfaufträge: OVMS-Anbindung, OCPP) und die Roadmap fehlen in der
  Datei. `docs/ROADMAP.md` ist eine **abgeleitete** Roadmap – mit Frank
  abgleichen, sobald die vollständige Fassung vorliegt.
- OVMS-Wakeup/Klima: Port wirft `PortError`, `ovms_available=False` fest im
  Coordinator, bis die Befehle am Fahrzeug getestet sind.
- RFID-Variante (§5.4): Arbeitsannahme C (Button/Push), Messung M6/M7 offen.
- Sessions/Trips/Monatsstatistik (§10) und Klima (§9) noch nicht gebaut.
- Repo ist **privat**; für HACS-Installation als Custom-Repo muss es öffentlich werden.

## Fortschritts-Log (letzte fünf)

- **2026-10-13 – v0.1.0 Grundgerüst.** Repo angelegt, Masterplan nach `docs/`.
  HA-freier Kern (Modell, Qualität, Planner, Arbiter, Executor mit Kaskade und
  CP-Maskierung, Health, Kosten) mit 50+ Tests inkl. DST und Neustart.
  Integration mit Config-/Options-Flow, Entitäten, Dry-Run-Default, Push,
  Event-Log (90 Tage), Diagnostics. Phase-0-Package mit Messprotokoll.
