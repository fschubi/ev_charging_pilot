# Prüfbericht 2026-10-24 (Stand v0.27.1)

Fünf parallele Prüfungen (Steuerlogik, Berechnungen, Anzeige, HA-Schicht, Szenario-Stresstest
über mehrere Tage) plus Live-Abgleich in Franks Instanz. Testlauf vorher: 302 Tests grün,
ruff und Panel-Syntax sauber – die Funde unten fallen den bisherigen Tests nicht auf.
„reproduziert“ = mit der Testwelt `tests/core/world.py` bzw. einem Skript nachgestellt.

> **Stand:** Kritisch und Hoch werden einzeln behoben (je ein Release ab v0.27.2), jeweils
> mit Regressionstest in `tests/core/test_review_2026_10_24.py` bzw. `tests/integration/`,
> der mit dem alten Code fehlschlägt. Mittel/Niedrig sind offen.

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

## Mittel (offen)

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

## Niedrig (offen)

„Akku voll“ bei abfallender Leistung, `null/1000` als „0,0 kW“, Roh-Codes (STALE, public),
„gesunken um -3 km“, Replay überspringt Zeitumstellungs-Stunde, Preiskurve auf 96 Slots,
überlappende 45-min-Intervalle, Preis-Einheiten-Heuristik ohne Einheit, endloses DISABLE alle
120 s, Shelly-Drift-Check ohne JSON-Fehlerbehandlung, `create_report` ohne Jahresgrenze.

## Ohne Befund

Dry-Run schaltet nie real; CP nie ohne `cp_failsafe_verified`; Zeitumstellung 25.10. im
Planer korrekt; kein XSS; Geheimnisse geschwärzt; Upload/Download gegen Pfad-Tricks gesichert;
Übersetzungen aktuell; keine Konsolenfehler im Panel.
