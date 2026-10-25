# Prüfbericht 2026-10-24 (Stand v0.27.1)

Fünf parallele Prüfungen (Steuerlogik, Berechnungen, Anzeige, HA-Schicht, Szenario-Stresstest
über mehrere Tage) plus Live-Abgleich in Franks Instanz. Testlauf vorher: 302 Tests grün,
ruff und Panel-Syntax sauber – die Funde unten fallen den bisherigen Tests nicht auf.
„reproduziert“ = mit der Testwelt `tests/core/world.py` bzw. einem Skript nachgestellt.

> **Stand 2026-10-25: Kritisch und Hoch behoben**, je ein Release: K1 v0.27.2, K2 v0.27.3,
> H1 v0.27.4, H2 v0.27.5, H3 v0.27.6, H4 v0.27.7, H5 v0.27.8, H6 v0.27.9, H7 v0.27.10.
> Jeder Fund hat einen Regressionstest (`tests/core/test_review_2026_10_24.py`,
> `test_session_energy.py`, `test_monitor.py`, `tests/integration/test_setup.py`,
> `test_vehicle_commands.py`), der mit dem alten Code fehlschlägt.
> **Mittel behoben** (je ein Release): HV-Zyklen-Sensor v0.27.11, Einheit v0.27.12, `inf` v0.27.13,
> Status Klima ohne Kabel v0.27.14, Panel-Details v0.27.15, SOC-Ausreißer/Nachladen v0.27.16,
> `enforce_target` v0.27.17, Pause nach Neustart v0.27.18, zweiter Preisblock v0.27.19,
> Rechte v0.27.20, Statistik v0.27.21 (inkl. Klima-Nachlauf aus „Niedrig“).
> **Niedrig behoben** (thematisch gebündelt): Panel v0.27.22, Texte/Werte v0.27.23,
> Ausschalten/Ø-Leistung v0.27.24, Preise/Intervalle v0.27.25, HA-Robustheit v0.27.26,
> Replay/Fahrstil/Einheiten/Klima-Monat v0.27.27 – Rest siehe „Bewusst nicht geändert“.

## Kritisch

- **K1 Historie weg nach Downgrade** (reproduziert) – `from_dict` mit `cls(**values)` warf bei
  unbekannten Feldern; der Shutdown nach dem Setup-Fehler speicherte den leeren Zustand über
  alle Stores. → v0.27.2
- **K2 Volles Auto wird geweckt** (reproduziert) – SOC LAST_KNOWN_VALID ≥ Ziel öffnet trotzdem
  das Fenster, nichts fließt, Weckkette läuft (Regel 2). → v0.27.3

## Hoch

- **H1 Zweites Weck-Budget nach Ladepause** (reproduziert) – Pause-Halten ändert `window_key`
  (`valid_until=None`), neue Versuchszähler: 2× OVMS + 2× CP pro Nacht (Regel 3).
- **H2 Shelly-Ausfall > 3 min ignoriert den Ziel-SOC** (reproduziert) – CP_STATE_UNKNOWN →
  ERROR → Sicherheits-Halt friert auch das Abschalten ein; laut §8.2 nur CP-Wakeup sperren.
- **H3 Fehlstart-Sperre löst sich nie** (reproduziert) – REPEATED_START_FAILURE → ERROR, ohne
  Ladung wird der Zähler nie zurückgesetzt; ab der dritten Nacht kein Laden mehr.
- **H4 Dry-Run → Live mitten im Fenster lädt 0 kWh** (reproduziert) – `set_shadow` lässt
  `_failed_window`/Versuche aus dem Probebetrieb stehen.
- **H5 Eingefrorene Halo-Leistung weckt eine laufende Ladung** (reproduziert) – Pause-Erkennung
  nur über Halo-Leistung, OVMS „lädt“ (GOOD) unbeachtet; CP-Puls unterbricht die Ladung.
- **H6 Zähler-Ausreißer/-Reset** (reproduziert) – ein 0-Wert des Halo-Zählers erzeugt
  Phantomenergie in den Intervallen (≈1006 kWh / 302 €); Reset in der Session: 0 kWh, aber Kosten.
- **H7 „Klima stopp“ ohne `ovms_enabled`** – `request_climate_stop` prüft `climate_available`
  nicht (Regel 8).

## Mittel (behoben, v0.27.11–v0.27.21)

- HV-Kontaktor-Sensor `TOTAL_INCREASING`, Quelle bei Frank sind die *verbleibenden* Zyklen
  (fallend) → LTS wertet jede Abnahme als Reset.
- Diagnose zeigt normalisierte Watt mit Roh-Einheit kW („9139.37 kW“), `websocket_api._value`.
- SOC-Ausreißer beendet Ladung; Hysterese wirkt als Abschaltschwelle (Ende 87 statt 90 %,
  bei Rauschen bis 25 Schaltungen/h).
- `enforce_target` verhält sich wie `battery_only` (Ziel-Hold überstimmt Klima-Marge).
- Pause-Halten übersteht keinen Neustart.
- Zwei Preisblöcke teilen ein Weck-Budget → zweiter Block START_FAILED.
- `inf` als Sensorwert lässt jeden Tick abstürzen (`inputs._float`).
- Rechte: Dry-Run-Switch, `reset_error` (leert Weck-Zähler) und Push-Aktionen ohne Prüfung.
- Statistik: km rekonstruierter Fahrten ohne Energie; Lernmodell inkl. Klimaenergie;
  `_charge_battery_kwh` bei später Erkennung zu niedrig; Klimaenergie ohne GOOD-Akkuleistung zu hoch.
- Status „Nicht eingesteckt“ statt „Vorklimatisierung läuft“ bei Klima aus dem Akku.
- Panel: nach Service-Aufruf hängen offene Details auf „Lade …“.

## Niedrig (behoben, v0.27.22–v0.27.27)

„Akku voll“ bei abfallender Leistung, `null/1000` als „0,0 kW“, Roh-Codes (STALE, public),
„gesunken um -3 km“, leere Klammern, Plan-Speichern bei leerer Uhrzeit, überlappende
Refreshes, Zeitzone der Panel-Zeiten, Fahrtkosten bei 0/negativ, Fremdladung ohne Preis,
endloses DISABLE alle 120 s (dabei gefunden: Abschalt-Weigerung lief unter dem Fehlstart-Code
→ eigener Code `CHARGER_OFF_REFUSED`), Ø-Leistung über Maximum (live 24.10.: 10,6/10,4 kW),
Preiskurve auf 96 Slots, gemischte Tibber-Raster, überlappende 45-min-Intervalle,
Shelly-Drift-Check ohne JSON-Prüfung, `create_report` ohne Jahresgrenze, Test-Push ohne
Admin, rohe TypeErrors bei Plänen/Replay, verwaistes Center nach Plattform-Fehler, Replay über
die Zeitumstellung, Fahrstil wertet Lücken als Vollbremsung, mi/mph/°F/MWh, Klima-Monat.

## Bewusst nicht geändert

- **Preis-Einheiten-Heuristik ohne Einheit:** ohne Einheit nicht eindeutig lösbar; Tibber und
  Nordpool liefern Einheiten, und der Einstellungen-Reiter zeigt das Ergebnis der Prüfung.
- **Replay ohne Probebetrieb:** der Abgleich braucht das aufgezeichnete Halo-Schalten; ohne es
  endet ein Replay zu Recht in START_FAILED.
- **Monatsfilter der Session-Liste im Panel** in Browser-Zeit: betrifft nur abweichende
  Zeitzonen am Monatsrand.
- **Health-Push nach jeder Abfahrt:** in der Simulation vermutet, im Feld nicht beobachtet –
  bei der Feldkontrolle darauf achten.
- **`check_prices` ohne Admin:** nur lesender Abruf.

## Ohne Befund

Dry-Run schaltet nie real; CP nie ohne `cp_failsafe_verified`; Zeitumstellung 25.10. im
Planer korrekt; kein XSS; Geheimnisse geschwärzt; Upload/Download gegen Pfad-Tricks gesichert;
Übersetzungen aktuell; keine Konsolenfehler im Panel.
