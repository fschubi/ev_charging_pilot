# Roadmap – Umsetzungsstand

Verbindlich ist [Masterplan §15](masterplan-v1.3.md#15-roadmap-und-definition-of-done)
mit seinen Gates. Diese Datei hält nur fest, wo der Code gegenüber dem Plan steht.

## Phase 0 – Automation und Messphase

| Punkt (§15) | Stand |
| --- | --- |
| Shelly konfiguriert, Checkliste §3.6 | offen (Hardware) |
| Halo-Zeitplan aus, evcc steuert nicht | offen (Hardware) |
| Automation: Halo an → Leistung prüfen → sonst CP-Puls → prüfen → Push; morgens aus | **teilweise**: `phase0/smart_eq_phase0.yaml` schaltet nur an/aus, Wakeup-Kette und Push fehlen noch |
| `utility_meter` + Energy Dashboard | Package fertig, Energy Dashboard manuell |
| Recorder in voller Auflösung | offen (Recorder-Konfig ergänzen) |
| Messungen | Protokoll M1–M8 in `phase0/README.md`, Ergebnisse in `docs/messungen.md` |

**Gate:** Messwerte dokumentiert, Zeitkonstanten in §13.2 eingetragen, ≥ 5 Nächte als Replay-Daten.

## v0.1 – Kern, Read-only, Dry-Run

| Punkt | Stand |
| --- | --- |
| Paketstruktur mit HA-freiem Kern | erledigt (Test erzwingt HA-Freiheit) |
| Config Flow, Entity-Auswahl | erledigt; Name/Dry-Run-Schritt aus §13.1 fehlt |
| Adapter mit Wertmodell | erledigt (`coordinator._value`) |
| Planner, Arbiter, Executor im Dry-Run | erledigt (über v0.1 hinaus: auch abfahrtsbasiert, Override, One-Shot) |
| Event Log, Health, Diagnostics | erledigt |
| Replay der Phase-0-Nächte | **offen**: `core/replay.py`, Aufzeichnung der Snapshots |
| Tests §14.1 Ladeerkennung, Kaskade, Maskierung, Neustart | erledigt |

**Gate:** 7 Nächte Dry-Run parallel zur Phase-0-Automation.

## Abweichungen zum Plan, die noch anzugleichen sind

- Entity-IDs/Namen nach §12.1/§12.2 (`sensor.smart_eq_executor_state` …);
  aktuell `sensor.smart_eq_charging_center_*`. Fehlende Entities: u. a.
  `switch.smart_eq_automation`, `select`/`number`/`time`-Steuer-Entities,
  `binary_sensor.smart_eq_vehicle_connected`, `_cp_failsafe_ok`.
- Services §12.3 und WebSocket-API §12.4 fehlen noch.
- Options-Flow §13.2: `mode` (dry_run | live | replay) statt nur Switch;
  `stable_samples`, `stable_min_s`, `loss_timeout_s`, `mask_grace_s`,
  `ovms_enabled`, `cp_fallback_enabled`, Wartezeiten, Benachrichtigungs-Kategorien.

## v0.2 – v0.5, später

Siehe §15. Noch nicht begonnen: Live-Schalten mit Gate, Actionable
Notification, YAML-Dashboard (v0.2); Sessions mit Kosten, Config-Drift live
(v0.3); OVMS (v0.4, nach Lieferung); Trips, Statistik, Export, eigene
Oberfläche (v0.5).
