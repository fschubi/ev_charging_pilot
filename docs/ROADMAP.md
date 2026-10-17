# Roadmap – Umsetzungsstand

Verbindlich ist [Masterplan §15](masterplan-v1.3.md#15-roadmap-und-definition-of-done).
Jede Stufe hat ein **Gate**, das nur im realen Betrieb erfüllt werden kann.
„Code fertig“ heißt deshalb: Funktion gebaut und automatisiert getestet –
das Gate selbst ist erst nach Messung bzw. Feldtest erfüllt.

| Stufe | Code | Gate (real) |
| --- | --- | --- |
| Phase 0 | fertig (`phase0/`) | offen: Messungen M1–M8, ≥ 5 Nächte, Zeitkonstanten in §13.2 |
| v0.1 Kern, Read-only, Dry-Run | fertig | offen: 7 Nächte Dry-Run parallel zu Phase 0, Replay stimmt |
| v0.2 Live-Basis, Bedienung | fertig | offen: `cp_failsafe_verified`, Tests §14.3 ohne OVMS |
| v0.3 Automatischer Ladeplan | fertig | offen: 14 Nächte live ohne unbemerkten Fehlstart |
| v0.4 OVMS | fertig (Mapping per Config Flow, Befehle per Options Flow) | offen: OVMS geliefert, Werte 2 Wochen plausibel |
| v0.5 Drive & Energy, Oberfläche | fertig | – |
| v0.6 Tibber/dynamischer Preis, PDF-Berichte, Fremdladeerkennung | fertig | offen: Tibber-Abruf und Erkennung im Alltag prüfen |
| Später | OCPP lokal (Prüfauftrag §16 #9) | nicht begonnen |

## Phase 0 – Automation und Messphase

- [x] HA-Automation: Halo an → Leistung prüfen → CP-Puls (`toggle_after`) → prüfen → Push; morgens aus
- [x] `utility_meter` Monat/Jahr
- [x] Messprotokoll ins Logbuch, Abend-Erinnerung
- [x] Replay-Datensätze aus der Recorder-Historie (`create_replay_dataset`)
- [ ] Shelly konfiguriert, Checkliste §3.6 (Hardware)
- [ ] Halo-Zeitplan aus (Hardware)
- [ ] Messungen M1–M8 in `docs/messungen.md`

## v0.1 – Kern, Read-only, Dry-Run

- [x] Paketstruktur mit HA-freiem Kern (`core/`, Test erzwingt HA-Freiheit)
- [x] Config Flow mit Entity-Auswahl (§13.1)
- [x] Wertmodell mit Quelle, Alter, Qualität inkl. `LAST_KNOWN_VALID`
- [x] Planner, Arbiter, Executor im Dry-Run
- [x] Event Log (Rotation), Health, Diagnostics (redigiert)
- [x] Replay mit Poll-Nachbildung und Abgleich gegen reales Schalten
- [x] Tests §14.1: Ladeerkennung, Kaskade, Maskierung, Cooldown, Ziel-SOC, LKV, Arbiter, Neustart, DST

## v0.2 – Live-Basis und manuelle Bedienung

- [x] Halo-Schalten über Executor (Cooldown, Bestätigung, max. 3 Versuche)
- [x] CP-Puls über Executor, Rückstellprüfung, Maskierung, Drift-Check
- [x] Manual Override (alle Modi), One-Shot, Buttons, Services (§12.3)
- [x] Push mit Kategorien, Actionable Notification beim Einstecken
- [x] YAML-Standard-Dashboard (`dashboards/`)

## v0.3 – Automatischer Ladeplan

- [x] Mehrere Wochenpläne, abfahrtsbasiert mit verriegeltem Fensterstart
- [x] Kaskade mit Versuchslimits je Fenster
- [x] Ladeende vs. Abbruch (OVMS, Halo-Status, Timeout) mit einem Neustartversuch
- [x] Sessions mit 15-min-Energieintervallen und Kosten (Preis-Historie)
- [x] Config-Drift-Check (Halo-Zeitplan, Shelly auto_on/initial_state/Pulsdauer)

## v0.4 – OVMS

- [x] Mapping SOC, SOH, Reichweite, Odometer, Ladestatus, Temperaturen, HV-Zyklen, 12 V
- [x] Quellenpolicy, Konflikterkennung, `LAST_KNOWN_VALID`
- [x] OVMS-Wakeup vor CP (Befehl per MQTT-Topic oder Script, leer = gesperrt)
- [x] Ziel-SOC-Abschaltung (nur mit GOOD), Machbarkeitsprognose, Abend-Push
- [x] Vorklimatisierung mit Profilen und `after_target_soc`-Regel
- [x] HV-Zyklen-Überwachung (Tagesschwelle, Zyklus ohne Anlass)

## v0.5 – Drive & Energy Monitor und eigene Oberfläche

- [x] Fahrten mit Fahrtgrenzen, PARTIAL-Rekonstruktion, manuelles Odometer
- [x] Fremdladen erfassen/löschen
- [x] Monats-/Jahresbilanz mit ΔSOC, Ladeverluste, €/100 km, Qualitätskennzeichnung
- [x] Temperatur- und Saisonstatistik
- [x] CSV/JSON-Export
- [x] Sidebar-Panel mit den Ansichten aus §12.5

## v0.6 – vorgezogen aus „Später“

- [x] Dynamischer Preis: Tibber (`tibber.get_prices`) oder jede Preis-Entität
      (Nordpool, EPEX, generische Attributlisten); Festpreis bleibt Rückfall
- [x] Planner „günstigste Intervalle“: abfahrtsbasierte Pläne laden in den billigsten
      Stunden, standardmäßig in **einem** Block (jeder Block kann einen Wakeup kosten)
- [x] Kosten je Energieintervall mit dem tatsächlichen Preis
- [x] PDF-Monats- und Jahresbericht (eigener PDF-Writer, keine Zusatzpakete),
      automatisch am 1. um 06:00, Download nur mit Login
- [x] Automatische Fremdladeerkennung: live über OVMS „lädt“ ohne Halo-Leistung,
      Rückfall über SOC-Sprung, den der Halo-Zähler nicht erklärt; Ergebnis ist eine
      geschätzte Fremdladung zum Ergänzen

## v0.7 – v0.19 (Oktober 2026)

Ausführlich im [CHANGELOG](../CHANGELOG.md). Die wichtigsten Schritte:

- [x] Umbenennung in EV Charging Pilot, generische Wallbox-Erkennung, Einstellungen-Reiter
- [x] OVMS-Befehle automatisch (`ovms.send_command`), gesendet nur mit „Lesen & Schreiben“
- [x] Einstecken über OVMS-Stecker + Standort (Halo meldet das Kabel nur bei Freigabe)
- [x] Lernendes Lade-Modell, Taper ab 80 %, voller Akku höchstens 2 h vor Abfahrt
- [x] Weiterladen nach Blockende, verpasste Preisblöcke neu planen
- [x] Ladestrom je Plan/Einmal-Abfahrt/„Jetzt laden“
- [x] Test-Center: Systemtest, Ladetest, Push-Test Preisabfrage, Test-Mail
- [x] Fremdladen: Preis per Push (Knöpfe, Ziffernblock-Dialog)
- [x] Monatsbericht per E-Mail, Betrag per Push an weitere Handys
- [x] Weitere Preisformate, „Preisquelle prüfen“
- [x] Gesamtprüfung 2026-10-18 ([Prüfbericht](pruefbericht-2026-10-18.md)), alle Stufen
      behoben in v0.19.1–v0.19.8

Noch offen sind die realen Gates (§15): Messungen M1–M8 in [messungen.md](messungen.md),
Dry-Run-Nächte, Feldtests.

## Offene Fragen (§16)

Fragen 1–6 beantwortet Phase 0, 7–8 die OVMS-Einrichtung, 9 (OCPP) und
10 (§14a-Anmeldung) sind Prüfaufträge außerhalb des Codes. `grid_limit_kw`
im Options Flow bildet eine §14a-Dimmung bereits ab.
