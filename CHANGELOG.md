# Changelog

## 0.17.1 – 2026-10-17

- **Preis-Fenster aufgeräumt:** Das Fenster „Preis der Fremdladung“ ist jetzt eine eigene,
  deckende Seite, das Cockpit scheint nicht mehr durch. Das Eingabefeld geht über die volle
  Breite mit großer Schrift, die Preis-Knöpfe stehen groß im 2×2-Raster, darunter
  „Abbrechen“ und „Speichern“. Zwei CSS-Namenskonflikte haben die untere Knopfzeile
  abgeschnitten; sie sind behoben.

## 0.17.0 – 2026-10-17

- **Preis-Knöpfe statt Textfeld:** Die Push-Nachricht nach einer erkannten Fremdladung (und
  der Push-Test) zeigt beim langen Drücken Knöpfe mit festen Preisen, Standard
  **0,39 / 0,49 / 0,59 / 0,69 €/kWh**. Ein Tipp speichert den Preis. Die Preise legst du unter
  Einstellungen → Fremdladen → „Preis-Knöpfe in der Push-Nachricht“ fest (bis zu vier,
  getrennt mit Semikolon).
- **Antippen öffnet ein Eingabefenster mit Ziffernblock:** Ein einfacher Tipp auf die
  Mitteilung öffnet das Panel mit dem Fenster „Preis der Fremdladung“. Das Feld öffnet auf
  dem iPhone den Ziffernblock mit Komma, die Preis-Knöpfe stehen dort ebenfalls bereit.
  Das iOS-Textfeld in der Mitteilung selbst kann keinen Ziffernblock zeigen und entfällt
  deshalb.
- Neuer Dienst `ev_charging_pilot.set_external_price` (id, price).

## 0.16.1 – 2026-10-17

- **Neu: Push-Test für die Preisabfrage** im Diagnose-Reiter. „Test-Push senden“ schickt
  die Frage nach dem Preis pro kWh aufs Handy, genau wie nach einer erkannten
  Fremdladung. Die Antwort erscheint direkt in der Karte, z. B. „angekommen – 0,49 €/kWh
  erkannt“ oder „nicht erkannt“ mit der Eingabe. Gespeichert wird dabei nichts. Auch als
  Dienst `ev_charging_pilot.test_price_push`.

## 0.16.0 – 2026-10-17

- **Preis per Push nach erkannter Fremdladung:** Erkennt der Pilot eine Ladung außer Haus,
  hat die Push-Nachricht jetzt den Knopf **„Preis eingeben“** mit Textfeld. Auf dem
  iPhone die Mitteilung lange drücken bzw. aufziehen, den Preis pro kWh eintippen (z. B.
  „0,49“, „0.49 €“ oder „49 ct“) und „Speichern“ tippen. Der Preis wird bei der
  Fremdladung hinterlegt und fließt in Kosten und Statistik ein. Kann der Pilot die
  Eingabe nicht lesen, meldet er das per Push.
- **Formulare einklappbar:** „Fremdladung manuell erfassen“ und „Kilometerstand manuell
  eintragen“ sind standardmäßig zugeklappt und bleiben offen, solange man sie braucht.
  Die Karte erklärt kurz, wie die automatische Erkennung arbeitet.

## 0.15.1 – 2026-10-17

- **Kilometer kommen automatisch aus OVMS:** Die Kilometerquelle stand bisher
  standardmäßig auf „manuell“. Ohne manuelle Einträge blieben Strecke, kWh/100 km und
  €/100 km in den Monats- und Jahreswerten leer, obwohl OVMS den Kilometerstand liefert.
  Neue Voreinstellung „automatisch“: Fahrzeugdaten, wenn ein OVMS-Kilometerstand
  zugeordnet ist, sonst manuell. Eine bewusst gewählte Einstellung bleibt erhalten.
- **Verbrauch netto statt brutto:** OVMS zählt entnommene und rekuperierte Energie
  getrennt. Der Verbrauch je Fahrt und in Temperaturgruppen/Jahreszeiten rechnet jetzt
  mit „verbraucht minus Rekuperation“; vorher war er um die Rekuperation zu hoch.
- **Rangierfahrten verfälschen nichts mehr:** Fahrten unter 1 km zeigen keinen
  kWh/100-km-Wert mehr (z. B. 138 kWh/100 km für 60 m), und Fahrten ohne Strecke oder mit
  unstimmigen Zählern fließen nicht in die Gruppenstatistik ein.
- **Kosten in Temperaturgruppen/Jahreszeiten** rechnen mit deinem tatsächlichen
  Heimstrompreis aus den Ladungen (dynamischer Tarif inklusive) statt mit dem Festpreis.

## 0.15.0 – 2026-10-17

- **Neu: Ladestrom einstellbar.** Jeder Wochenplan, die einmalige Abfahrt und „Jetzt laden“
  haben jetzt ein Feld **„Ladestrom“** (6–16 A, mit kW-Angabe, z. B. 12 A ≈ 8,3 kW). Der
  Pilot setzt den Strom an der Wallbox (`number.…_max_current`), wenn er laden will, und
  nur dann. Nachts schonend mit 12 A, bei Bedarf mit 16 A (11 kW).
- „Standard“ lässt die Wallbox-Einstellung unverändert. Unter Einstellungen → Fahrzeug und
  Wallbox kannst du einen **Standard-Ladestrom** für alle Pläne ohne eigene Angabe
  festlegen (0 = Wallbox-Einstellung lassen).
- Startzeit und Ladeprognose rechnen mit der Leistung, die zum gewählten Strom passt.
- Der Ladestrom für „Jetzt laden“ gilt sofort, ohne Neuladen der Integration, und steht im
  Ladeplan-Reiter direkt unter „Laden bis“.
- Neue Ereignisse „Ladestrom 12 A (ca. 8,3 kW)“; im Dry-Run wird das Setzen nur
  protokolliert.

## 0.14.1 – 2026-10-17

- **Kein falsches „Eingesteckt“ nach einem Neustart:** Direkt nach dem Start von HA ist
  die OVMS-Integration oft noch nicht geladen. Für ein paar Sekunden sah der Pilot nur die
  gesperrte Wallbox („kein Kabel“) und hielt die anschließende OVMS-Meldung „Stecker
  erkannt“ für ein neues Einstecken. Die Folge war eine Push-Nachricht „Eingesteckt – Wie
  soll geladen werden?“, obwohl das Auto schon seit Stunden steckte. Solange der
  OVMS-Stecker noch keinen Wert hat, gilt „kein Kabel“ der gesperrten Wallbox jetzt nicht
  mehr als Information.

## 0.14.0 – 2026-10-17

- **Neu: Ladetest im Diagnose-Reiter.** Ein Knopf prüft einmal die ganze Startkette wie in
  einer echten Nacht: Wallbox freigeben, auf Ladeleistung warten, bei Bedarf das Auto
  wecken (erst per OVMS, als letztes Mittel per CP-Puls), kurz stabil laden und die
  Wallbox danach wieder sperren. Die Karte zeigt jeden Schritt mit Zeitpunkt und am Ende
  das Ergebnis, z. B. „Ladung startete nach Wecken per OVMS mit 2,3 kW“. Der Test dauert
  höchstens 8 Minuten und steht auch als Dienst `ev_charging_pilot.charge_test` zur
  Verfügung.
- Der Test läuft nur im Live-Modus und mit eingestecktem Auto. Er bricht ab, wenn das
  Kabel gezogen oder das Laden manuell geändert wird. Ist gerade ein Ladeplan aktiv,
  bleibt die Wallbox danach an.
- Wer kurz zuvor den Dry-Run-Schalter umgelegt hat, löst Aktionen jetzt sofort im
  richtigen Modus aus (bisher erst nach dem nächsten Takt).

## 0.13.9 – 2026-10-17

- **Weiterladen nach Blockende:** Bisher endete die Ladung hart mit dem gewählten günstigen
  Block, auch wenn das Ziel noch nicht erreicht war, z. B. weil das Wecken ein paar
  Minuten gedauert hat oder der kalte Akku im Winter langsamer lädt. Bis zur Abfahrt wurde
  dann nicht mehr nachgeladen. Jetzt lädt der Pilot weiter, bis das Ziel erreicht ist, das
  Auto selbst beendet oder „Fertig vor Abfahrt“ erreicht ist. Das gilt nur, wenn zum
  Blockende tatsächlich geladen wird; das Auto wird dafür nie zusätzlich geweckt. Im
  Ereignisprotokoll steht dann „Ladeziel zum Blockende noch nicht erreicht – lade weiter
  bis zum Ziel“.

## 0.13.8 – 2026-10-17

- **Voller Akku steht nicht mehr stundenlang:** Mit Preisoptimierung suchte der Plan in den
  24 Stunden vor der Abfahrt einfach die günstigste Zeit. Bei Ziel 100 % konnte das Auto so
  z. B. schon um 23 Uhr voll sein und bis zum Morgen bei 100 % stehen. Neu: Ladeziele über
  „Hoher Ladestand ab“ (Standard 90 %) werden höchstens „… so lange vor Abfahrt voll“
  (Standard 2 h) vor „Fertig vor Abfahrt“ erreicht. Innerhalb dieses Rahmens wird weiter
  die günstigste Zeit genommen. Einstellbar unter Einstellungen → Preise, 0 h schaltet
  die Begrenzung ab.

## 0.13.7 – 2026-10-17

- **Eingaben bleiben stehen:** Das Panel zeichnet sich bei neuen Live-Werten (SOC,
  Leistung …) alle paar Sekunden neu. Dabei wurden die Formulare „Einmalige Abfahrt“,
  „Fremdladung“ und „Kilometerstand“ auf ihre Vorgaben zurückgesetzt (z. B. morgen 07:00
  und 100 %), sobald man ein Feld verlassen hatte. Eingetippte Werte bleiben jetzt erhalten,
  bis sie erfolgreich gespeichert sind.

## 0.13.6 – 2026-10-17

- **Kostenprognose realistisch:** Die Prognose rechnete volle Ladeleistung über den ganzen
  Block inklusive Reserve und zeigte so deutlich zu viel an (z. B. 2,40 € für 4 kWh). Jetzt
  zählt nur die benötigte Energie zum Durchschnittspreis des gewählten Blocks.
- Eine einmalige Abfahrt heißt im Ladeplan und Cockpit jetzt „Einmalige Abfahrt“ bzw.
  „Einmalig: Abfahrt So., 18.10., 15:50“ statt „Heute Nacht“, weil sie auf jeden Tag fallen
  kann.

## 0.13.5 – 2026-10-17

- **Wichtig für Pendeltage: Preisblock nur festhalten, wenn das Auto eingesteckt ist.**
  Bisher wurde der günstigste Ladeblock beim Erreichen fest eingeplant, auch wenn das Auto
  gar nicht zu Hause war. Lag er z. B. Montagmittag, während das Auto im Büro steht,
  verstrich er ungenutzt, und für die Abfahrt am nächsten Morgen wurde nicht mehr geladen.
  Jetzt wird ein verpasster Block ab dem Einstecken neu geplant, und zwar wieder in der
  günstigsten noch möglichen Zeit vor der Abfahrt.

## 0.13.4 – 2026-10-17

- **Einstecken wird auch bei gesperrter Wallbox erkannt:** Die Charge-Amps-Halo meldet das
  Kabel nur, solange der Ladepunkt freigegeben ist. Weil der Charging Pilot sie im
  Normalfall gesperrt hält, stand das Cockpit trotz eingestecktem Auto auf „Nicht
  eingesteckt“. Neu: Das Auto meldet über OVMS selbst, dass der Ladestecker steckt
  (`…_charge_plug_detected`). Der OVMS-Standort (`device_tracker …_location`) sorgt dafür,
  dass ein Stecker an einer fremden Ladesäule nicht als Wallbox-Kabel zählt.
- Bestehende Installationen übernehmen beide Entitäten beim Start automatisch; im
  Einrichtungsdialog stehen sie unter den Fahrzeugwerten.

## 0.13.3 – 2026-10-17

- **„Preisquelle liefert keine Preise“ nach einem HA-Neustart behoben:** Der Preisabruf lief,
  bevor Tibber nach dem Start seine Preise geladen hatte, bekam eine leere Antwort und
  versuchte es erst 30 Minuten später erneut. Jetzt wartet der Abruf, bis HA vollständig
  gestartet ist, und wiederholt einen Fehlschlag nach 1, 2 und 5 Minuten. Die Warnung
  erscheint nur noch, wenn auch diese Versuche scheitern.

## 0.13.2 – 2026-10-16

- **Leistungsanzeige und 24-h-Kurve skalieren auf die echte Ladeleistung:** bei einem
  größeren Bordlader als eingestellt (smart 453 mit 22-kW-Lader an einer 11-kW-Wallbox)
  stand die Anzeige bisher am Anschlag und die Kurve war oben abgeschnitten. Maßstab ist
  jetzt die Wallbox bzw. die gemessene Leistung.
- Hinweis bei „Ladeleistung des Fahrzeugs“: smart 453 hat 4,6 kW Serie oder 22 kW mit
  Schnelllader; zuhause begrenzt die Wallbox.

## 0.13.1 – 2026-10-16

- **Neuer Akku im Cockpit:** moderne Kapsel mit Farbverlauf (rot → gelb → grün je nach
  Ladestand), Glanz, feinen Zellen-Linien und einem Lichtschimmer beim Laden; Mindest- und
  Ziel-Ladestand als beschriftete Marker. Schläft das Auto, steht darunter „letzter bekannter
  Ladestand“.
- **Langsamer laden ab 80 %** (vorher 90 %): so verhält sich der smart 453. Einstellbar unter
  Einstellungen → Fahrzeug und Wallbox → „Lädt langsamer ab Ladestand“.
- **Behoben: 22-kW-Bordlader wurde beim Lernen verworfen.** Die gemessene Ladeleistung
  (z. B. ~11 kW an der Halo) galt als unplausibel, weil sie über dem eingestellten
  Bordlader lag. Grenze ist jetzt die Wallbox; der gemessene Wert ersetzt den Bordlader-Wert.

## 0.13.0 – 2026-10-16

- **Systemtest** (Panel → Diagnose): prüft Schritt für Schritt Wallbox-Freigabe,
  Kabel/Leistung/Zähler, internen Zeitplan der Wallbox, CP-Relais und Shelly-Failsafe,
  Fahrzeugdaten, Befehlsweg zum Auto (inkl. Weckbefehl – nicht ausgeführt), Push-Ziel und
  Strompreis. Es wird nichts geschaltet und das Auto nie geweckt. Optional mit Test-Push.
- **Einmalige Abfahrt mit Datum** (Panel → Ladeplan): z. B. Freitag 07:00 mit Ziel 100 %
  für den Urlaub. Gilt zusätzlich zu den Wochenplänen und löscht sich nach der Abfahrt.
  Auch per Service `start_one_shot` mit `departure_at` und `target_soc`.
- **Wochenrückblick** am Sonntag um 18:00 per Push: kWh zuhause, Kosten, Ladungen,
  Weckvorgänge, Fremdladungen und Kilometer der letzten 7 Tage (abschaltbar unter
  Benachrichtigungen).
- README: Energie-Dashboard mit `sensor.ev_pilot_home_energy_total`.

## 0.12.0 – 2026-10-16

- **Die Prognose lernt aus den eigenen Ladungen:** nach drei Heimladungen ersetzen
  gemessene Werte die Nennwerte – Netzenergie je Prozent Ladestand (inkl. Verluste) und die
  tatsächliche Ladeleistung (aus den 15-Minuten-Werten). Ausreißer (falsche SOC-Sprünge,
  Fehlstarts) zählen nicht. Abschaltbar unter Einstellungen → Fahrzeug und Wallbox.
  Das Cockpit zeigt unter „Prognose“, woraus gelernt wurde.
- **Langsameres Laden kurz vor voll berücksichtigt:** oberhalb von 90 % rechnet der Plan
  mit 60 % der Ladeleistung. Ein Ziel von 100 % startet dadurch früher und ist zur Abfahrt
  wirklich fertig.

## 0.11.0 – 2026-10-16

- **Cockpit sagt in einem Satz, was passiert:** z. B. „Lädt in der günstigsten Zeit
  Mi 02:00–03:12 – Abfahrt Mi 05:30, fertig vor 05:00“, „Ziel 90 % erreicht – das Auto ruht
  bis zur Abfahrt“ oder „Nicht eingesteckt – bitte bis 04:27 einstecken“. Bei Fehlern steht
  dort, was zu prüfen ist, und der Knopf heißt „Erneut versuchen“.
- **Ladeplan-Karte neu:** Name und Ein/Aus-Schalter im Kopf, darunter eine Zeile mit der
  nächsten Abfahrt; Abfahrtstage als Knöpfe; „Wann laden?“ als Umschalter „Rechtzeitig zur
  Abfahrt“ / „Ab fester Uhrzeit“ – es erscheint nur die jeweils passende Uhrzeit;
  Mindest- und Ziel-Ladestand mit Balken.
- **Zeitleiste der Nacht** jetzt auch im Ladeplan, mit Uhrzeit des Ladeblocks und
  Klimastart; der Block endet bei der voraussichtlichen Fertigzeit.
- **Ereignisprotokoll:** Standardansicht „Wichtiges“ blendet Routineschritte aus,
  Meldung vor Code, Knopf „Aktualisieren“; lädt nur noch alle 30 s statt alle 5 s.
- **Ruhigeres Panel:** neu gezeichnet wird nur, wenn sich etwas Sichtbares geändert hat;
  Scrollpositionen in Tabellen bleiben erhalten.

## 0.10.0 – 2026-10-16

- **Fremdladeerkennung bei Wallbox-Cloud-Ausfall abgesichert:** Laden außer Haus wird nur
  erkannt, wenn das Kabel zuhause nachweislich nicht steckt; ein SOC-Sprung nur, wenn der
  Zähler der Wallbox an beiden Enden bekannt ist. Vorher konnte ein Cloud-Ausfall eine
  Heimladung als Fremdladung (0,59 €/kWh) eintragen. Uhrzeiten in der Notiz jetzt in Ortszeit.
- **Nur noch ein Zeitpuffer:** „Fertig vor Abfahrt“ im Plan. Die separate
  „Sicherheitsreserve“ (20 min) entfällt; die Startzeit enthält automatisch eine Reserve von
  10 % der Ladedauer (mind. 5 min) für Prognosefehler. Bestehende Einstellungen werden
  automatisch umgestellt.
- **Ladepläne und „Jetzt laden“-Ziel für alle Benutzer:** auch Nicht-Admins (z. B.
  Familienmitglieder) können Pläne und das manuelle Ladeziel ändern. Die übrigen
  Einstellungen bleiben Administratoren vorbehalten.
- **Push-Knöpfe gelten nur für das jeweilige Einstecken:** eine alte „Eingesteckt“-Nachricht
  (Kabel seitdem gezogen oder älter als 12 h) startet nichts mehr.
- **„Erneut versuchen“ direkt in der Push-Nachricht** nach fehlgeschlagenem Start oder
  Abbruch, dazu ein konkreter Hinweis, was zu prüfen ist (Stecker, Wallbox online …).
- **Cockpit-Kurve nach Neustart nicht mehr leer:** die letzten 24 h kommen aus dem Verlauf
  von Home Assistant.
- Selten gebrauchte Diagnose-Entitäten (letztes Ereignis, Datenkonflikt, SOC veraltet,
  Erreichbarkeit) sind bei Neuinstallation ausgeblendet.

## 0.9.3 – 2026-10-16

- **Behoben: Nach Erreichen des Ziel-SOC wurde das Auto geweckt.** Sobald der SOC-Wert des
  schlafenden Autos älter als 10 min war, schaltete der Plan die Wallbox wieder ein und
  startete Wecken per Fahrzeug und CP-Puls, danach kam „Ladestart fehlgeschlagen“. Ein
  erreichtes Ziel gilt jetzt für das ganze Ladefenster. Nachgeladen wird nur, wenn ein
  frischer SOC mindestens 3 % unter dem Ziel liegt – und dafür wird nie geweckt.
- **Ladeende ohne Signal wird erkannt:** sinkt die Leistung zum Schluss ab (Akku voll),
  meldet OVMS kürzlich „lädt nicht“ (auch wenn das Auto gleich danach einschläft) oder ist
  der Akku bei 99 %, ist das ein normales Ladeende – kein Abbruch, kein CP-Puls.
- **Probebetrieb als echter Schattenbetrieb:** die Steuerung rechnet mit einer gedachten
  Wallbox, die jeden Befehl ausführt. Keine Fehlalarme, keine fehlgeschlagenen Sessions,
  kein Health-Abzug mehr in Nächten, in denen nichts geschaltet wird. Beim Wechsel auf Live
  wird der Zustand neu aus der Wirklichkeit abgeleitet.
- „Ladung abgebrochen“ wird nur noch einmal gepusht (nach dem erfolglosen Neustart).
- „Datenkonflikt“ erst, wenn Wallbox und Fahrzeug sich länger als 3 min widersprechen
  (unterschiedliche Abfrageverzögerung beim Start/Stopp).
- Normale Ladestarts erscheinen nicht mehr als „Laufende Ladung nach Neustart übernommen“.
- Neue Nacht-Szenariotests (schlafendes Auto, volles Auto, Probebetrieb); Integrationstests
  laufen mit fester Uhrzeit statt der echten.

## 0.9.2 – 2026-10-16

- **Behoben: gelöschte Ladepläne kamen nach einem Neustart zurück.** Eine leere Planliste
  wurde beim Start als „nichts gespeichert“ gelesen und durch den Standardplan ersetzt.
- **Ladepläne speichern sich jetzt automatisch** kurz nach jeder Änderung; „Plan löschen“
  fragt nach und löscht sofort. Es gibt keinen Speichern-Knopf mehr, den man vergessen
  kann (vorher gingen Änderungen beim Reiterwechsel stillschweigend verloren).
- Einstellungen: Wechsel des Reiters mit ungespeicherten Änderungen fragt nach.
- „Fahrzeug: Lesen & Schreiben“ ließ sich in 0.9.0 nicht ausschalten (Speichern blieb
  gesperrt) – seit 0.9.1 behoben, jetzt mit Neustart-Test abgesichert.
- Regler „Mindest-/Ziel-SOC“ (Entitäten) stürzen ohne Plan nicht mehr ab, sondern legen
  den Standardplan an.

## 0.9.1 – 2026-10-16

- **Einstellungen neu aufgebaut:** aufklappbare Gruppen mit Symbol und Kurzbeschreibung,
  je Option eine Zeile mit Erklärung, Schalter statt Häkchen, Einheiten im Eingabefeld.
  Umschalter **Einfach | Experte** – Feinabstimmung (Ladeerkennung, Datenqualität,
  OVMS-Befehle) nur im Expertenmodus. Abhängige Felder erscheinen nur, wenn sie
  gebraucht werden (z. B. Preis-Entität nur bei Preisquelle „Entität“). Speichern-Leiste
  erscheint nur bei Änderungen, „geändert“-Markierung je Gruppe. Auf dem Smartphone
  stehen Bezeichnung und Eingabe untereinander.
- „Ziel bei ‚Jetzt laden‘“ aus den Einstellungen entfernt – es wird im Ladeplan eingestellt.
- **OVMS-Abgleich mit der smart-453-Doku:** Wecken nutzt beim smart 453 automatisch
  `xsq wakeup` (erkannt an den `xsq.*`-Metriken), sonst `wakeup`; Vorgabe „auto“.
  Der HV-Kontaktorzähler `xsq.bms.contactor.cycles` wird als Vektor gelesen
  (verbrauchte Zyklen). Klima `homelink 1/2/3` = 5/10/15 min, nur ab SOC > 30 %.

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
