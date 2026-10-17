# Prüfliste nach der ersten echten Ladung mit v0.19.8

Angelegt am 2026-10-18 nach der Gesamtprüfung ([Prüfbericht](pruefbericht-2026-10-18.md)).
Alle Korrekturen sind bisher nur in Simulationen getestet – diese Liste prüft sie am
echten Auto. Wenn Frank sich meldet: Punkte der Reihe nach abarbeiten und Ergebnisse
unten eintragen.

## Ausgangslage

- Installiert: **v0.19.8**, HA neu gestartet am 18.10. kurz nach Mitternacht.
- Modus **Live**, Automatik an, OVMS „Lesen & Schreiben“, CP-Checkliste §3.6 erledigt.
- Geplant: **einmalige Abfahrt So 18.10., 16:00**, Ziel 90 %, Mindest 85 % (Stand Cockpit
  am 17.10.: SOC 70 %). Günstigster Block laut Plan **So 06:00–06:37** (Tibber, 1 Block).
- Wochenplan „Büro Mo-Mi“: Mo–Do, Abfahrt 05:30, Ziel 100 % (hohes Ziel → höchstens 2 h
  vor „fertig“ voll), Ladestrom 12 A falls im Plan gesetzt.
- Halo: Maximalstrom 12 A (≈ 8 kW), gesperrt = Status „Unavailable“.

## So kommt man an die Daten

- Ereignisse: WebSocket `ev_charging_pilot/get_events` (Panel → Diagnose → Event Log) –
  oder Diagnose-Datei herunterladen (Einstellungen → Geräte & Dienste → Integration →
  Diagnose).
- Zustand: WebSocket `ev_charging_pilot/state`; Sitzungen `get_sessions`.
- Verlauf der Entitäten (Halo-Leistung, OVMS-SOC, Stecker) über `history/history_during_period`.
- Frank hat HA meist in Chrome offen (`http://homeassistant.local:8123`); Zugriff wie in
  dieser Sitzung über die Browser-Werkzeuge und `document.querySelector('home-assistant').hass`.

## Was zu prüfen ist

### 1. Die Ladung am Sonntagmorgen (einmalige Abfahrt)
- [ ] Wallbox um ~06:00 freigegeben (`CHARGER_ENABLE`), Bestätigung in Sekunden.
- [ ] Falls ein Ladestrom gesetzt ist: `CURRENT_SET` und Halo-Wert übernommen.
- [ ] Hat der smart von selbst geladen, oder wurde geweckt (`OVMS_WAKEUP`, `CP_PULSE_START`)?
      Zeit vom Freigeben bis zur Leistung notieren → **Messung M8**.
- [ ] `CHARGE_STABLE` nach wie vielen Sekunden/Messwerten → **Messung M1**.
- [ ] Abschaltung bei **90 %** (`TARGET_SOC_REACHED` bzw. Wallbox aus) – nicht darüber
      (Fix K7). Falls der Block vorher endete: `BLOCK_EXTENDED` und Weiterladen bis Ziel.
- [ ] Genau **eine Sitzung** in „Hausstrom“, sauber geschlossen (Fix K8/K10), kWh und Kosten
      plausibel (≈ 4 kWh, Tibber-Preis ~0,39 €/kWh).

### 2. Nach der Ladung
- [ ] Systemzustand bleibt **gesund**, keine Push „Systemzustand: eingeschränkt“,
      SOC-Qualität „letzter Wert“ statt „veraltet“ (Fix K1).
- [ ] Keine Weck- oder Schaltbefehle mehr bis zur Abfahrt.
- [ ] Vorklimatisierung vor 16:00 (falls „auto“ und kalt genug): `CLIMATE_START`, aber
      **kein** OVMS-/CP-Weckversuch durch die Wallbox (Fix K4).

### 3. Neustart-Verhalten (wenn sich die Gelegenheit ergibt)
- [ ] HA-Neustart, nachdem das Auto fertig geladen hat: danach **kein** `OVMS_WAKEUP` /
      `CP_PULSE_START`, Zustand „Auto hat fertig geladen“ (Fix K2).
- [ ] Beim ersten Speichern der Einstellungen nach dem Boot kein ERROR im HA-Log
      (Fix H5).

### 4. Wochenplan ab Montag
- [ ] Montag 05:30: Ziel 100 % erst kurz vor der Abfahrt erreicht (frühestens ~02:50).
- [ ] Ist das Auto tagsüber im Büro, verfällt kein Preisblock (Fix v0.13.5) – abends
      eingesteckt wird neu geplant.
- [ ] Mehrere Nächte = mehrere getrennte Sitzungen.

### 5. Danach
- [ ] Werte M1, M2 (bekannt: Freigabe ~5 s), M3 (Status bei „voll“), M8 in
      [messungen.md](messungen.md) eintragen und Defaults in `core/settings.py` anpassen.
- [ ] Nach drei Ladungen: gelernte Ladeleistung (Cockpit/Prognose) gegen die echten ~7,9 kW
      bei 12 A prüfen.
- [ ] Monatsanfang 01.11.: Monatsbericht, Mail (falls eingerichtet) und Push an Melanie.

## Ergebnisse

_(hier eintragen)_
