# Changelog

## 0.9.0 – 2026-10-16

- **Fahrzeug: ein Schalter „Lesen & Schreiben“** (Einstellungen → Allgemein). Aus =
  nur lesen. An = Wakeup und Vorklimatisierung werden gesendet. Der Befehlsweg wird
  automatisch erkannt (HACS-Integration „OVMS“ mit `ovms.send_command`, Fahrzeug-ID aus
  deren Eintrag); MQTT-Topic/Script bleiben nur als Experten-Rückfall. Die OVMS-Befehle
  sind mit den v3-Standards vorbelegt (`wakeup`, `homelink 1/2/3`, `climatecontrol off`).
- **Cockpit ohne Doppelungen:** ein Akku-Balken mit Markern für Mindest- und Ziel-SOC,
  darunter Akkugesundheit (SOH) und Reichweite; der zweite SOC-Ring entfällt.
- **Ladeziele dort, wo sie hingehören:** je Zeitplan als Schieberegler im Reiter
  Ladeplan, dazu „Manuelles Laden“ – Ziel für „Jetzt laden“ (Standard 100 % = voll),
  auch als `number.ev_pilot_manual_target_soc`. Die doppelte Ladeziel-Karte in Cockpit
  und Einstellungen entfällt.
- „Jetzt laden“ (Button, Push, Service ohne Modus) lädt bis zum manuellen Ziel, ohne
  Fahrzeugdaten bis zum Abstecken. Das manuelle Ziel wirkt sofort, ohne Neuladen.

## 0.8.3 – 2026-10-15

- **SOH im Cockpit:** Akkugesundheit (und Reichweite, falls vorhanden) unter dem
  SOC-Ring.
- **Fahrzeug-Status klarer:** Die Diagnose trennt jetzt „Fahrzeugdaten (lesen)“ –
  verbunden/Qualität/zuletzt – von „Wakeup-“ und „Klima-Befehl (senden)“ und nennt
  für eine Sperre jeden Grund (Schalter aus, kein Befehlsweg, Befehl nicht eingetragen).
- Option heißt jetzt „Befehle ans Fahrzeug erlauben (OVMS-Wakeup, Klima)“ statt
  „OVMS-Funktionen aktiv“ – das Lesen der Daten war davon nie betroffen.

## 0.8.2 – 2026-10-15

- Das Panel zeigt die installierte Version neben dem Titel (z. B. „Smarty Charging
  Pilot v0.8.2“). Einzige Quelle ist die `manifest.json`; sie dient auch als
  Cache-Buster für die Panel-Datei, damit nach einem Update sicher die neue lädt.

## 0.8.1 – 2026-10-15

- Neues Logo: Akku mit Ladestand und Blitz über einer Auto-Silhouette
  (`brand/icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`).

## 0.8.0 – 2026-10-15

**Neuer Name: EV Charging Pilot.** Die Integration ist herstellerneutral und
funktioniert mit jeder Wallbox und jedem Fahrzeug, die Home Assistant als Entitäten
kennt.

- **Fahrzeugname frei wählbar** (Einrichtung und Panel → Einstellungen → Allgemein):
  Seitenleiste, Panel-Titel, Gerät, Push-Titel und PDF heißen dann z. B.
  „Smarty Charging Pilot“.
- Domain `ev_charging_pilot`, Entitäten `*.ev_pilot_*`, Panel `/ev-pilot`,
  GitHub-Repo `fschubi/ev_charging_pilot`.
- Texte neutral: „Wallbox“ statt „Halo“, „Fahrzeug“ statt „OVMS“.
- **Achtung, inkompatibel:** Wegen der neuen Domain muss eine bestehende Installation
  („Smart EQ Charging Center“) entfernt und neu eingerichtet werden.

## 0.7.0 – 2026-10-13

- **Neuer Reiter „Einstellungen“** im Panel: alle Optionen (Laden, Wakeup/CP,
  Planung, Strompreis, Klima, Datenqualität, Benachrichtigungen, Statistik,
  Fremdladen, OVMS-Befehle) als Formular; Speichern übernimmt sie wie der
  Options-Flow. Strompreis manuell mit „gültig ab“ und Preis-Historie.
- **Eigenes Fahrzeugfoto:** Upload im Reiter Einstellungen (PNG/JPG/WebP, wird im
  Browser auf 1600 px verkleinert), Anzeige im Cockpit; Download nur mit Login,
  Upload nur für Administratoren. Die gezeichnete Fahrzeuggrafik entfällt –
  ohne Foto zeigt das Cockpit eine Akku-/Stecker-Grafik.
- **Ladeziel-Karte** im Cockpit: Mindest-/Wunsch-SOC per Regler, Abfahrtszeit.
- Fremdladen: Preis pro kWh als Alternative zu den Kosten.
- Integrations-Icon (`brand/`), damit die Geräteseite ein Logo zeigt.

## 0.6.3 – 2026-10-13

- **Shelly-Konfiguration:** Die Prüfung zeigt jetzt jede Abweichung mit Ist- und
  Sollwert (Einschaltzustand, Auto-On, Auto-On-Verzögerung). Neuer Button
  „Shelly konfigurieren“ (Cockpit/Diagnose) bzw. Service `configure_shelly` setzt die
  Failsafe-Werte aus §3.1 per RPC und prüft sofort neu. Passwortgeschützte Shellys
  bekommen eine klare Meldung.
- **Fahrzeuggrafik:** Neu gezeichnet als smart fortwo 453 – echte Proportionen
  (2,70 m × 1,55 m, Räder an den Ecken), lange flache Frontscheibe, Tridion-Zelle als
  „C“ aus Dachrahmen, breitem Rücken und Schweller.
- Klima-Sperrgründe im Klartext (z. B. „OVMS ist noch nicht aktiv“).

## 0.6.2 – 2026-10-13

- **Grafisches Cockpit:** smart-fortwo-Illustration mit Wallbox und Ladekabel
  (animiert beim Laden, Akkuanzeige an der Tür), SOC-Ring mit Mindest-/Wunsch-Marken,
  Leistungs-Tacho, Zeitleiste der Nacht mit Ladeblöcken, Preiskurve und Abfahrt,
  24-h-Verlauf von Leistung und SOC.
- Health-Gründe im Klartext; bei gesperrter Automatik ein deutlicher Hinweis.
- Erkennung: Entitäten der Chargeamps-Integration haben klar Vorrang, Sensoren
  anderer Lade-Integrationen werden nie mehr vorgeschlagen.
- Deutsche Wochentage und Jahreszeiten, Dezimalkomma in den Grafiken.

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
