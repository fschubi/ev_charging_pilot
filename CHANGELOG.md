# Changelog

## 0.6.1 – 2026-10-13

- **Einrichtung mit automatischer Erkennung:** Die Integration sucht Halo-Entitäten
  (Chargeamps), das CP-Relais samt IP aus der Shelly-Integration, das Handy der
  Companion-App und – falls vorhanden – OVMS-Entitäten und belegt die Felder vor.
  Jeder Schritt zeigt, wie viele Felder erkannt wurden; alles bleibt änderbar.
- Jedes Feld der Einrichtung hat einen Erklärtext.
- „Neu konfigurieren“ ergänzt leere Felder ebenfalls automatisch (z. B. OVMS später).

## 0.6.0 – 2026-10-13

- **Tibber und dynamische Tarife:** Preise aus `tibber.get_prices` oder jeder
  Preis-Entität (Nordpool `raw_today/raw_tomorrow`, EPEX `data`, `today/tomorrow`).
  Abfahrtsbasierte Pläne laden in den günstigsten Stunden (Standard: ein Block,
  optional zwei). Kosten je 15-min-Intervall mit dem echten Preis. Festpreis bleibt
  Rückfall. Neue Sensoren `current_price`, `next_charge_cost`, Service `refresh_prices`.
- **PDF-Berichte:** Monats- und Jahresbericht (Hausabrechnung, Sessions,
  Fremdladungen, Verbrauch, Temperaturgruppen) ohne Zusatzpakete; automatisch am 1.
  um 06:00 mit Push; Service `create_report`; Download nur mit Login.
- **Automatische Fremdladeerkennung:** OVMS „lädt“ ohne Halo-Leistung oder
  SOC-Sprung ohne passende Halo-Energie → geschätzte Fremdladung mit Push; im Panel
  ergänzbar.
- Fix: Die erste Beobachtung des Kabelzustands nach einem Neustart galt als
  Aktivität und machte einen alten SOC fälschlich zu STALE.
- Fertig-Zeit bei Preisblöcken korrekt, Pläne in ganzen Minuten.
- evcc spielt keine Rolle mehr – alle Hinweise entfernt.

## 0.5.0 – 2026-10-13

Komplette Integration nach Masterplan v1.3 (v0.1–v0.5). Startet weiterhin im
Dry-Run; die Gates aus §15 (Messungen, Feldtests) stehen noch aus.

### Phase 0
- Package mit Wakeup-Kette: Halo an → Leistung prüfen → CP-Puls per
  `toggle_after` → prüfen → Push; Abend-Erinnerung; per `check_config` validiert.

### Kern (HA-frei)
- `Engine` bündelt die komplette Tick-Pipeline; Replay ist dieselbe Engine
  mit aufgezeichneten Eingaben, inklusive Nachbildung des Cloud-Pollings und
  Abgleich gegen das reale Schalten.
- Settings nach §13.2, Quellenpolicy, Konflikterkennung, HV-Zyklen-Wächter.
- Mehrere Wochenpläne, verriegelter Fensterstart, Machbarkeit mit Fertig-Zeit.
- Vorklimatisierung mit Temperaturprofilen und `after_target_soc`-Regel.
- Lade-Sessions mit 15-min-Intervallen und Kosten, Fahrten mit Fahrtgrenzen
  und PARTIAL-Rekonstruktion, Monats-/Jahresbilanz mit ΔSOC,
  Temperatur- und Saisonstatistik, Fremdladen, manuelles Odometer.

### Home Assistant
- Entitäten nach §12 (`sensor.smart_eq_*` …): Status, Laden, Fahrzeug,
  Energie & Kosten, Binärsensoren, Automatik/Dry-Run, Override-Modus,
  Abfahrt und SOC-Ziele, Buttons inkl. Klima und Wakeups.
- 19 Services (§12.3), WebSocket-API (§12.4), Export CSV/JSON.
- Config Flow in fünf Schritten plus Rekonfiguration, Options-Menü mit allen
  Werten aus §13.2, Preis-Historie mit Gültigkeitsdatum, Migration von 0.1.
- Push mit Kategorien, Rückfrage-Push beim Einstecken mit drei Aktionen.
- Sidebar-Panel mit Cockpit, Ladeplan, Hausstrom, Drive & Energy, Diagnose.
- YAML-Standard-Dashboard.

## 0.1.0 – 2026-10-13

Erste Entwicklungsversion, läuft ausschließlich im Dry-Run.

- HA-freier Kern: Datenqualität mit `LAST_KNOWN_VALID`, Wochenplan
  (abfahrtsbasiert mit Rückfall auf festen Start), One-Shot „Heute Nacht
  laden“, Manual Override, Ziel-SOC, Arbiter mit fester Priorität.
- Executor als Soll/Ist-State-Machine mit stabiler Ladeerkennung,
  Wakeup-Kaskade (OVMS → CP), CP-Maskierung, Schalt-Cooldown, Ladeende vs.
  Abbruch und Neustart-Rekonstruktion.
- System-Health (HEALTHY/DEGRADED/ERROR) inkl. Shelly-Config-Drift-Check.
- Intervallbasiertes Kostenmodell mit Preis-Historie.
- Config-Flow mit Entity-Selektoren, Options-Flow für Plan und Technik.
- Entitäten: Zustand, Soll-Grund, Health, nächster Ladestart, erwarteter
  SOC, Override/Konflikt/Problem, Dry-Run-Switch, Bedien-Buttons.
- Push-Benachrichtigungen, Event-Log mit 90 Tagen Aufbewahrung, Diagnostics.
- Phase-0-Package: Zeitautomation, `utility_meter`, Messprotokoll, CP-Test.
