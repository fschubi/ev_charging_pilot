# Smart EQ 453 Charging Center – Masterplan v1.3

Oct 13, 2026 · @Frank

## Änderungen gegenüber v1.2

v1.3 ersetzt v1.0–v1.2 vollständig und konsolidiert sie in eine einzige, widerspruchsfreie Spezifikation. Die wichtigsten Änderungen:

| Bereich | Änderung in v1.3 |
| --- | --- |
| Grundsatz | Charging Center ersetzt evcc vollständig; nur ein System steuert die Halo |
| Grundsatz | Tibber und dynamische Tarife vorerst außen vor; Kostenmodell aber intervallbasiert vorbereitet |
| Architektur | Flache State Machine ersetzt durch Soll/Ist-Modell: Planner, Executor, Health getrennt |
| Architektur | Kernlogik als HA-freie Python-Bibliothek mit injizierter Uhr; Replay = Unit-Test |
| CP-Puls | Neuer Maskierungszustand: Kabel- und Statuswechsel der Halo während des Pulses werden ignoriert |
| CP-Puls | Puls gerätseitig per `toggle_after`; Pulsdauer nur an einer Stelle definiert |
| CP-Puls | Shelly `unavailable` = CP-Zustand unbekannt = ERROR statt Warnung |
| Halo | Cloud-Polling berücksichtigt: Stabilität über N Messwerte statt Sekunden; Zeitkonstanten erst nach Messung |
| Halo | OCPP nicht mehr pauschales Nicht-Ziel, sondern Prüfauftrag |
| Bedienung | RFID-Sofortladen als eigener Anwendungsfall |
| Bedienung | Push-Benachrichtigungen und Actionable Notification beim Einstecken |
| Ziel-SOC | Konflikt Ziel-SOC-Abschaltung vs. Vorklimatisierung aufgelöst |
| Datenqualität | Neue Stufe LAST\_KNOWN\_VALID für Werte eines schlafenden Fahrzeugs |
| Datenqualität | Regel: Fahrzeug wird nie nur zur Datenaktualisierung geweckt (HV-Kontaktorzyklen) |
| Fehler | ERROR mit definierten Ausgängen; Ladeabbruch während CHARGING modelliert |
| Statistik | Monatsbilanz mit SOC-Ausgleichsterm; Rechenfehler im alten Beispiel korrigiert |
| Statistik | `utility_meter` und Long-Term Statistics statt eigener Monatsaufteilung |
| Statistik | Fahrtgrenzen (Trip-Start/-Ende) definiert |
| Rahmen | §14a EnWG (Dimmung auf 4,2 kW) als Eingangsgröße der Prognose |
| Roadmap | Neue Phase 0: einfache Automation + Messphase vor der Integration; v0.1 verschlankt |

## 1. Projektziel und Grundsatzentscheidungen

Das Smart EQ 453 Charging Center ist eine eigene Home-Assistant-Custom-Integration, die Laden, Wakeup, Vorklimatisierung, Diagnose und Verbrauchsstatistik des Smart EQ 453 als einziges Steuerungssystem übernimmt. Es ersetzt evcc vollständig und bündelt die vorhandenen Geräteintegrationen, statt sie nachzubauen.

Die fertige Lösung beantwortet auf einen Blick: Ist der Smart angeschlossen und lädt er stabil? Wird er bis zur Abfahrt den Mindest-SOC erreichen? Musste er geweckt werden? Wie viele kWh hat das Auto diesen Monat zuhause geladen, und was hat das gekostet? Ist das System gesund?

### 1.1 Verbindliche Grundsatzentscheidungen

1. **Ein Controller:** Das Charging Center ist das einzige System, das die Halo schaltet. evcc wird nicht parallel betrieben (auch nicht lesend mit Ladesteuerung), der Halo-interne Zeitplan bleibt aus.
2. **Tibber vorerst außen vor:** Kosten mit Festpreis bzw. Preis pro Session. Das Kostenmodell rechnet trotzdem intervallbasiert, damit ein dynamischer Tarif später ohne Umbau andockt.
3. **Soll/Ist statt Befehlsketten:** Planner berechnen nur den gewünschten Zustand, ein Executor gleicht ihn mit Guards gegen den Ist-Zustand ab. Nach Neustarts wird das Soll neu berechnet, nie werden alte Befehle nachgeholt.
4. **CP-Normalzustand ist geschlossen.** Rückstellung doppelt: gerätseitiger Puls bzw. Auto-On im Shelly plus Software-Kontrolle.
5. **Wakeup-Reihenfolge:** OVMS vor CP. CP ist begrenzter Fallback, kein Startmechanismus.
6. **Fahrzeugschonung:** Das Auto wird nie geweckt, nur um Daten aufzufrischen. Jeder Wakeup kostet HV-Kontaktorzyklen.
7. **Laden gilt erst als gestartet, wenn es stabil bestätigt ist.**
8. **Ziel-SOC wird über die Halo umgesetzt, nie über den CP.**
9. **Datenqualität ist Teil jeder Steuerentscheidung.** Konflikte werden angezeigt, nie verschluckt.
10. **Halo-kWh sind maßgeblich für die Hausabrechnung.** Heim- und Fremdladen werden getrennt.
11. **Keine produktive Automatik vor Messphase, Dry-Run und Einzeltest.**
12. **Keine hart codierten Entity-Namen,** OVMS-Mapping erst nach realem Test.
13. **Fehler sind sichtbar und werden aktiv gemeldet** (Push), keine Endlosschleifen.
14. **Was HA schon kann, wird genutzt** (`utility_meter`, Long-Term Statistics, Energy Dashboard, Notifications), nicht nachgebaut.

### 1.2 Nicht-Ziele der ersten Produktivversion

- Tibber, dynamische Tarife, Preisoptimierung
- PV-Überschussladen (Anlage zu klein)
- GPS-Fahrtenbuch, steuerliche Abrechnung
- Automatische Fremdladeerkennung
- Ungetestete OVMS-Kommandos
- Eigene Charge-Amps-Cloud-API neben der HACS-Integration

OCPP ist kein pauschales Nicht-Ziel mehr, sondern ein Prüfauftrag (Abschnitt 16).

## 2. Systemumgebung und bekannte Entities

Drei Geräte liefern Daten und Aktoren, Home Assistant OS orchestriert. Die Entity-IDs unten sind die aktuell bekannten Defaults; im Config Flow werden sie per Entity-Selector gewählt, nie hart codiert.

| Gerät | Rolle | Anbindung | Bekannte Einschränkung |
| --- | --- | --- | --- |
| Charge Amps Halo (11 kW) | Ladefreigabe, Netzleistung, Energiezähler, Kabelstatus | HACS „Chargeamps“, Cloud-API mit API-Key | Polling-Latenz, Cloud- und Internetabhängigkeit |
| Shelly 1 Mini Gen3 | Kurze Unterbrechung der CP-Leitung (Wakeup) | HA-Shelly-Integration, lokal | Schließer-Kontakt: stromlos = CP offen |
| OVMS v3 | SOC, SOH, Fahrdaten, Klima, Software-Wakeup | noch offen (MQTT, Abschnitt 16) | Keine Ladefreigabe; Daten nur bei wachem Fahrzeug |

### 2.1 Charge Amps Halo

```yaml
charger_enable:   switch.halo_wallbox_connector_1
cable_connected:  binary_sensor.halo_wallbox_connector_1_cable_connected
charge_power:     sensor.halo_wallbox_connector_1_power
charger_status:   sensor.halo_wallbox_connector_1_status
max_current:      number.halo_wallbox_connector_1_max_current
total_energy:     sensor.halo_wallbox_total_energy
internal_schedule: switch.halo_wallbox_connector_1_schedule   # muss dauerhaft off sein
cable_lock:       lock.halo_wallbox_connector_1_cable_lock
phases:           sensor.halo_wallbox_connector_1_l{1,2,3}_{current,voltage}
```

Vor dem Bau zu messen (Phase 0): tatsächliches Update-Intervall von Leistung und Status, Latenz zwischen Schaltbefehl und Zustandsänderung, alle vorkommenden Werte von `status_raw`.

### 2.2 Shelly 1 Mini Gen3 (CP-Unterbrechung)

```yaml
cp_relay:           switch.mini_1_wallbox_wallbox_cp_unterbrechung
cp_temperature:     sensor.mini_1_wallbox_wallbox_cp_unterbrechung_temperatur
shelly_signal:      sensor.mini_1_wallbox_signalstarke
shelly_restart_req: binary_sensor.mini_1_wallbox_neustart_erforderlich
```

Logik: `ON` = Kontakt geschlossen = CP durchverbunden (Normalzustand), `OFF` = CP unterbrochen. Muss vor dem ersten Automatiktest elektrisch bestätigt werden (Checkliste in Abschnitt 3).

### 2.3 OVMS (Smart ED/EQ Gen.4, 453)

Laut OVMS-Dokumentation verfügbar: SOC, SOH, Reichweite, Temperaturen, Ladestatus, 12-V-Überwachung, BMS-Diagnose, Odometer- und Tripdaten, zeitbasierte Klimatisierung. Nicht verfügbar: direkte Ladefreigabe.

Relevante Metriken (Mapping auf HA-Entities erst nach Einbau):

| Zweck | OVMS-Metrik |
| --- | --- |
| Fahrtenergie, Rekuperation, Nebenverbrauch | `xsq.v.energy.used`, `xsq.v.energy.recd`, `xsq.v.aux.consumption` |
| Trip-Werte | `xsq.v.reset.{consumption,distance,energy,speed,time}`, `xsq.v.start.{distance,time}` |
| Kilometerstand | `xsq.odometer.{start,start.total,trip,trip.total}` |
| Laden Fahrzeugseite | `xsq.v.charge.bcb.power`, `xsq.obl.{volts,amps,power}`, `xsq.obd.charge.duration` |
| Batterie | `xsq.bms.{soh,cap,temps,voltages,soc.values,batt.power,energy.nominal}` |
| HV-Kontaktor | `xsq.bms.contactor.cycles`, Befehl `xsq hvcycles` |

Klima: `climatecontrol on` bzw. `homelink 1` = 5 min, `homelink 2` = 10 min, `homelink 3` = 15 min. Keine Solltemperatur, dokumentierte Voraussetzung SOC > 30 %.

## 3. Hardware: CP-Unterbrechung und Failsafe

Der CP-Puls wird vom Shelly selbst getimt und zusätzlich durch Auto-On und Power-on-Default abgesichert; HA prüft danach nur noch. So bleibt der Kontakt auch dann nicht offen, wenn HA, WLAN oder die Integration mitten im Puls ausfallen.

### 3.1 Drei Rückfallebenen

1. **Gerätseitiger Puls:** HA löst den Puls mit einem einzigen RPC-Aufruf aus, der Shelly schaltet selbst zurück:

   ```json
   {"method": "Switch.Set", "params": {"id": 0, "on": false, "toggle_after": 10}}
   ```

   Falls die HA-Shelly-Integration das nicht direkt anbietet: Aufruf über `rest_command` an die lokale Shelly-RPC-API.
2. **Auto-On:** Shelly-Konfiguration `auto_on = true`, `auto_on_delay = 10`. Greift bei jedem `OFF`, auch manuell.
3. **Power-on-Default:** `initial_state = on`. Greift nach Spannungswiederkehr.

Die Pulsdauer wird **nur an einer Stelle** festgelegt: Der Config-Wert `cp_pulse_s` (Default 10, erlaubt 5–15) wird beim Puls als `toggle_after` gesendet. Ein Health-Check vergleicht ihn mit dem im Shelly konfigurierten `auto_on_delay`; Abweichung = DEGRADED.

### 3.2 Softwareprüfung nach dem Puls

Nach `cp_pulse_s + 5 s` muss `cp_relay == on` gemeldet sein. Sonst: `ERROR_CP_NOT_RESTORED`, Push-Benachrichtigung, keine weitere Lade- oder Wakeup-Aktion, bis der Normalzustand bestätigt ist.

### 3.3 Fehlerfälle des Shelly

| Situation | Folge | Behandlung |
| --- | --- | --- |
| Shelly `unavailable` | CP-Zustand unbekannt | ERROR (nicht nur Warnung), CP-Fallback gesperrt, Push |
| Shelly stromlos/defekt | Schließer offen → Auto lädt nie | Ladeversuch scheitert → `CHARGE_START_FAILED` mit Hinweis „Shelly prüfen“ |
| `auto_on` nach Firmware-Update weg | Puls hängt nur noch an HA | Config-Drift-Check → DEGRADED |

### 3.4 Was die Halo während des Pulses sieht

Bei offener CP-Leitung sehen Fahrzeug **und** Wallbox Zustand A („nicht verbunden“). Die Halo meldet daher voraussichtlich kurz `cable_connected = false`, beendet evtl. ihre Session und verlangt danach evtl. neue Autorisierung.

Konsequenz für die Software: Während eines Pulses gilt eine **Maskierung**. Kabel- und Statuswechsel werden für `cp_pulse_s + cp_mask_grace_s` (Default 30 s, nach Messung anpassen) ignoriert und lösen weder `DISCONNECTED` noch ein Session-Ende aus. Echte Kabelabzüge danach werden normal erkannt.

In Phase 0 zu messen: Was meldet die Halo während und nach dem Puls? Lädt sie ohne neue Autorisierung weiter? Bewegt sich der Kabellock?

### 3.5 Elektrische Hinweise

Die CP-Leitung ist ein SELV-Signal, der Shelly hängt an 230 V. Verdrahtung und Trennung (potentialfreier Kontakt, Isolationsabstände, Einbauort) einmal von einer Elektrofachkraft abnehmen lassen. Der Eingriff in die Pilot-Ader kann Gewährleistung und Konformität der Halo berühren.

### 3.6 Checkliste vor dem ersten produktiven CP-Test

- [ ] `ON` entspricht elektrisch CP geschlossen
- [ ] `OFF` entspricht elektrisch CP unterbrochen
- [ ] `initial_state = on`
- [ ] `auto_on = true`, `auto_on_delay = 10`
- [ ] Puls per `toggle_after` getestet
- [ ] Auto-On ohne HA real getestet (HA während Puls stoppen)
- [ ] CP nach Shelly-Neustart geschlossen
- [ ] CP nach HA-Neustart geschlossen
- [ ] Halo-Verhalten während des Pulses dokumentiert (3.4)
- [ ] Elektrofachkraft hat Verdrahtung abgenommen

Erst danach wird `cp_failsafe_verified = true` gesetzt; ohne diesen Wert bleibt der CP-Wakeup gesperrt.

## 4. Architektur: Soll/Ist-Modell

Planner berechnen, was sein soll; ein Executor setzt das unter Guards gegen den Ist-Zustand um; Health läuft getrennt daneben. Damit gibt es keine flache Zustandsliste mehr, in der Laden, Klima, Override und Fehler gegeneinander konkurrieren.

### 4.1 Schichten

| Schicht | Aufgabe | Schreibt Hardware? |
| --- | --- | --- |
| Adapter (Halo, Shelly, OVMS, Temperatur) | Rohwerte lesen, Befehle ausführen, alles mit Zeitstempel und Quelle | ja, nur auf Anweisung des Executors |
| Datenqualität | Alter, Qualitätsstufe, Konflikte je Wert (Abschnitt 7) | nein |
| Planner | Leiten aus Zeitplan, One-Shot, Override, RFID, Ziel-SOC, Klima ein **Soll** ab | nein |
| Arbiter | Wählt bei mehreren Wünschen den gültigen nach fester Priorität | nein |
| Executor | Gleicht Soll mit Ist ab, betreibt Wakeup-Kaskade, beachtet Cooldown und Limits | ja |
| Health | HEALTHY / DEGRADED / ERROR, sperrt Executor-Aktionen | nein |
| Monitor | Sessions, Trips, Statistik, Kosten, Event Log | nein |

### 4.2 Das Soll-Objekt

```yaml
desired:
  charger_enabled: true          # true / false / null (= nicht eingreifen)
  reason: schedule_weekday       # one_shot, override, rfid, target_soc_reached, climate, ...
  source_id: plan-werktage
  valid_until: 2026-10-14T05:30+02:00
  climate: null                  # {duration_min: 10, start_at: ...}
```

Arbiter-Priorität (höchste zuerst): Sicherheitssperre (Health ERROR) → Manual Override / RFID → One-Shot → Ziel-SOC erreicht → Klima → Wochenplan → Default „Halo aus“.

### 4.3 HA-freier Kern

Planner, Arbiter, Executor-Logik, Datenqualität und Statistikberechnung leben in einem Paket ohne `homeassistant`-Imports. Zeit kommt über eine injizierte Uhr, Aktionen gehen über ein Interface (`ChargerPort`, `CpPort`, `VehiclePort`).

Vorteile: Unit-Tests mit `pytest` in Millisekunden, Replay ist nur ein weiterer Port, Sommer-/Winterzeitwechsel testbar, Dry-Run = Port, der Befehle nur protokolliert.

### 4.4 Paketstruktur

```text
custom_components/smart_eq_charging/
├── __init__.py, manifest.json, const.py
├── config_flow.py            # Config + Options Flow
├── coordinator.py            # verbindet HA-Events mit dem Kern
├── ha_ports.py               # HA-Implementierung der Ports (Halo, Shelly, OVMS)
├── entities/                 # sensor, binary_sensor, button, switch, number, select
├── services.py, websocket_api.py, diagnostics.py, storage.py, export.py
├── translations/
└── core/                     # HA-frei
    ├── model.py              # Value mit Qualität, Soll-Objekt, Events
    ├── quality.py, source_policy.py
    ├── planner.py, arbiter.py
    ├── executor.py, wakeup.py
    ├── health.py
    ├── sessions.py, trips.py, statistics.py, costs.py
    └── replay.py
tests/                        # pytest, inkl. Replay-Datensätze
```

Frontend separat (eigenes Repo bzw. `www/`), ohne Steuerlogik; Daten über WebSocket-API (Abschnitt 12).

## 5. Planner

Sechs Planner erzeugen Ladewünsche; der Arbiter (4.2) wählt den gültigen. Abfahrtsbasiertes Laden ist das Hauptziel (Akku ca. 30 min vor Abfahrt voll), fester Startzeitpunkt ist der Rückfall, solange kein SOC verfügbar ist.

### 5.1 Wochenplan

```yaml
schedule:
  id: plan-werktage
  enabled: true
  weekdays: [mon, tue, wed, thu, fri]
  mode: departure_based          # oder fixed_start
  charge_start_time: "03:00"     # nur fixed_start und Rückfall ohne SOC
  departure_time: "05:30"
  ready_buffer_min: 30
  minimum_departure_soc_pct: 80
  preferred_departure_soc_pct: 90
  climate: auto                  # off / auto (Profil) / fixe Dauer
```

`departure_based` berechnet den Start rückwärts von `departure_time − ready_buffer_min` (5.6). Ohne gültigen SOC fällt der Plan auf `charge_start_time` zurück und zeigt das an.

### 5.2 One-Shot „Heute Nacht laden“

Wie ein Wochenplan, gilt aber nur für die nächste Nacht und löscht sich danach selbst. Wird bevorzugt über die Benachrichtigung beim Einstecken gesetzt (Abschnitt 8.4).

### 5.3 Manual Override

```yaml
manual_override:
  mode: until_unplugged          # until_unplugged / duration / until_time / until_soc / stop
  expires_at: null
  target_soc: null
  started_at: ...
```

„Jetzt laden“ und „Laden stoppen“ haben Vorrang vor allen Plänen, umgehen aber nie Health-Sperren oder den Schalt-Cooldown. Ein aktiver Override wird im UI und als `binary_sensor` immer sichtbar angezeigt.

### 5.4 RFID-Sofortladen

Ziel: tagsüber per Karte sofort laden, ohne App. Problem: Ist die Halo per Switch deaktiviert, funktioniert die Karte vermutlich nicht.

In Phase 0 zu klären, dann eine der Varianten festlegen:

| Variante | Ablauf | Voraussetzung |
| --- | --- | --- |
| A: RFID-Erkennung | Halo meldet Autorisierung/Session-Start per Status → Planner setzt Override `until_unplugged` | Halo nimmt RFID auch bei deaktiviertem Connector an und meldet es |
| B: Halo bleibt freigegeben, Fahrzeug wartet | Halo standardmäßig an; Nachtplan wird über Wakeup gestartet | Smart beginnt beim Einstecken nicht selbst zu laden (unwahrscheinlich) |
| C: Ersatz durch HA | NFC-Tag/Button in der Companion-App oder Push-Aktion „Jetzt laden“ | keine; funktioniert immer |

Arbeitsannahme bis zur Messung: Variante C, Variante A als Ausbau.

### 5.5 Ziel-SOC

Sobald OVMS-SOC verfügbar ist: `SOC ≥ Ziel` → Soll `charger_enabled = false`, Grund `target_soc_reached`. Der CP wird dabei nie geschaltet. Voraussetzung: SOC-Qualität `GOOD` (Fahrzeug lädt, also wach). Ein alter SOC löst nie eine Abschaltung aus.

Ziel ist bis zur Abfahrt der Wunsch-SOC, wenn erreichbar, sonst der Mindest-SOC.

### 5.6 Machbarkeit und empfohlener Start

```text
benötigte_kWh   = (Ziel_SOC − SOC) × nutzbare_Kapazität / Ladewirkungsgrad
ladedauer       = benötigte_kWh / erwartete_Ladeleistung
empfohlener_start = abfahrt − ready_buffer − ladedauer − sicherheitsreserve
```

- `erwartete_Ladeleistung` = Minimum aus Halo-Limit, Fahrzeuglader und ggf. §14a-Dimmung (4,2 kW); später aus gemessenen Sessions gelernt.
- Kapazität und Wirkungsgrad sind Konfigurationswerte, später aus Sessions kalibriert.
- Ergebnis wird als **Schätzung** angezeigt: Mindest-SOC erreichbar ja/nein, Wunsch-SOC erreichbar ja/nein, erwarteter SOC bei Abfahrt.
- Wird der Mindest-SOC voraussichtlich verfehlt → Push am Abend.

## 6. Executor und Wakeup-Kaskade

Der Executor kennt nur ein Ziel: das Soll herstellen. Will das Soll Laden, aber es fließt keine stabile Leistung, eskaliert er genau einmal über OVMS und einmal über CP und meldet sonst einen Fehler.

### 6.1 Zustände

| Zustand | Bedeutung | Verlassen durch |
| --- | --- | --- |
| `DISCONNECTED` | Kabel nicht gesteckt (außer während CP-Maskierung) | Kabel gesteckt |
| `IDLE` | Gesteckt, Soll = Halo aus, Ist = aus | Soll = an |
| `ENABLING` | Freigabe an Halo gesendet, warte auf Bestätigung | Halo meldet an / Timeout → Fehler |
| `WAITING_FOR_CHARGE` | Halo an, warte auf Leistung | Leistung über Schwelle / Wartezeit abgelaufen |
| `CHARGE_STABILIZING` | Leistung erkannt, noch nicht stabil | stabil → `CHARGING`, eingebrochen → zurück |
| `WAKEUP_OVMS` | Software-Wakeup gesendet, Wartezeit läuft | Ladung stabil / Wartezeit ab → `WAKEUP_CP` |
| `WAKEUP_CP` | Puls läuft, Halo-Wechsel maskiert, danach Wartezeit | Ladung stabil / CP nicht zurück → ERROR / ab → `START_FAILED` |
| `CHARGING` | Stabile Ladung, Session läuft | Soll = aus, Ladeende, Ladeverlust |
| `CHARGE_ENDED` | Fahrzeug hat beendet (voll oder Fahrzeuglimit) | Kabel ab / neues Soll |
| `INTERRUPTED` | Leistung länger als `charging_loss_timeout_s` weg, ohne Ladeende | ein erneuter Startversuch (Kaskade) oder `START_FAILED` |
| `DISABLING` | Abschaltung gesendet | Halo meldet aus → `COOLDOWN` |
| `COOLDOWN` | Mindestpause zwischen Halo-Schaltungen | Zeit abgelaufen |
| `START_FAILED` | Kaskade erfolglos | Kabel ab, nächstes Ladefenster, Reset |

Zusätzlich die Schalter **Dry-Run** und **Replay**: Der Executor läuft vollständig, die Ports protokollieren aber nur (`WOULD ENABLE CHARGER`).

### 6.2 Stabile Ladeerkennung

Wegen Cloud-Polling wird Stabilität über Messwerte definiert, nicht über Sekunden:

```text
stabil = mindestens N aufeinanderfolgende Halo-Leistungswerte > Schwelle
         UND seit dem ersten davon ≥ charging_stable_min_s vergangen
ODER     OVMS charging == true (GOOD) UND mindestens 1 Halo-Wert > Schwelle
```

Vorläufig: Schwelle 300 W, N = 2, `charging_stable_min_s` = 20. Endgültig nach Phase 0, wenn die Poll-Rate bekannt ist.

### 6.3 Ladeende vs. Abbruch

Fällt die Leistung während `CHARGING` unter die Schwelle, entscheidet in dieser Reihenfolge:

1. OVMS meldet Ladeende oder SOC ≥ Fahrzeuglimit → `CHARGE_ENDED`.
2. Halo-`status_raw` meldet „fertig/geladen“ (Werte in Phase 0 dokumentieren) → `CHARGE_ENDED`.
3. Sonst nach `charging_loss_timeout_s` → `INTERRUPTED`, ein Neustartversuch über die Kaskade, danach `START_FAILED`.

### 6.4 Limits und Pausen

```yaml
wakeup:
  start_detection_wait_s: 60     # vorläufig, nach Messung
  ovms_wait_s: 45
  post_cp_wait_s: 60
  max_ovms_attempts_per_window: 1
  max_cp_attempts_per_window: 1
  min_gap_between_wakeups_s: 120
charger:
  min_switch_interval_s: 120
```

Die Wartezeiten sind bewusst länger als in v1.2: Ein unnötiger Wakeup kostet Kontaktorzyklen, eine Minute Wartezeit nicht. Der CP-Wakeup setzt `cp_failsafe_verified = true` und Health ≠ ERROR voraus.

### 6.5 Neustart

Nach einem HA-Neustart: alle Ist-Werte lesen, Soll neu berechnen, CP-Normalzustand prüfen, laufende Session aus dem Store und dem Halo-Zähler rekonstruieren. Ein Wakeup, der vor dem Neustart lief, wird nicht fortgesetzt, sondern frisch bewertet (Versuchszähler bleiben gespeichert).

## 7. Datenqualität, Quellenpolicy, System-Health

Jeder steuerungsrelevante Wert trägt Quelle, Zeitstempel und Qualitätsstufe; Steuerentscheidungen verlangen eine Mindestqualität. Neu ist die Stufe `LAST_KNOWN_VALID`, damit ein schlafendes Auto nicht ständig als „veraltet“ gilt und geweckt wird.

### 7.1 Wertmodell

```yaml
value:
  raw: "72"
  normalized: 72.0
  unit: "%"
  source: ovms
  updated_at: 2026-10-13T18:02:11+02:00
  age_s: 1040
  quality: LAST_KNOWN_VALID
```

### 7.2 Qualitätsstufen

| Stufe | Bedeutung | Für Steuerung nutzbar? |
| --- | --- | --- |
| `GOOD` | Aktuell, plausibel | ja |
| `LAST_KNOWN_VALID` | Alt, aber seit dem Einschlafen weder gefahren noch geladen | für Planung ja, für Abschaltung nein |
| `STALE` | Alt und nach Aktivität nicht erneuert | nein, nur Anzeige |
| `ESTIMATED` | Berechnet statt gemessen | nur Planung, gekennzeichnet |
| `CONFLICT` | Quellen widersprechen sich | nein, Warnung im UI |
| `INVALID` | Unplausibel (z. B. SOC > 100) | nein |
| `UNAVAILABLE` | Kein Wert | nein |

`LAST_KNOWN_VALID` wird zu `STALE`, sobald Halo-Energie fließt, das Kabel gezogen wird oder OVMS Aktivität meldet, ohne dass der Wert erneuert wurde.

### 7.3 Altersgrenzen (vorläufig)

```yaml
max_age_s:
  halo_power: 3 × gemessenes Poll-Intervall
  halo_energy: 600
  vehicle_charging_state: 300
  soc_while_charging: 600
  odometer: 3600
  temperatures: 900
```

Regel: **Kein Wakeup nur zur Datenauffrischung.** Fehlt für eine Entscheidung ein GOOD-Wert, wird die Entscheidung konservativ getroffen (z. B. weiterladen statt abschalten), nicht das Auto geweckt.

### 7.4 Quellenpolicy

| Information | Primärquelle | Sekundär / Rückfall |
| --- | --- | --- |
| Netz-Ladeleistung | Halo | OVMS (Plausibilisierung) |
| Zuhause geladene kWh | Halo-Gesamtzähler | keine |
| Kabel gesteckt | Halo (mit CP-Maskierung) | OVMS |
| SOC, SOH | OVMS | keine Schätzung als Ersatz |
| Fahrzeug lädt | OVMS | Halo-Leistung |
| Kilometerstand | OVMS | manuelle Eingabe |
| Fahrzeugverbrauch | OVMS | berechnet, gekennzeichnet |
| Außentemperatur | Fahrzeug (wenn GOOD) | HA-Sensor, dann Wetter |

Widerspruch (z. B. Halo 2,2 kW, OVMS „lädt nicht“) → beide Werte `CONFLICT`, `binary_sensor.smart_eq_data_conflict` an, keine Quelle wird still überschrieben.

### 7.5 System-Health

| Status | Auslöser (Beispiele) | Wirkung |
| --- | --- | --- |
| `HEALTHY` | alles erreichbar, CP geschlossen, Failsafe verifiziert | volle Automatik |
| `DEGRADED` | OVMS offline, SOC STALE, Temperatur fehlt, Halo-Zeitplan an, Shelly-`auto_on` abweichend | zeitbasiertes Laden ja, SOC-Funktionen und Klima gesperrt |
| `ERROR` | CP nicht geschlossen oder unbekannt, Halo im Ladefenster nicht erreichbar, wiederholter Fehlstart | keine automatischen Schaltaktionen außer „CP schließen“, Push |

Zur Health gehört ein **Config-Drift-Check** alle 15 min: Halo-interner Zeitplan aus, Shelly `auto_on`/`initial_state` wie erwartet, Pulsdauer konsistent.

## 8. Fehlerbehandlung, Ausfälle, Benachrichtigungen

Jeder Fehler hat einen definierten Ausgang, und jeder Fehler, der ein leeres Auto am Morgen bedeuten kann, wird sofort per Push gemeldet. Ohne Benachrichtigung merkt man einen Fehlstart um 03:00 erst beim Einsteigen.

### 8.1 Fehlercodes und Ausgänge

| Code | Auslöser | Automatischer Ausgang | Manuell |
| --- | --- | --- | --- |
| `CHARGE_START_FAILED` | Kaskade erfolglos | Kabel ab, nächstes Ladefenster | Reset-Button |
| `CHARGE_INTERRUPTED` | Ladeverlust, Neustart erfolglos | Kabel ab, nächstes Ladefenster | Reset |
| `CP_NOT_RESTORED` | Relais nach Puls nicht `on` | keiner, bis `on` bestätigt | Reset nach Prüfung |
| `CP_STATE_UNKNOWN` | Shelly `unavailable` | Shelly wieder erreichbar und `on` | – |
| `CHARGER_UNAVAILABLE` | Halo im Ladefenster nicht erreichbar | Halo wieder erreichbar → Soll neu bewerten | – |
| `CHARGER_NOT_CONFIRMED` | Halo bestätigt Schaltbefehl nicht | nächster Abgleichzyklus (max. 3 Versuche) | Reset |
| `SWITCH_CYCLE_VIOLATION` | Schaltbefehl im Cooldown angefordert | verworfen, nur Event | – |

### 8.2 Kommunikationsausfälle

| Ausfall | Weiter möglich | Gesperrt |
| --- | --- | --- |
| Halo/Cloud | nichts Automatisches | alle Lade- und Wakeup-Aktionen |
| Shelly | zeitbasiertes Laden über Halo | CP-Wakeup; Health ERROR, weil CP-Zustand unbekannt |
| OVMS | zeitbasiertes Laden, CP-Wakeup | SOC-Funktionen, Klima, Software-Wakeup, Trips |
| Internet | nichts über die Halo (Cloud) | wie Halo-Ausfall |

Keine erfundenen Ersatzwerte; fehlende Werte werden als `UNAVAILABLE` angezeigt.

### 8.3 Push-Benachrichtigungen

Über `notify.mobile_app_*` (Ziel im Config Flow wählbar), Kategorien einzeln abschaltbar:

| Ereignis | Wann | Priorität |
| --- | --- | --- |
| Ladestart fehlgeschlagen | sofort | hoch |
| CP nicht zurückgestellt / unbekannt | sofort | kritisch |
| Mindest-SOC bis Abfahrt nicht erreichbar | abends nach Planberechnung | normal |
| Abends nicht eingesteckt | konfigurierbare Uhrzeit, nur wenn Plan für die Nacht aktiv | normal |
| Ladung abgebrochen | sofort | hoch |
| Health wechselt auf DEGRADED/ERROR | sofort, entprellt 5 min | normal/hoch |
| HV-Kontaktorzähler auffällig | sofort | normal |

### 8.4 Actionable Notification beim Einstecken

Beim Einstecken (außer im Ladefenster) fragt eine Benachrichtigung: **Normaler Plan** · **Heute Nacht laden** · **Jetzt laden**. Die Antwort setzt One-Shot bzw. Override. Ohne Antwort gilt der normale Plan. Das ist zugleich der einfachste Ersatz für RFID-Sofortladen (5.4, Variante C).

### 8.5 Event Log

```yaml
event:
  timestamp: 2026-10-14T03:01:12+02:00
  category: wakeup              # charging, wakeup, cp, climate, health, config, user
  severity: info                # debug, info, warning, error, critical
  code: CP_PULSE_DONE
  message: "CP geschlossen nach 10 s"
  session_id: s-2026-10-14-01
  data: {}
```

Gespeichert im eigenen Store mit Rotation (Standard 90 Tage), Abruf über WebSocket. Wichtige Events zusätzlich ins HA-Logbuch.

## 9. Vorklimatisierung

Die Klimatisierung wird über OVMS zeitbasiert gestartet (5/10/15 min); ist das Auto gesteckt, wird die Halo vorher freigegeben, damit Netzstrom bereitsteht. Der Konflikt mit der Ziel-SOC-Abschaltung ist über eine feste Regel gelöst.

### 9.1 Konflikt Ziel-SOC und Klima

Wird die Halo nach erreichtem Ziel-SOC für die Klimatisierung wieder freigegeben, lädt der Smart voraussichtlich einfach weiter (in Phase 5 bestätigen). Festlegung (konfigurierbar über `climate_after_target_soc`):

| Option | Verhalten | Default |
| --- | --- | --- |
| `allow_topup` | Halo für die Klimadauer freigeben; Nachladen um wenige Prozent wird akzeptiert, Halo danach aus | ja |
| `battery_only` | Halo bleibt aus, Klima aus dem Akku | – |
| `enforce_target` | Halo frei, Ziel-SOC-Logik bleibt aktiv und schaltet bei Überschreitung ab | erst nach Test, Risiko Schaltzyklen |

Default `allow_topup`, weil die Abfahrt kurz bevorsteht und ein paar Prozent über Ziel unkritisch sind.

### 9.2 Ablauf

1. Abfahrtszeit minus Klimadauer minus 2 min erreicht.
2. Profil aus Außentemperatur wählen (9.3).
3. Prüfen: OVMS erreichbar, SOC ≥ `climate_min_soc_pct` (Default 35 %) in Qualität `GOOD` oder `LAST_KNOWN_VALID`, Health nicht ERROR.
4. Gesteckt → Soll `charger_enabled = true`, Grund `climate`; Cooldown beachten.
5. OVMS-Klimabefehl senden (`homelink 1/2/3`).
6. Status und Netzleistung während der Klimaphase protokollieren.
7. Nach Ende: Soll zurück auf den Planwert.

Das UI zeigt „Wallbox für Vorklimatisierung freigegeben“ und – wenn messbar – die Netzleistung während der Klimaphase, behauptet aber nicht, dass die komplette Heizleistung aus dem Netz kommt.

### 9.3 Klimaprofile

| Profil | Außentemperatur | Dauer |
| --- | --- | --- |
| sehr kalt | < 0 °C | 15 min |
| kalt | 0 bis < 8 °C | 10 min |
| kühl | 8 bis < 15 °C | 5 min |
| neutral | 15 bis 24 °C | aus |
| warm | > 24 °C | 10 min |

Alle Schwellen konfigurierbar. Profile werden erst produktiv, wenn die drei OVMS-Befehle am Fahrzeug getestet sind.

## 10. Drive & Energy Monitor

Die Hausabrechnung (zuhause geladene kWh pro Monat) kommt aus HA-Bordmitteln und funktioniert ab Tag 1, auch ohne OVMS. Die Integration ergänzt nur, was HA nicht kann: Fremdladen, Verknüpfung mit Kilometern, Fahrzeugverbrauch, Ladeverluste mit SOC-Ausgleich und Qualitätskennzeichnung.

### 10.1 Hausabrechnung mit HA-Bordmitteln

```yaml
utility_meter:
  smart_eq_home_energy_month:
    source: sensor.halo_wallbox_total_energy
    cycle: monthly
  smart_eq_home_energy_year:
    source: sensor.halo_wallbox_total_energy
    cycle: yearly
```

Die Aufteilung über Mitternacht und Monatswechsel übernehmen die stündlichen Long-Term Statistics automatisch; eine eigene Monatsaufteilung (v1.2 §24) entfällt. Zusätzlich wird der Halo-Zähler im Energy Dashboard als Einzelverbraucher eingetragen.

Hinweis: Der interne Halo-Zähler reicht für die private Aufteilung im Haushalt. Für eine Erstattung durch Arbeitgeber oder eine steuerliche Abrechnung wäre ein MID-geeichter Zähler nötig.

### 10.2 Betriebsmodi

| Modus | Kilometer | Energie | Verfügbar ab |
| --- | --- | --- | --- |
| Manuell | Eingabe | Halo automatisch | v0.5 ohne OVMS |
| Vollautomatisch | OVMS-Odometer | Halo + OVMS | v0.5 mit OVMS |

Fremdladungen werden immer manuell erfasst (10.5).

### 10.3 Fahrten

Fahrtgrenzen: Eine Fahrt beginnt, wenn OVMS „Fahrbereit“ meldet (Metrik in Phase 5 festlegen, z. B. `v.e.on`), und endet, wenn das Fahrzeug länger als `trip_merge_gap_min` (Default 10 min) aus ist. Kürzere Stopps werden zusammengefasst.

```yaml
trip:
  trip_id, started_at, ended_at
  odometer_start_km, odometer_end_km, distance_km
  duration_min, average_speed_kmh
  vehicle_energy_used_kwh, recovered_energy_kwh, auxiliary_energy_kwh
  consumption_kwh_100km
  outside_temp_avg_c, season
  soc_start_pct, soc_end_pct
  quality: GOOD | PARTIAL | ESTIMATED
```

Voraussetzung: OVMS-Daten erreichen HA auch unterwegs (Abschnitt 16). Sonst werden Fahrten nur aus Odometer-Differenzen zuhause rekonstruiert (`quality: PARTIAL`).

### 10.4 Lade-Sessions

```yaml
charge_session:
  session_id, source: home_halo
  started_at, ended_at
  start_total_energy_kwh, end_total_energy_kwh, grid_energy_kwh
  start_soc_pct, end_soc_pct, vehicle_charge_energy_kwh
  max_power_w, average_power_w
  ovms_wakeup_used, cp_wakeup_used
  reason: schedule | one_shot | override | rfid | climate
  cost_eur, success, failure_code
  energy_intervals: [{start, end, kwh}]   # für Kosten pro Preisintervall
```

Ein CP-Puls beendet keine Session (Maskierung, 3.4).

### 10.5 Fremdladen

```yaml
external_charge:
  id, date, source: public | workplace | other_home
  energy_kwh, cost_eur, price_eur_kwh
  odometer_km, soc_before, soc_after, provider, note
```

Nur `home_halo` fließt in die Hausabrechnung. Für Verbrauchswerte zählen Heim- und Fremdladung zusammen als „dokumentierte Ladeenergie“.

### 10.6 Monatsbilanz mit SOC-Ausgleich

Fahrverbrauch und Ladeenergie eines Monats sind nur gleich, wenn der Akku am Monatsanfang und -ende gleich voll ist. Deshalb geht die Bestandsänderung in die Bilanz ein:

```latex
E_{\text{Akku,netto}} = E_{\text{Fahrzeug,geladen}} - \Delta SOC \cdot C_{\text{nutzbar}}
```

```latex
\text{Ladeverlust} = E_{\text{Netz,dokumentiert}} - E_{\text{Fahrzeug,geladen}}
```

```latex
\text{Netzverbrauch}_{100\,\text{km}} = \frac{E_{\text{Netz,dokumentiert}} - \Delta SOC \cdot C_{\text{nutzbar}} / \eta}{s} \cdot 100
```

Ladeverluste werden nur aus Sessions mit gemessener Fahrzeugladeenergie berechnet, nie aus Fahrverbrauch. Fehlt ΔSOC, wird der Wert als `ESTIMATED` markiert.

Monatsdatensatz: Strecke, Heim-kWh, Fremd-kWh, Fahrzeugverbrauch, Rekuperation, Nebenverbrauch, Ladeverluste (kWh, %), Kosten, €/100 km, Anzahl Sessions und Fahrten, Ø-Temperatur, Vollständigkeit (alle Tage mit Daten ja/nein).

### 10.7 Temperatur- und Saisonstatistik

Gruppen: < 0, 0–5, 5–10, 10–15, 15–20, ≥ 20 °C sowie Winter/Frühling/Sommer/Herbst. Pro Gruppe: Kilometer, Fahrzeug- und Netzverbrauch, Nebenverbrauch, Rekuperation, Kosten. Rekuperationsanteil nur mit klar definierter Bezugsgröße (rekuperiert / verbraucht brutto).

### 10.8 Datenhaltung

Eigener Store (`helpers.storage`, JSON) für Sessions, Trips, Fremdladungen, Monats-/Jahresaggregate und Events; bei erwarteten \~1.000 Einträgen pro Jahr unkritisch. Rohdaten-Zeitreihen bleiben in HA Recorder/Statistics. Aggregate werden aus Sessions neu berechenbar gehalten. GPS-Daten werden nicht gespeichert.

## 11. Kostenmodell

In der ersten Version gilt ein fester Arbeitspreis (Default 0,29 €/kWh, im Options Flow änderbar mit Gültigkeitsdatum); gerechnet wird trotzdem pro Energieintervall, damit Tibber oder ein anderer dynamischer Tarif später nur eine neue Preisquelle ist.

```latex
\text{Kosten}_{\text{Session}} = \sum_i E_i \cdot p_i
```

- `E_i` = Halo-Energie im Intervall i (aus `energy_intervals` der Session, Raster 15 min).
- `p_i` = Preis im Intervall i. v1: konstant aus `price_history` (Preis + gültig ab), damit eine Preisänderung alte Monate nicht umschreibt.
- Fremdladungen: Kosten wie eingegeben.
- Grundgebühr wird nicht anteilig umgelegt (Nicht-Ziel).

```yaml
costs:
  price_source: fixed            # später: entity (Tibber o. ä.)
  price_history:
    - {valid_from: 2026-10-01, eur_per_kwh: 0.29}
  interval_min: 15
```

Kennzahlen: Kosten pro Session, Monat, Jahr; €/100 km (Heim + Fremd, dokumentierte Energie); Kosten nur Heimladen für die Hausabrechnung.
