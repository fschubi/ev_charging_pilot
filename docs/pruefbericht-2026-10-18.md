# Prüfbericht 2026-10-18 (Stand v0.19.0)

Sechs parallele Prüfungen (Lade-Kern, Preise/Planung, Statistik/Berichte/Mail, HA-Schicht,
Panel, Texte/Doku). Die schweren Funde wurden mit Simulationen (Testwelt `tests/core/world.py`)
bzw. Brute-Force-Vergleichen **nachgestellt und bestätigt** („bestätigt“). „plausibel“ =
aus dem Code eindeutig ablesbar, aber nicht end-to-end nachgestellt.

> **Stand 2026-10-18 abends: behoben** in v0.19.1 (K1, K7), v0.19.2 (K2–K6, K8, K10),
> v0.19.3 (H1, H2), v0.19.4 (K9, K11–K13, P1–P5), v0.19.5 (S1–S8, H3–H6), v0.19.6 (Panel),
> v0.19.7 (Stufe 3) und v0.19.8 (Texte/Doku). Jeder Fund hat einen Regressionstest
> (`tests/core/test_review_fixes.py` u. a.), der mit dem alten Code fehlschlägt.
> Bewusst nicht geändert (gering, eigene Abwägung): naive Zeitangaben am Tag der
> Zeitumstellung (Tibber/Nordpool liefern Zeitzonen), Push-Test meldet die Zustellung
> nicht zurück (HA-Notify ist „fire and forget“), Wochenfenster der Fremdladungen nach
> Datum, Temperaturstatistik je Jahr mit Gesamt-Durchschnittspreis, Begriff „SOC“ in
> Experten-Einstellungen.

Betrifft Frank = tritt in der aktuellen Einrichtung (Halo + Shelly + OVMS mit Stecker,
Tibber, 1 Preisblock) realistisch auf.

## Stufe 1 – vor dem nächsten Live-Betrieb beheben

| # | Bereich | Fund | Datei | Status | Frank |
|---|---|---|---|---|---|
| K1 | Kern | Nach jeder Ladung wird der SOC „veraltet“ (Ladeleistung zählt als Aktivität nach der letzten OVMS-Meldung) → Health DEGRADED, Push „System-Health DEGRADED“, Vorklimatisierung und SOC-Funktionen blockiert | `core/engine.py` ~293, `core/quality.py` ~54 | bestätigt | **ja** |
| K2 | Kern | Neustart/Moduswechsel nach „Auto hat fertig geladen“ (Halo noch an) → Wartezustand → **Auto wird geweckt** (OVMS/CP) und „Start fehlgeschlagen“ – verstößt gegen „Auto nie unnötig wecken“ | `core/executor.py` `_initial_state` ~369 | bestätigt | ja |
| K3 | Kern | Nach fehlgeschlagenem Start bleibt die Halo **an**; beim 2. Fehlschlag friert die Sicherheitssperre sie dauerhaft an → Auto lädt später unkontrolliert ohne Zielabschaltung | `core/executor.py` `_fail` ~426, `core/health.py` ~86 | bestätigt | ja |
| K4 | Kern | Vorklimatisierung bekommt ein eigenes Weck-Budget → nach einer gescheiterten Nacht erneut OVMS + CP kurz vor Abfahrt (max. 1× pro Fenster verletzt) | `core/climate.py` ~66, `core/model.py` window_key | bestätigt | ja |
| K5 | Kern | Neustart in einem gescheiterten Fenster zählt einen 2. Fehlschlag (doppelter Push, Health ERROR) | `core/executor.py` ~369/556 | bestätigt | ja |
| K6 | Kern | CP-Puls beendet „Jetzt laden“/Ladetest, wenn die Wallbox während des Pulses „kein Kabel“ meldet (Override-Ablauf nicht maskiert) | `core/engine.py` `_expire` ~241 | bestätigt | nein (OVMS-Stecker hält Kabel) – aber ohne OVMS-Stecker ja |
| K7 | Kern | Ziel-SOC der **einmaligen Abfahrt** wird nicht durchgesetzt (lädt z. B. statt bis 70 % bis ~95 %) – Priorität ONE_SHOT vor TARGET_SOC_REACHED | `core/arbiter.py` ~12, `core/engine.py` ~578 | bestätigt | **ja** |
| K8 | Kern | Sitzung wird nach „Auto fertig“ nicht geschlossen, solange das Kabel steckt → Nächte verschmelzen, Statistik/Kosten/Lernen falsch | `core/executor.py` ~671 | bestätigt | **ja** |
| H1 | HA | Monats-/Jahres-Sensoren: `last_reset` aus der Uhr, Wert bis 60 s alt → bei jedem Monatswechsel wird ein ganzer Monat negativ in der Langzeitstatistik/Energy-Dashboard verbucht | `sensor.py` ~301, `coordinator.py` ~397 | plausibel (Code eindeutig) | ja |
| H2 | HA | Hängt ein Halo-/OVMS-Dienst (Cloud), bleibt die Sperre gehalten → Steuerung (Zielabschaltung, Verlusterkennung) steht still; kein Zeitlimit um `ports.execute` | `coordinator.py` ~387, `ha_ports.py` | plausibel | möglich |

## Stufe 2 – falsche Zahlen / Funktionsfehler in realistischen Fällen

| # | Bereich | Fund | Datei | Status | Frank |
|---|---|---|---|---|---|
| K9 | Kern | Jede Unterbrechung mit wachem OVMS gilt als „Auto fertig“ → kein Neustart, keine Abbruch-Meldung | `core/engine.py` `_vehicle_finished` ~356 | plausibel | möglich |
| K10 | Kern | Phantom-Sitzungen (0 s), wenn innerhalb der 120-s-Schaltpause gestoppt wird – immer beim Ladetest | `core/executor.py` ~643 | bestätigt | ja (Ladetest) |
| K11 | Kern | Automatik aus: Ende von „Jetzt laden“ lässt die Halo an (lädt auf 100 %) | `core/engine.py` ~601 | plausibel | bei Automatik aus |
| K12 | Kern | Gelerntes Lade-Modell rechnet fest mit 15-min-Intervallen (`INTERVAL_H`) | `core/learning.py` ~29 | plausibel | nein (Default 15) |
| K13 | Kern | OVMS-Außentemperatur wird bei schlafendem Auto verworfen → TEMPERATURE_MISSING/DEGRADED bei Klima „auto“ | `core/source_policy.py` ~43 | plausibel | möglich |
| P1 | Preise | Zwei-Block-Suche findet das Optimum nicht (bis ~2× Kosten) **und** ist langsam (0,8–1,4 s pro Takt im Event-Loop) | `core/prices.py` ~279–312 | bestätigt | nein (1 Block) |
| P2 | Preise | ct/€-Erkennung pro Wert: Preise 0–5 ct und negative ct werden als €/kWh gelesen | `core/prices.py` `_eur` | bestätigt | nein (Tibber €) |
| P3 | Preise | Lücken in Preislisten werden durch Ende = nächster Start „zugekleistert“ (24-h-Slot) | `core/prices.py` `_close` | bestätigt | selten |
| P4 | Preise | Tibber-Fehler außerhalb der gefangenen Typen (Timeout, aiohttp) → kein Retry, keine Meldung | `price_source.py` ~101 | plausibel | möglich |
| P5 | Preise | Wechsel 15-min → Stunden-Quelle lässt alte Viertelstunden 3 Tage stehen | `core/engine.py` `set_prices` | plausibel | nein |
| S1 | Statistik | Fremdladungen bekommen das **UTC-Datum** → Ende nach Mitternacht landet im Vortag/Vormonat | `core/external.py` ~150 | bestätigt | ja |
| S2 | Statistik | Zusammengeführte Fahrten verlieren Energie bei OVMS-Zählerreset je Fahrt | `core/trips.py` ~85/126 | bestätigt | ja |
| S3 | Statistik | HA-Neustart während der Fahrt verschluckt die Kilometer (Fahrt bleibt GOOD) | `core/trips.py` ~123/186 | bestätigt | ja |
| S4 | Statistik | Monatsbericht 06:00 am 1. ohne die noch laufende Nachtladung; kein Nachholen, wenn HA um 06:00 aus war; stille Fehler | `coordinator.py` ~269 | plausibel | ja |
| S5 | Statistik | Manuelle Kilometerstände: Monat bekommt die ganze Lücke seit dem letzten Stand | `core/statistics.py` ~124 | bestätigt | nein (OVMS) |
| S6 | Statistik | PDF-Sitzungstabelle ≠ Monatssumme bei Ladung über Monatsende | `core/report.py` ~183 | bestätigt | selten |
| S7 | Statistik | SOC-Sprung-Erkennung (5 %) kann Kalibriersprünge/eingefrorenen Halo-Zähler als Fremdladung buchen | `core/external.py` ~100 | plausibel | möglich |
| S8 | Statistik | €/100 km ohne SOC-Ausgleich neben kWh/100 km mit Ausgleich | `core/statistics.py` | bestätigt | ja |
| U1 | Panel | Meldungen („gespeichert“, Fehler) verschwinden sofort – Toast liegt im neu gezeichneten Bereich | `frontend/ev-pilot-panel.js` ~522/691 | bestätigt | ja |
| U2 | Panel | Ansicht friert ein, solange ein Auswahlfeld fokussiert ist; Änderung erscheint erst nach Klick woanders | `ev-pilot-panel.js` ~589/686 | bestätigt | ja |
| U3 | Panel | „Speichern“ in den Einstellungen braucht nach Texteingabe 2 Klicks; Klick auf den aktiven Reiter verwirft Änderungen ohne Rückfrage | `ev-pilot-panel.js` ~850/665 | plausibel | ja |
| U4 | Panel | PDF öffnet sich in der iOS-App/Safari evtl. nicht (Pop-up nach await, blob-URL) | `ev-pilot-panel.js` ~1083 | plausibel | möglich |
| U5 | Panel | „Ergänzen“ bei Fremdladung: leer = 0 € gespeichert, SOC/km gehen verloren; Foto-Löschen meldet immer Erfolg | `ev-pilot-panel.js` ~1094/1051 | bestätigt (Code) | möglich |
| H3 | HA | Attribut `updated_at` ändert sich bei jedem Poll → Datenbank wächst unnötig | `sensor.py` ~53 | bestätigt (Code) | ja |
| H4 | HA | Listener-Leck bei fehlgeschlagenem Setup; alte Instanz kann nach Reload noch schalten | `coordinator.py` ~165/193 | plausibel | selten |
| H5 | HA | ERROR im Log beim ersten Reload nach jedem Boot (`async_listen_once`-Remover) | `price_source.py` ~66 | bestätigt | **ja** |
| H6 | HA | Dienste mit Seiteneffekt (Shelly konfigurieren, echte Mail, Replay) auch für Nicht-Admins | `services.py` ~267 | bestätigt | gering |

## Stufe 3 – Feinschliff, Randfälle

- Kern: eingefrorener Leistungswert verdeckt Ladeverlust; Endlosschleife, wenn die Halo „aus“ nie bestätigt; unbekanntes Kabel nach Neustart → Weckversuch; Halo-only ohne OVMS-Stecker startet evtl. nie.
- Preise: €/MWh ohne Einheit 10× zu hoch; „4 ct“/Minus in der Preiseingabe; Epoch als Text; halbstündliche Listen; Gleichstand → Start sofort; naive Zeiten am Zeitumstellungstag.
- Statistik: Wochen-/Monatswerte zählen abgebrochene Ladungen unterschiedlich; Qualität ignoriert geschätzte Fremdladungen; Ladeverlust ohne Plausibilitätsprüfung; `friendly_error` meldet SMTP-Fehler als „nicht erreichbar“.
- HA: Mail-Empfänger in Ereignistexten/Diagnose; persönliche Mail-Daten auch für Nicht-Admins sichtbar; gelöschter OVMS-Stecker kommt beim Start zurück; Fehler-Push ersetzt „Bericht fertig“-Push; Passwort im `repr` von `MailConfig`.
- Panel: Zeitleiste bei weit entfernten Fenstern unlesbar; `failure_hint` nie angezeigt; Replay-Auswahl springt zurück; Datums-Anzeige `dateOnly` in UTC.

## Texte und Doku (keine Funktionsfehler)

- Englische Codes beim Nutzer: Push „System-Health DEGRADED“ mit Codes, CP-Push „CP_STATE_UNKNOWN“, PDF „Ort: public“, „Ergebnis: CHARGE_START_FAILED“, „Qualität: GOOD/ESTIMATED“, Panel „Override: until_unplugged“, englische Fehlertexte bei Diensten.
- Begriffe vereinheitlichen: „Heute Nacht“/„One-Shot“ → „Einmalige Abfahrt“; „Dry-Run“ vs „Probebetrieb“; „Preis-Sensor“ vs „Preis-Entität“; Sensor „Ladezustand“ meint den Ablauf, nicht den SOC; „zu Hause“ einheitlich.
- Veraltet: README (OVMS-Befehle „leer“, „ab 90 % langsamer“, falsche Entity-ID, 21 von 26 Diensten, Mail fehlt), ROADMAP endet bei v0.6, CLAUDE.md („OVMS leer = gesperrt“, „~100 Tests“ statt ~210), Optionsbeschreibung OVMS-Befehle und Wakeup-Default, Preisformat-Beschreibung.
- Options-Flow erlaubt Akkukapazität 5–30 kWh, Panel 5–150 → Formular kann ungültig werden.

## Was geprüft und in Ordnung ist

- Keine XSS-Lücke im Panel, alle Knöpfe verdrahtet, Feldnamen stimmen mit dem Backend.
- Mail-Passwort verlässt HA nie, Diagnose geschwärzt, Pfade gegen Traversal gesichert, PDF/SMTP/Datei-I/O im Executor.
- Dienste, `services.yaml` und Übersetzungen vollständig synchron; Version, Changelog und Tag stimmen.
- Einzelblock-Preissuche exakt optimal; Zeitumstellung und UTC-Rechnung im Planer korrekt; Dauer-/Taper-Rechnung konsistent.
- Monatsgrenzen in Ortszeit, SOC-Ausgleich, Division durch null abgesichert, PDF-Sonderzeichen korrekt.
