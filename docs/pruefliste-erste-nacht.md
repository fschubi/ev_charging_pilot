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

### Erste Nacht, So 18.10.2026 – ausgewertet um 08:30 (Ereignisse, Zustand, Sitzungen, HA-Log, Verlauf)

**Ablauf (Ortszeit):**

| Zeit | Ereignis | Bemerkung |
| --- | --- | --- |
| 01:57:46 | `EXECUTOR_STARTED` | HA-Neustart, Zustand bereit |
| 06:00:03 | `CURRENT_SET` 14 A, `CHARGER_ENABLE` (one_shot) | Plan stand auf 14 A (nicht 12 A wie oben angenommen) |
| 06:00:13 | `CHARGER_CONFIRMED` | Freigabe nach **10 s** bestätigt, Halo-Status „Charging“ |
| 06:00:19 | OVMS „lädt“ = an | Auto lud **von selbst**, kein OVMS-/CP-Wakeup |
| 06:00:43 | `CHARGE_STABLE` | 30 s nach Bestätigung = nächster Halo-Poll |
| 06:23:39 | SOC 90 % → `SESSION_END` (target_soc_reached), `CHARGER_DISABLE` | genau beim Ziel, kein Überladen |
| 06:23:44 | `CHARGER_OFF_CONFIRMED` | Abschaltung nach 5 s bestätigt |

Danach keine weiteren Schalt- oder Weckbefehle. SOC stieg gleichmäßig ~1 %/75 s,
Leistung 8,8–9,2 kW (gegen Ende 7,6–7,9 kW).

**Abgehakt:**

- [x] Freigabe um 06:00, Bestätigung in Sekunden (10 s).
- [x] `CURRENT_SET` 14 A, Halo meldet 14 A.
- [x] Kein Wecken nötig: Leistung ~10 s nach Freigabe → **M8 ≈ 10 s** (Status), Auto-Meldung nach 16 s.
- [x] `CHARGE_STABLE` nach 30 s / erster Leistungswert → **M1: Halo pollt alle 30 s**.
- [x] Abschaltung genau bei 90 % (K7 bestätigt), kein `BLOCK_EXTENDED` nötig (Block 06:00–06:36, fertig 06:23).
- [x] Genau eine Sitzung `s-20261018-040043`, sauber geschlossen, `success`, 71 → 90 %,
      3,31 kWh, 1,27 € (0,384 €/kWh Tibber), max. 9,17 kW, Ø 8,66 kW.
- [x] Systemzustand HEALTHY, SOC-Qualität GOOD, keine Fehler von `ev_charging_pilot` im HA-Log.
- [x] Vorklimatisierung 15:53–16:00 (auto, 8,7 °C → 5 min) – Ergebnisse unten.
- [ ] Wochenplan ab Montag (Büro Mo–Mi, 100 %), Monatsbericht – noch offen.

**Vorklimatisierung 18.10. (v0.19.9):**
- `CLIMATE_START` und `CHARGER_ENABLE` gleichzeitig 15:53:04, Halo bestätigt nach 7 s, Auto
  wach 15:53:09 durch den OVMS-Befehl – kein `OVMS_WAKEUP`/CP-Puls.
- Klima (`hvac_active`) 15:53:20–15:58:06, Innenraum 17 → 26 °C, Lüfter konstant 96;
  Heizleistung taktet (Halo 7–8,8 kW, Akku 3,2–6,5 kW).
- Wallbox blieb bis 16:00:04 an (`allow_topup`), lud nach Klima-Ende auf 92 %.
- Sitzung `s-20261018-135409` Grund `climate`: 0,80 kWh, 0,34 €.
- Falsche Warnung `HV_CYCLE_WITHOUT_ACTIVITY` 15:53:53 (Executor noch WAITING_FOR_CHARGE).
- → behoben in **v0.20.1** (Halo-Bestätigung vor Klimabefehl, Ende mit `hvac_active`,
  HV-Wächter), Klima-Anteil getrennt ab **v0.21.0**.

**Weitere Befunde 18.10.:**
- SOC-Anzeige 90 → 88 % um 14:30 ohne Wecken: Korrektur nach Entspannung (389,5 → 383,5 V),
  `real_soc` lag bei 85,6 %. Beobachten, ob das Ladeziel dadurch regelmäßig 1–2 % zu tief
  landet.
- Cockpit/Statuszeile nannte „Lädt 06:00–15:54“ nach dem Block → **v0.20.2**.
- Fahrten 16:13–16:32 (15,3 km, 19,4 kWh/100 km) und 19:14–19:32 (14,4 km, 20,2 kWh/100 km)
  korrekt; eine Fahrt erscheint erst 10 min nach „Fahrzeug aus“ (`trip_merge_gap_min`).
- Shelly-WLAN −79 … −87 dBm (Vortag −69), 30 Aussetzer 16–19 Uhr, zweimal
  `HEALTH_ERROR` → Toleranz 3 min in **v0.21.1**; WLAN selbst bleibt zu verbessern.
- OVMS `battery_power`: + in den Akku (Laden/Rekuperation), − beim Fahren.

**Gefundene Fehler** (alle vier behoben in **v0.19.9**, mit Tests):

1. **HV-Zyklen-Wächter wirkungslos (wichtig, Regel 6).** Gemappt ist
   `sensor.vorgarten_pi_eq_16e_hv_contactor_cycles_remaining_smart_fortwo` – ein
   **Restzähler**, der fällt (194784 → 194783 um 06:00:54). `HvCycleMonitor` erwartet einen
   steigenden Zähler: `hv_cycles_today` zeigt **−1**, `HV_CYCLE_WITHOUT_ACTIVITY` und
   `HV_CYCLES_HIGH` können nie auslösen. Die Auto-Erkennung (`discovery.py`,
   Muster `contactor_cycles`) wählt diesen Sensor. Lösung: Betrag der Änderung zählen
   (oder „remaining“ erkennen und umdrehen) + Test.
2. **Cockpit-Text nach Ziel veraltet.** Um 08:29 (Auto 90 %, Wallbox aus) steht noch
   „Lädt in der günstigsten Zeit 06:00–06:36“. Nach Blockende ist `active_window` leer,
   damit ist `target_held` falsch, und `summary._upcoming` zeigt die verriegelten, schon
   vergangenen Blöcke. Erwartet: „Ziel 90 % erreicht – Das Auto ruht bis zur Abfahrt 16:00“.
   Lösung: vergangene Blöcke ausblenden; bei `needed_kwh == 0` „Ziel erreicht“ zeigen
   (`duration_min` ist dann `null`, deshalb greift „Kein Laden nötig“ nicht).
3. **Sitzungsenergie zu klein (~3,5 %).** Halo-Gesamtzähler 1,12 → 4,55 kWh = **3,43 kWh**,
   Sitzung nur **3,31 kWh**: Start erst bei `CHARGE_STABLE` (06:00:43, 1,17 kWh; seit 06:00:13
   lief schon Strom) und Ende bei `SESSION_END` (4,48 kWh), die letzten Cloud-Werte
   4,54/4,55 kamen 1–30 s später. Folge: Kosten und Wirkungsgrad zu niedrig, Fahrzeug-
   energie (3,38 kWh) liegt sogar über der Netzenergie. Lösung: Startstand vom letzten
   Wert vor `CHARGER_ENABLE` nehmen, Endstand bis zum ersten Zählerwert nach
   `CHARGER_OFF_CONFIRMED` (max. ~60 s) nachführen.
4. **Panel-Skriptfehler nach Versionswechsel.** HA-Log 08:12 (Chrome und iOS):
   `Identifier 'DOMAIN' has already been declared` / `duplicate variable 'AMPS'`. Das Panel
   wird als klassisches Skript (`js_url`) geladen; kommt nach Neustart eine neue `?v=`-URL in
   einen offenen Tab, kollidieren die globalen `const`. Das Panel läuft dann mit altem Code
   bis zum Neuladen. Lösung: `module_url` statt `js_url` (Datei hat keine Importe/Exporte).

**Hinweise (keine Fehler der Integration):**

- `tibber.realtime` „Watchdog: Connection is down“ 359× seit 01:58 und `tibber_local`
  „no sensors found“ – Tibber-Pulse/Echtzeitverbindung, nicht der Preisabruf; Preise kamen an.
- Wochenplan „Büro Mo-Mi“ hat für Montag noch keine Preisblöcke (Tibber-Preise für morgen
  kommen erst gegen 13 Uhr) – heute Nachmittag nachsehen.
- Ausgangslage oben: Halo steht auf 14 A (≈ 9,2 kW), nicht 12 A; gelernte Leistung braucht
  noch zwei Ladungen (`learned.sessions` = 1).

### Neustart mit Update auf v0.19.9 – So 18.10.2026, 08:48

Auto eingesteckt, 90 %, Wallbox aus. Ausgewertet um 08:50.

- [x] Nach dem Neustart nur `EXECUTOR_STARTED` (bereit), **kein** `OVMS_WAKEUP` /
      `CP_PULSE_START`, kein Schaltbefehl (Fix K2 bestätigt).
- [x] Systemzustand HEALTHY, SOC 90 % mit Qualität GOOD.
- [x] Cockpit: „Ziel 90 % erreicht – Das Auto ruht bis zur Abfahrt 16:00“ (v0.19.9, Fehler 2).
- [x] „HV-Zyklen heute“ = 1 (vorher −1), Tageswert über den Neustart erhalten (Fehler 1).
- [x] Panel als Modul geladen (`ev_charging_pilot_panel?v=0.19.9`), keine Skriptfehler im
      HA-Log (Fehler 4). Ein älterer, noch offener Tab braucht einmal Neuladen.
- [x] Erstes Speichern der Einstellungen nach dem Boot (08:53): Integration neu geladen
      (`EXECUTOR_STARTED`), **kein** ERROR von `ev_charging_pilot` im HA-Log (Fix H5),
      danach wieder kein Wecken, Zustand bereit, Cockpit „Ziel 90 % erreicht“.
