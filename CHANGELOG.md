# Changelog

## 0.27.23 – 2026-10-25

Ehrlichere Texte und Werte:
- **„Akku voll“ nur bei vollem Akku.** Endete eine Ladung, weil die Leistung absank oder die
  Wallbox „fertig“ meldete, hieß es immer „der Akku ist voll“ – auch bei 80 %. Jetzt:
  „Das Auto hat bei 80 % selbst aufgehört.“
- **Fahrt-Details:** Eine Fahrt mit 0 kWh netto zeigt 0 € statt „–“, und eine Bergab-Fahrt
  mit mehr Rekuperation als Verbrauch kostet 0 € statt eines negativen Betrags.
- **Fremdladung ohne Preis:** Der Monat gilt dann als „geschätzt“, weil diese Ladung mit
  0 € in die Kosten eingeht.

## 0.27.22 – 2026-10-25

Panel: kleine Anzeigefehler behoben:
- **Fehlende Werte zeigen „–“** statt „0,0 kW“ oder „0,000 €/kWh“ (Max./Ø-Leistung, Ø-Preis).
- **Deutsche Begriffe statt Codes:** Ort der Fremdladung („Öffentlich“ statt „public“) und
  Qualität des Ladestands („veraltet“ statt „STALE“).
- **Reichweitenanzeige:** „gestiegen um 3 km“ statt „gesunken um -3 km“.
- **Außentemperatur** ohne leere Klammern, wenn die Quelle fehlt.
- **Ladeplan:** Ein geleertes Uhrzeitfeld behält die alte Zeit (mit Hinweis), statt alle
  weiteren Speicherungen zu blockieren; nach einem abgelehnten Speichern lädt das Panel
  die gespeicherten Pläne neu.
- **Shelly nicht erreichbar:** Der Hinweis heißt jetzt „CP-Wakeup gesperrt – Laden und Ziel
  laufen weiter“ statt „Automatik gesperrt“ (seit v0.27.5 lädt der Pilot dann weiter).
- **Zeitzone:** Uhrzeiten folgen der HA-Profileinstellung (Server- oder Browser-Zeitzone).
- Überlappende Aktualisierungen werden nacheinander ausgeführt (kein doppeltes Laden).

## 0.27.21 – 2026-10-25

Statistik rechnet genauer:
- **Fahrzeugverbrauch je 100 km nur über Fahrten mit gemessener Energie.** Fahrten ohne
  Energiewert (z. B. aus dem Kilometerstand rekonstruiert) zählten mit ihren Kilometern,
  aber ohne Energie – der Verbrauch fiel viel zu niedrig aus (Beispiel: 6 statt 15 kWh/100 km).
- **Gelernter Energiebedarf je Prozent ohne Vorklimatisierung.** Lief während einer Ladung
  die Klimatisierung, rechnete der Pilot deren Strom in „kWh pro % Ladestand“ ein – Planer
  und Ladedauer überschätzten den Bedarf (bis ~18 %).
- **Fremdladung spät erkannt:** Die Akku-Energie ist jetzt die ganze Ladung, nicht nur der
  Teil ab der Erkennung (Beispiel: 4,35 statt 3,15 kWh).
- **Klimaanteil ohne Akkuleistung:** Fehlte die OVMS-Akkuleistung, wurde während einer
  Ladung der ganze Zähleranstieg als Klima gebucht. Ohne Akkuleistung zählt er jetzt als
  Laden (eine reine Klima-Session bleibt Klima). Auch im Nachlauf nach dem Klima-Ende wird
  die Akkuleistung mitgerechnet.

## 0.27.20 – 2026-10-25

Rechte: Live-Schalter, Fehler-Reset und Push-Knöpfe abgesichert:
- **Live-Betrieb einschalten nur für Admins.** Der Modus ist in den Einstellungen schon
  Admin-Sache; über den Schalter „Probebetrieb“ konnte ihn aber jeder Benutzer auf Live
  stellen. Jetzt nur noch Admins (und Automationen); zurück in den Probebetrieb darf
  weiterhin jeder.
- **„Fehler zurücksetzen“ nur für Admins** (Button und Dienst), weil es auch die
  Weckversuche des Ladefensters zurücksetzt.
- **Push-Knöpfe gelten nur für den eigenen Push.** Bisher startete *jedes*
  „mobile_app_notification_action“-Ereignis mit passender Aktion das Laden – von jedem
  Gerät oder aus einer Automation, beliebig oft. Jetzt wirkt ein Knopf nur, wenn der Pilot
  ihn in den letzten 12 Stunden per Push angeboten hat, und nur einmal pro Push.
  Nach einem HA-Neustart sind ältere Pushes nicht mehr bedienbar – dann über das Panel.

## 0.27.19 – 2026-10-25

Zwei Preisblöcke: der zweite Block ist kein Fehlstart mehr:
- **Klare Meldung statt „Ladestart fehlgeschlagen“.** Bei der Option „2 Ladeblöcke“ teilen
  sich beide Blöcke die Weckversuche ihres Ladefensters (höchstens einmal OVMS und einmal
  CP pro Nacht). Schlief das Auto in der Lücke wieder ein und waren die Weckversuche im
  ersten Block schon verbraucht, endete der zweite Block als „Ladestart fehlgeschlagen“ –
  und zählte für die Fehlstart-Sperre mit. Jetzt heißt es „Ladeblock nicht gestartet“
  (Push mit Ladestand und Hinweis, dass das Ziel evtl. nicht erreicht wird, inkl.
  „Erneut versuchen“), ohne als Fehlstart zu zählen.
- Weiterhin gilt: Standard ist ein Block pro Nacht – genau um das Auto nicht zweimal
  wecken zu müssen.

## 0.27.18 – 2026-10-25

Ladepause übersteht einen HA-Neustart:
- **Die Wallbox bleibt nach einem Neustart frei.** Pausierte eine Ladung unter dem Ziel und
  hielt der Pilot die Wallbox über das Fensterende frei („bleibt frei, bis das Kabel gezogen
  wird“), schaltete ein Neustart von Home Assistant sie trotzdem aus. Jetzt merkt sich der
  Pilot die Pause samt ihrem Weckversuch; nach dem Neustart wartet er weiter, ohne erneut
  zu wecken.

## 0.27.17 – 2026-10-25

Klima-Option „Ziel einhalten“ heizt wieder aus der Wallbox:
- **„enforce_target“ gibt die Wallbox für die Klimatisierung frei.** War das Ziel vor der
  Vorklimatisierung erreicht, hielt der Pilot die Wallbox trotzdem aus – das Auto heizte
  aus dem Akku, wie bei „nur Akku“, während die Statuszeile „Strom aus der Wallbox“ zeigte.
  Jetzt ist die Wallbox während der Klimatisierung frei und schaltet erst ab, wenn der
  Ladestand das Ziel um mehr als 1 % überschreitet (Masterplan §9.1).
- Die Standard-Option „Nachladen erlaubt“ und „nur Akku“ sind unverändert.

## 0.27.16 – 2026-10-25

Ziel-SOC: kein Abbruch durch Ausreißer, Nachladen bis zum Ziel:
- **Ein einzelner falscher Ladestand beendet die Ladung nicht mehr.** Meldete OVMS kurz
  z. B. 95 % bei echten 65 %, schaltete der Pilot sofort ab. Springt der Ladestand um mehr
  als 5 Prozentpunkte, muss er jetzt 3 Minuten stehen, bevor er am Ziel abschaltet.
  Steigt er wie beim Laden üblich in kleinen Schritten, wird wie bisher sofort abgeschaltet.
- **Nachladen läuft bis zum Ziel.** Sank der Ladestand nach erreichtem Ziel unter Ziel − 3 %,
  wurde zwar nachgeladen, aber schon bei Ziel − 3 % wieder abgeschaltet (z. B. 87 statt
  90 %). Die 3 % entscheiden jetzt nur noch, *ob* nachgeladen wird – dann bis zum Ziel.

## 0.27.15 – 2026-10-25

Panel: aufgeklappte Details bleiben nach einer Aktion lesbar:
- **Kein endloses „Lade Verlauf …“ / „Lade Details …“ mehr.** War der Temperaturverlauf
  oder eine Session- bzw. Fahrt-Zeile aufgeklappt und man drückte z. B. „Klima 10 min“
  oder „Jetzt laden“, blieb die Zeile auf „Lade …“ stehen, bis man sie zweimal zu- und
  aufklappte. Die geladenen Details bleiben jetzt erhalten; beim Wechsel von Reiter oder
  Monat werden aufgeklappte Zeilen sauber geschlossen.

## 0.27.14 – 2026-10-25

Cockpit und Statuskarte zeigen die Vorklimatisierung auch ohne Kabel:
- **„Vorklimatisierung läuft“ statt „Nicht eingesteckt“.** Lief die Klimatisierung bei
  abgestecktem Auto aus dem Akku, zeigten Cockpit und `sensor.ev_pilot_status` (die
  Mushroom-Karte) „Nicht eingesteckt …“. Jetzt steht dort „Vorklimatisierung läuft · Strom
  aus dem Akku“.

## 0.27.13 – 2026-10-25

Unsinnige Sensorwerte legen den Piloten nicht mehr lahm:
- **„inf“, „nan“ oder überlaufende Werte gelten als ungültig.** Meldete ein Sensor z. B.
  „inf“ als Leistung, rechnete der Pilot damit weiter und stürzte während einer Ladung oder
  Fahrt bei jedem Takt ab – die Schaltbefehle dieses Takts gingen verloren, solange der
  Wert anstand. Solche Werte sind jetzt „ungültig“ wie ein unlesbarer Text.

## 0.27.12 – 2026-10-25

Diagnose zeigt Werte mit der richtigen Einheit:
- **„9139.369999999999 kW“ behoben.** Werte in kW (z. B. Akkuleistung, Ladeleistung aus
  OVMS) rechnet der Pilot intern in Watt um, zeigte in „Datenqualität je Wert“ und im
  Systemtest aber die ursprüngliche Einheit kW dazu. Jetzt passt die Einheit immer zur Zahl
  (9139,37 W), Zahlen werden auf höchstens drei Nachkommastellen gekürzt.
- Fehlt ein Wert oder sein Alter, steht dort „–“ statt „– s“.

## 0.27.11 – 2026-10-25

HV-Kontaktorzyklen ohne falsche Statistik:
- **Der Sensor „HV-Kontaktorzyklen“ ist kein steigender Zähler mehr.** Die OVMS-Integration
  liefert beim smart die *verbleibenden* Zyklen (z. B. 194 754, fallend). Als
  „steigender Zähler“ wertete die HA-Langzeitstatistik jeden Schritt nach unten als
  Zählerreset. Jetzt ist er ein normaler Messwert; die Warnung „HV-Kontaktor auffällig“
  und „heute“ zählten schon immer nur die Größe der Änderung.
- Hinweis: HA meldet unter *Entwicklerwerkzeuge → Statistiken* evtl. einmalig eine
  geänderte Zustandsklasse für `sensor.ev_pilot_hv_contactor_cycles` – dort „Beheben“ wählen.

## 0.27.10 – 2026-10-25

„Klima stopp“ respektiert den Fahrzeugzugriff:
- **Ohne „Lesen & Schreiben“ geht kein Befehl mehr ans Auto.** Der Button bzw. Dienst
  „Klima stoppen“ schickte den OVMS-Befehl bisher auch, wenn der Fahrzeugzugriff auf
  „nur Lesen“ stand – als einziger Fahrzeugbefehl. Jetzt erscheint stattdessen der Hinweis
  „Klima-Stopp nicht gesendet – Fahrzeugbefehle sind nicht freigegeben“.
- Damit sind alle kritischen und hohen Punkte aus dem Prüfbericht vom 24.10. behoben
  (v0.27.2–v0.27.10, Details in `docs/pruefbericht-2026-10-24.md`).

## 0.27.9 – 2026-10-25

Ladeenergie und Kosten robust gegen Zähler-Aussetzer:
- **Ein einzelner Fehlwert des Wallbox-Zählers erzeugt keine Phantomkosten mehr.** Meldete
  die Halo-Cloud einmal 0 kWh statt des echten Zählerstands, zählte der Sprung zurück auf
  den echten Wert als Ladeenergie – im Monatsbericht hätten dann rund 1000 kWh und mehrere
  hundert Euro gestanden. Anstiege, die schneller sind, als eine Wallbox liefern kann,
  werden jetzt verworfen (gemessen ab der letzten Zähleränderung, mit Spielraum für
  verspätete Cloud-Werte).
- **Zählerreset während einer Ladung:** Energie und Kosten der Session stimmen wieder
  überein. Bisher stand 0 kWh in der Session, die Kosten aber zählten trotzdem.
- Die Klimaenergie einer Session wird auch in Euro nie größer als der Netzbezug.

## 0.27.8 – 2026-10-25

Hängende Wallbox-Cloud unterbricht keine Ladung mehr:
- **Kein Wecken und kein CP-Puls, während das Auto selbst „lädt“ meldet.** Lieferte die
  Halo-Cloud eine Zeit lang keine neuen Leistungswerte, hielt der Pilot die laufende Ladung
  für pausiert, weckte das Auto und unterbrach mit dem CP-Puls ausgerechnet die Ladung, die
  gerade lief. Jetzt zählt in dieser Lage die frische Meldung des Autos (OVMS „lädt“).
- Meldet die Halo dagegen frisch 0 W, gilt das weiterhin – auch wenn OVMS noch kurz
  „lädt“ zeigt.

## 0.27.7 – 2026-10-25

Umschalten vom Probebetrieb auf Live lädt sofort:
- **Live mitten im Ladefenster startet frisch.** Im Probebetrieb fließt nie Strom, deshalb
  endet ein Ladefenster dort als „Ladestart fehlgeschlagen“. Wurde danach im selben Fenster
  auf Live umgeschaltet, übernahm der Live-Betrieb dieses Ergebnis und schaltete die ganze
  Nacht nichts – 0 kWh. Gerade beim ersten Live-Gang nach den Probenächten wichtig.
- Probebetrieb und Live führen ihre Weckversuche und Fenster-Ergebnisse jetzt getrennt:
  Ein kurzer Ausflug in den Probebetrieb setzt auch keine echten Weckversuche zurück.

## 0.27.6 – 2026-10-25

Nach Fehlstarts geht es von selbst weiter:
- **Die Sperre nach zwei Fehlstarts löst sich wieder.** Schlug der Ladestart zweimal
  hintereinander fehl, meldete das System „Fehler“ und sperrte die Automatik – dauerhaft,
  denn nur eine erfolgreiche Ladung hätte den Zähler zurückgesetzt, und die war gesperrt.
  Ab der dritten Nacht wurde gar nicht mehr geladen. Jetzt gilt die Sperre nur noch bis
  zum nächsten Ladefenster („Neues Ladefenster – nach den Fehlstarts wird wieder normal
  geladen“) oder bis das Kabel gezogen wird.
- Die Push-Meldung zu den Fehlstarts kommt weiterhin.

## 0.27.5 – 2026-10-25

Shelly nicht erreichbar – Laden geht weiter, Ziel-SOC gilt:
- **Fällt der Shelly (CP-Relais) aus, wird nicht mehr alles eingefroren.** Bisher schaltete
  der Systemfehler „Shelly nicht erreichbar“ jede Automatik ab – auch das Abschalten am
  Ziel. Ein WLAN-Aussetzer von ein paar Stunden ließ das Auto so auf 100 % statt 90 % laden,
  und die Wallbox blieb nach der Abfahrt an. Jetzt läuft das zeitbasierte Laden über die
  Wallbox weiter, das Ziel wird eingehalten und die Vorklimatisierung bleibt möglich; gesperrt
  ist nur der CP-Wakeup (wie im Masterplan §8.2 vorgesehen).
- Der Fehler bleibt sichtbar (System „Fehler“, Push). Bei offenem oder nicht
  zurückgestelltem CP-Relais und anderen echten Fehlern bleibt die Automatik gesperrt.

## 0.27.4 – 2026-10-25

Ladepause: höchstens ein Weckversuch je Art und Nacht:
- **Kein zweites Wecken nach einer Ladepause.** Pausierte die Ladung unter dem Ziel und
  hielt der Pilot die Wallbox über das Fensterende (bzw. Preisblock-Ende) frei, galt das
  intern als neues Ladefenster – mit frischen Weckversuchen. In einer Nacht konnte das Auto
  so zweimal per OVMS und zweimal per CP-Puls geweckt werden. Jetzt zählt die gehaltene
  Pause zum ursprünglichen Fenster: Ist dessen Weckversuch verbraucht, wird nur noch
  gewartet („Ladung pausiert – Wallbox bleibt frei“).

## 0.27.3 – 2026-10-25

Ein volles Auto wird nicht mehr geweckt:
- **Kein Wecken, wenn der zuletzt bekannte Ladestand das Ziel schon erreicht.** Schlief das
  Auto mit z. B. 92 % bei Ziel 90 %, öffnete der Plan trotzdem sein Ladefenster, es floss
  nichts, und die Weckkette (OVMS, danach CP-Puls) weckte das volle Auto – jede Nacht ein
  unnötiger HV-Schaltzyklus. Jetzt gibt die Wallbox nur frei; nimmt das Auto keinen Strom,
  endet das Fenster still („Nachladen nicht gestartet“), ohne Fehlstart-Meldung.
- Abgeschaltet wird wie bisher nur mit frischem Ladestand – im Zweifel darf das Auto laden.

## 0.27.2 – 2026-10-25

Gespeicherte Historie ist beim Zurückgehen auf eine ältere Version sicher:
- **Kein Datenverlust mehr bei einem Downgrade.** Kannte eine ältere Version ein Feld aus
  einer neueren nicht (z. B. Fahrstil oder Reichweite je Fahrt), brach der Start ab – und
  beim Aufräumen wurde der leere Zustand über alle Ladesessions, Fahrten und Ereignisse
  gespeichert. Jetzt werden unbekannte Felder ignoriert, und nach einem fehlgeschlagenen
  Laden wird nie gespeichert.
- **Ein einzelner beschädigter Datensatz** wird übersprungen (Warnung im Log) statt die
  ganze Historie unlesbar zu machen.

## 0.27.1 – 2026-10-22

Reichweite gegen Anzeige – richtig gemessen und verständlich angezeigt:
- **Falsche Werte wie „820 %“ behoben.** Der smart rechnet die laufende Heizung in die
  Reichweitenanzeige ein: Beim Losfahren lief noch die Vorklimatisierung (101 statt 112 km),
  und nach dem Abstellen springt die Anzeige hoch, weil die Heizung ausgeht (88 → 98 km).
  Jetzt zählt beim Start der höchste Wert der ersten 3 Minuten und am Ende der letzte Wert,
  solange das Auto noch an war. Am 21.10.: 112 → 88 km für 24,6 km statt 101 → 98.
- **Alle bisherigen Fahrten** werden mit der neuen Regel aus der HA-Historie neu berechnet.
- **Verständliche Anzeige** statt einer nackten Prozentzahl: „4 % weiter“ (du bist weiter
  gekommen als angezeigt) bzw. „12 % kürzer“ (die Anzeige war zu optimistisch); in den
  Details „24,6 km für 24 km Anzeige → 3 % weiter als angezeigt“.

## 0.27.0 – 2026-10-22

Eigener Fahrstil-Wert je Fahrt (Reiter „Drive & Energy“):
- **Fahrstil 0–100** aus dem 15-Sekunden-Verlauf von Geschwindigkeit und Akkuleistung,
  aus drei Teilen:
  - **sanft beschleunigt** – selten kräftig beschleunigt (hohe Antriebsleistung bei
    steigendem Tempo),
  - **gleichmäßig** – über 30 km/h schwankt das Tempo höchstens 5 km/h je 15 Sekunden,
  - **vorausschauend** – selten hart gebremst (mehr als 40 km/h weniger in 15 Sekunden;
    normales Anhalten an der Ampel zählt nicht).
- Je Fahrt in der Tabelle und in den Details (mit den drei Teilen), in den Temperatur- und
  Jahreszeitengruppen nach Strecke gewichtet.
- Der smart-eigene Eco-Score kommt über OVMS nicht an – das ist ein eigener Wert nach
  demselben Prinzip, nicht identisch mit der Anzeige im Auto.
- **Rückwirkend:** Für Fahrten der letzten 10 Tage aus der HA-Historie berechnet.

## 0.26.0 – 2026-10-22

Reichweitenanzeige gegen echte Kilometer (Reiter „Drive & Energy“):
- **Jede Fahrt merkt sich die Reichweitenanzeige des Autos** (OVMS) beim Losfahren und
  nach dem Abstellen, z. B. „80 → 50“.
- **„Reichweite stimmt“:** gefahrene km je km, um den die Anzeige sank. 25 km gefahren,
  Anzeige 30 km gesunken = 83 % – das Auto war zu optimistisch; über 100 % war es vorsichtig.
  Je Fahrt in der Tabelle und in den Details, in den Temperatur- und Jahreszeitengruppen als
  Mittel.
- **Rückwirkend:** Für Fahrten der letzten 10 Tage holt der Pilot die Reichweite einmal aus
  der HA-Historie.

## 0.25.2 – 2026-10-22

- **Kein falsches „Lädt unterwegs“ mehr:** Nach der Lidl-Ladung meldete OVMS stundenlang
  dieselbe Ladeleistung von 5,7 kW, obwohl „lädt“ längst auf „aus“ stand. Seit v0.25.1
  zeigte das Cockpit deshalb den ganzen 22.10. „Lädt unterwegs mit 5,7 kW“. Die Leistung
  zählt jetzt nur, wenn sie sich in den letzten 10 Minuten geändert hat und das Auto nicht
  ausdrücklich „lädt nicht“ meldet.
- **Keine Schein-Fremdladung:** Eine erkannte Fremdladung wird nur gespeichert, wenn
  wirklich Energie floss (OVMS „Energie dieser Ladung“ gestiegen oder SOC um mindestens
  2 % höher). Der falsche laufende Eintrag vom 22.10. wird verworfen, nicht gebucht.

## 0.25.1 – 2026-10-21

Fremdladen nach der ersten echten Ladung unterwegs (Lidl, 21.10., 16:01–16:27):
- **Fremdladung wird live erkannt:** OVMS meldete „lädt“ nur einmal um 16:01 und dann
  26 Minuten nicht mehr – der Wert galt als veraltet, die Ladung wurde nicht erkannt. Jetzt
  zählt auch die OVMS-Ladeleistung, die laufend kommt.
- **Kein „Ladung beendet“ mitten in der Ladung:** Um 16:14 meldete die Ersatz-Erkennung
  über den SOC-Sprung die Ladung als fertig (2,47 kWh), obwohl das Auto bis 16:27 weiterlud.
  Solange das Auto „lädt“ meldet, gibt es keine SOC-Sprung-Erkennung mehr; das Ende kommt
  erst 10 Minuten ohne Strom.
- **Energie aus dem Auto:** Die Menge kommt aus OVMS „Energie dieser Ladung“ (4,35 kWh in
  den Akku), daraus die Netzenergie mit dem Wirkungsgrad.
- **Im Cockpit sichtbar:** „Lädt unterwegs mit 9,6 kW · seit 16:01 · bisher 3,1 kWh in den
  Akku · 66 → 84 %“ – auch im Statussensor und damit auf der Dashboard-Karte.
- **Keine Fehlwarnungen unterwegs:** kein „Datenkonflikt“ (die Wallbox ist nicht beteiligt)
  und keine Warnung „HV-Kontaktor ohne Aktivität“ beim Laden unterwegs.
- **Vorklimatisierung:** Fehlende Blöcke startet der Pilot schon nach 10 statt 30 Sekunden
  nach – am 21.10. stand das Auto beim Hingehen kurz still.

## 0.25.0 – 2026-10-20

Realistische Verbrauchswerte (Reiter „Drive & Energy“), nach dem Hinweis vom 20.10.:
- **Strom, der noch im Akku ist, zählt nicht mehr als Verbrauch.** Der SOC-Ausgleich
  suchte einen Ladestand vom 1. Januar, den es nicht gab – also fiel er weg, und die 8 %,
  die seit dem 16.10. zusätzlich im Akku stecken, liefen als „verbraucht“ mit (daher
  20,4 kWh/100 km). Jetzt beginnt die Bilanz beim ersten bekannten Ladestand.
- **Vorklimatisierung extra:** Der Netzverbrauch gilt fürs Fahren; die Vorklimatisierung
  steht getrennt daneben. Auch die Kosten pro 100 km sind die fürs Fahren.
- **Fahrzeugverbrauch ganz vorn:** der Wert aus dem Auto (OVMS: verbraucht minus
  Rekuperation), darunter der Netzverbrauch mit Ladeverlust.
- **Ladeverlust stimmt:** Bisher stand dort −0,0 %, weil die OVMS-„Ladeleistung“ beim
  smart die Netzseite misst. Jetzt zählt die Energie, die laut OVMS wirklich in den Akku
  ging (`…_charge_energy`): am 20.10. 7,68 kWh für 8,99 kWh aus der Wallbox, also etwa
  15 %. Neuer OVMS-Eingang, wird automatisch übernommen.
- **Rückwirkend:** Die Bilanz rechnet aus den gespeicherten Daten immer neu. Die Energie
  in den Akku holt der Pilot für ältere Ladungen einmal aus der HA-Historie (soweit der
  Recorder die Tage noch hat).

## 0.24.1 – 2026-10-20

Vorklimatisierung bis zum Einsteigen:
- **Klima und Wallbox laufen bis 5 Minuten nach der Abfahrt** (vorher 2). Bei Abfahrt
  05:30 und 15 Minuten also 05:20–05:35.
- **Der Pilot startet fehlende 5-Minuten-Blöcke selbst nach.** Der smart klimatisiert nur
  in 5-Minuten-Blöcken; OVMS sollte bei 10/15 Minuten nachstarten, hat am 20.10. aber den
  dritten Block ausgelassen (Klima 05:18–05:28, beim Einsteigen 05:33 nur 15 °C). Meldet
  das Auto die Klima 30 Sekunden lang aus, obwohl noch mindestens 2 Minuten geplant sind,
  sendet der Pilot `homelink 1` für einen weiteren Block – höchstens 3-mal.
- **Die Wallbox bleibt bis zum geplanten Klima-Ende frei,** auch in den Lücken zwischen den
  Blöcken. Danach gilt wieder das Ladeziel.

## 0.24.0 – 2026-10-20

Ladepause statt Abbruch – wie am 20.10. besprochen:
- **Nimmt das Auto unter dem Ziel keinen Strom mehr** (z. B. Akku zu warm oder zu kalt),
  ist das eine **Ladepause**, kein Ende: Die Wallbox bleibt frei. Lädt das Auto wieder,
  geht es normal weiter bis zum Ziel.
- Nach **15 Minuten** ohne Strom weckt der Pilot **einmal** (erst OVMS, dann CP-Puls mit
  anschließend 5 Minuten Wartezeit). Bringt auch das nichts, bleibt die Wallbox frei, **bis
  du das Kabel ziehst** – auch über das Ladefenster und den Preisblock hinaus. Lädt das
  Auto später weiter, stoppt der Pilot beim Ziel.
- Push „Ladepause bei 60 % – Wallbox bleibt frei …“ und später „Lädt wieder“.
- Cockpit und Statussensor zeigen „Ladepause bei … %“.
- **Ziel 100 %:** Die Wallbox geht nur aus, wenn das Auto selbst aufgehört hat **und** der
  SOC bei mindestens 99 % steht. Hört es bei 60 % auf, ist das eine Pause.
- Eine Leistung, die vor dem Stopp absinkt, gilt nur dann als „voll geladen“, wenn der SOC
  nicht deutlich unter dem Ziel liegt.

## 0.23.3 – 2026-10-20

- **Wallbox bleibt während der Vorklimatisierung frei:** Am 20.10. wartete der Pilot nach
  der Freigabe 60 Sekunden auf Ladeleistung. Der Akku war voll, es kam keine, also schaltete
  er die Wallbox um 05:18:06 ab („Nachladen nicht gestartet“). Die Klimaanlage startete erst
  6 Sekunden später und heizte aus dem Akku. Jetzt hält der Pilot die Wallbox für die ganze
  Vorklimatisierung frei, egal ob und wann das Auto Strom zieht. Taktet die Heizung, gilt
  das auch nicht mehr als Ladeabbruch.

## 0.23.2 – 2026-10-19

- **Fahrten löschen:** In der aufgeklappten Fahrt (Reiter „Drive & Energy“) gibt es den
  Knopf „Fahrt löschen“ mit Rückfrage; auch als Dienst `ev_charging_pilot.delete_trip`.
- **Kein Unsinns-Verbrauch bei Rangierfahrten:** Fahrten unter 1 km zeigen keinen
  Verbrauch pro 100 km mehr – auch nicht die älteren vom 17.10. (0,06 km mit
  138 kWh/100 km, 0,14 km mit 86 kWh/100 km); sie werden beim Start korrigiert. Sie
  zählen außerdem nicht mehr in den Temperatur- und Jahreszeitengruppen.

## 0.23.1 – 2026-10-19

Temperaturen ehrlich – nach dem Vergleich mit der Wetterstation am 19.10.:
- **Eine Außentemperatur aus HA (Wetterstation) hat Vorrang vor dem Autosensor.** Das
  Auto zeigte 13,1 °C, die Station 7,4 °C: Der Autosensor lag schon während der Fahrt
  3–4 °C zu hoch, und das schlafende Auto wiederholte den Wert von 16:08 bis in die Nacht.
  Die Außentemperatur bestimmt die Dauer der Vorklimatisierung – mit 13,1 °C wären es
  10 statt 15 Minuten gewesen.
- **Ein Autowert, der sich 30 Minuten nicht ändert, gilt nicht mehr als aktuell**
  (Außen- und Innenraumtemperatur); dann wird z. B. die Wetter-Entität genommen.
- **„Stand …“ an der Innenraumtemperatur übersteht einen HA-Neustart:** HA setzt beim
  Neustart die Änderungszeit aller Werte neu; der Pilot merkt sich die echte selbst.

## 0.23.0 – 2026-10-19

Temperaturen im Cockpit:
- **Neue Plakette unter dem Akku:** „🌡 innen 21 °C · außen 8,3 °C“. Hat sich der
  Innenraumwert länger als 30 Minuten nicht geändert, steht dabei, seit wann
  („Stand 17:31“) – ein schlafendes Auto meldet seinen letzten Wert immer wieder
  (am 19.10. die ganze Nacht 23 °C bei tatsächlich 11 °C).
- **Ein Klick zeigt den Verlauf der letzten 24 Stunden:** Innenraum und außen, Zeiten mit
  laufender Klimaanlage grün hinterlegt. Abschnitte, in denen sich ein Wert über 30
  Minuten nicht ändert, sind gestrichelt – dort schläft das Auto und es gibt keine
  echten Messwerte.
- **Neuer OVMS-Eingang „Innenraumtemperatur“** (`…_cabin_temperature`), wird bei
  bestehenden Installationen automatisch übernommen.

## 0.22.5 – 2026-10-19

- **Vorklimatisierung endet nach der Abfahrt, nicht davor:** Sie endet jetzt 2 Minuten
  *nach* der geplanten Abfahrt statt 2 Minuten davor. Am 19.10. war sie um 05:28 vorbei,
  eingestiegen wurde um 05:33 – der Innenraum war von 23 auf 15 °C abgekühlt. Bei
  Abfahrt 05:30 und 10 Minuten läuft sie jetzt 05:22–05:32.
- **Eine laufende Vorklimatisierung wird nicht mehr abgebrochen,** wenn während des
  Heizens ein Wert veraltet (z. B. die Außentemperatur) und der Systemzustand auf
  „eingeschränkt“ fällt. Eine Sicherheitssperre stoppt sie weiterhin.

## 0.22.4 – 2026-10-19

Korrekturen nach der Vorklimatisierung am 19.10. (der neue Ablauf selbst lief richtig:
Klimabefehl erst nach der Wallbox-Bestätigung, Wallbox aus, sobald das Auto Klima aus
meldet):
- **Klima-Energie stimmt:** Sie kommt jetzt aus dem Wallbox-*Zähler* statt aus der
  angezeigten *Leistung*. Die Halo zeigte 5 kW, die Heizung zog laut Zähler nur etwa
  1,6 kW (einphasig, die Halo rechnet auf drei Phasen hoch). Gespeicherte Sitzungen werden
  beim Start korrigiert: Der Klima-Anteil ist nie größer als die Netzenergie.
- **Jede Ladung bekommt eine eigene Sitzungs-ID:** Die Klima-Sitzung übernahm die ID der
  Nachtladung, die Detailansicht zeigte dann die falsche Ladung. Doppelte IDs werden
  beim Start repariert.
- **Kein „Datenkonflikt“ mehr beim Heizen:** Das volle Auto zieht Strom, ohne zu laden –
  das ist während der Vorklimatisierung normal.

## 0.22.3 – 2026-10-19

- **Ladeziel 100 %: das Auto entscheidet, wann es voll ist.** Bei 100 % schaltet der Pilot
  nicht mehr bei 100 % in der Anzeige ab. Am 19.10. zeigte der smart 100 %, während der
  echte Ladestand erst bei etwa 93 % lag – das Ausgleichen der Zellen am Ende wurde
  abgeschnitten. Jetzt bleibt die Wallbox frei, bis das Auto die Ladung selbst beendet, und
  geht aus, sobald es **3 Minuten** keinen Strom mehr zieht. Zieht es zwischendurch wieder
  Strom (Ausgleichen), beginnen die 3 Minuten neu. Spätestens zur Abfahrt ist wie bisher
  Schluss.
- Ladeziele unter 100 % schalten unverändert beim Ziel-SOC ab.

## 0.22.2 – 2026-10-18

Cockpit-Beschriftungen ohne Überlappung:
- **Akku:** Liegen Mindest- und Ziel-SOC dicht beieinander (z. B. 85 und 100 %), steht
  „Ziel“ über dem Akku statt auf „min“; keine Beschriftung ragt mehr aus dem Bild.
- **Zeitleiste:** Klima, fertig, Abfahrt und jetzt weichen einander aus (andere Seite der
  Linie oder eine Zeile tiefer). Die Klima-Marke zeigt jetzt auch die Dauer.

## 0.22.1 – 2026-10-18

- **Fahrt sofort abgeschlossen, sobald du das Auto abschließt:** Wird das Auto nach
  dem Abstellen entriegelt und wieder verriegelt (Tür auf, aussteigen, abschließen), ist
  die Fahrt gleich fertig und steht im Panel – statt erst nach 10 Minuten. Am 18.10.
  wäre die Rückfahrt so 6 s statt 10 min nach dem Abstellen erschienen.
- Ein Stopp mit Abschließen ergibt damit zwei Fahrten. Ohne Abschließen (z. B. im Auto
  warten) und ohne Verriegelungsmeldung gilt weiter die Pause von 10 Minuten.
- Die Selbstverriegelung des smart während der Fahrt zählt nicht.
- **Neuer OVMS-Eingang „verriegelt“** (`lock.…_vehicle_lock`), wird bei bestehenden
  Installationen automatisch übernommen.

## 0.22.0 – 2026-10-18

Fahrt-Details mit Fahrtkurve (Reiter „Drive & Energy“):
- **Fahrt anklicken → Details:** Zeitraum, Dauer, Strecke, Ø-Geschwindigkeit, verbraucht,
  rekuperiert (mit Anteil), netto, Nebenverbraucher, kWh/100 km, SOC vorher/nachher,
  Außentemperatur und was die Fahrt zu Hause gekostet hat (Netto-Energie mit Ladeverlust
  zum durchschnittlichen Heimstrompreis).
- **Fahrtkurve:** oben die Geschwindigkeit, unten Antrieb (orange) und Rekuperation (grün)
  aus der Akkuleistung, dazu der SOC; beim Überfahren die Werte jedes Messpunkts.
- Jede Fahrt speichert ihren Verlauf jetzt selbst (alle 15 s, auch über einen Neustart).
  Für ältere Fahrten kommt die Kurve aus der HA-Historie.
- **Neuer OVMS-Eingang „Geschwindigkeit“** (`…_vehicle_speed`), wird bei bestehenden
  Installationen automatisch übernommen.

## 0.21.1 – 2026-10-18

- **Kurze WLAN-Aussetzer des Shelly sperren die Automatik nicht mehr:** War der Shelly
  eben noch erreichbar und die CP-Leitung geschlossen, gilt das bei einem Aussetzer noch
  3 Minuten weiter. Erst danach heißt es „Shelly (CP-Relais) nicht erreichbar“ mit Sperre
  und Push. Am 18.10. fiel der Shelly bei −80 dBm 30-mal für etwa eine Minute aus und
  löste zweimal „Systemzustand: Fehler“ aus.
- Keine Toleranz in den 10 Minuten nach einem CP-Puls und nicht bei offener CP-Leitung:
  Dann zählt nur ein frischer Wert. Ein CP-Puls wird während eines Aussetzers nie
  ausgelöst.

## 0.21.0 – 2026-10-18

Strom der Vorklimatisierung wird getrennt ausgewiesen:
- **Spalte „Klima“ in den Lade-Sessions** (Reiter „Hausstrom“) mit kWh und €, in den
  Details „davon Vorklimatisierung“, in der Monatskarte „Heimladen“ und im
  PDF-Monatsbericht.
- **So wird gerechnet:** Solange das Auto „Klimaanlage aktiv“ meldet, zählt der Teil
  der Wallbox-Leistung, der nicht in den Akku geht: Netzleistung − Akkuleistung ÷
  Lade-Wirkungsgrad (Einstellung, Standard 0,88). Der Ladeverlust bleibt so beim Laden.
  Kosten mit dem Preis der jeweiligen Viertelstunde (Tibber genau).
- **Neuer OVMS-Eingang „Akkuleistung“** (`…_battery_power`), wird bei bestehenden
  Installationen automatisch übernommen. Ohne ihn bleibt die Spalte leer.

## 0.20.2 – 2026-10-18

Klare Statuszeile – im Cockpit und als Sensor fürs eigene Dashboard:
- **Neuer Sensor `sensor.ev_pilot_status`:** derselbe Satz wie oben im Cockpit, mit
  `detail` und `tone` (ok/info/warn/bad) sowie `climate_start`, `climate_minutes`,
  `climate_phase` als Attribute. Damit braucht eine Dashboard-Karte keine eigene Logik.
- **Vorklimatisierung wird genannt:** „Vorklimatisierung um 15:53 für 5 min“ (mit
  Abfahrt, Außentemperatur und ob der Strom aus der Wallbox oder dem Akku kommt) und
  während sie läuft „Vorklimatisierung läuft“.
- **Kein „Lädt 06:00–15:54“ mehr nach dem Ladeblock:** Ist der Preisblock vorbei und
  schaltet nichts mehr ein, heißt es „Kein Laden mehr geplant – 88 %“.
- **`sensor.ev_pilot_next_charge_start`** zeigt keinen vergangenen Start mehr: nach dem
  letzten Ladeblock ist er leer, sonst der nächste Block bzw. Fensterstart.

## 0.20.1 – 2026-10-18

Vorklimatisierung nach dem ersten echten Test (18.10., 15:53, 5 min bei 8,7 °C):
- **Erst Netzstrom, dann Klima:** Der OVMS-Klimabefehl geht erst raus, wenn die Wallbox
  die Freigabe bestätigt hat (im Test nach 7 s). Bestätigt sie nicht innerhalb von 60 s,
  fällt die Vorklimatisierung aus – das Auto wird nicht geweckt, du bekommst eine Push.
- **Wallbox nur so lange wie die Klimaanlage:** Neuer OVMS-Eingang „Klimaanlage aktiv“
  (`…_hvac_active`, wird bei bestehenden Installationen automatisch übernommen). Meldet
  das Auto die Klimaanlage aus, gilt sofort wieder das Ladeziel. Im Test lief die Klima
  bis 15:58, die Wallbox lud aber bis 16:00 weiter auf 92 %.
- **Klimastart wird festgehalten:** Ändert sich die Außentemperatur während der
  Vorklimatisierung, wird kein zweiter Befehl gesendet; auch nicht nach einem Neustart.
- **Keine falsche HV-Warnung mehr:** „HV-Kontaktor geschaltet, ohne dass das Auto lud“
  kam, weil das Auto beim Ladestart bzw. für die Klimaanlage den Kontaktor schloss, bevor
  die Ladung als stabil galt. Start und Klima zählen jetzt als Aktivität.

## 0.20.0 – 2026-10-18

Ladekurve und Details je Ladung (Reiter „Hausstrom“):
- **Zeile anklicken → Details:** Zeitraum, Dauer, Grund, Wecken, Netz-kWh laut
  Wallbox-Zähler, kWh im Akku laut OVMS, Ladeverlust, Zählerstände, SOC vorher/nachher,
  Ø/max. Leistung, Kosten und Ø-Preis.
- **Ladekurve:** Wallbox-Leistung (Netz), Ladeleistung laut OVMS und SOC über die Zeit,
  mit Werten beim Überfahren jedes Messpunkts.
- **Kosten je Viertelstunde** mit dem jeweils gültigen Preis und die **Ereignisse** rund um
  die Ladung (Freigabe, Wecken, Start, Ende).
- Jede Ladung speichert ihren Verlauf jetzt selbst (ein Punkt pro Minute). Für ältere
  Ladungen kommt die Kurve aus der HA-Historie, solange der Recorder die Tage noch hat.

## 0.19.9 – 2026-10-18

Korrekturen nach der ersten echten Ladung (Nacht zum 18.10., 71 → 90 %, sauber bei 90 %
abgeschaltet – siehe `docs/pruefliste-erste-nacht.md`):
- **HV-Kontaktor-Wächter wirkt wieder:** Die OVMS-Integration liefert die *verbleibenden*
  Zyklen (Zähler fällt). Der Wächter zählt jetzt jede Änderung, egal in welche Richtung –
  „HV-Zyklen heute“ zeigt 1 statt −1, und die Warnungen „Zyklus ohne Laden/Fahren“ und
  „zu viele Zyklen am Tag“ können wieder auslösen.
- **Cockpit nach erreichtem Ziel:** Nach dem Preisblock stand noch „Lädt in der
  günstigsten Zeit 06:00–06:36“, obwohl das Auto schon 90 % hatte. Jetzt: „Ziel 90 %
  erreicht – Das Auto ruht bis zur Abfahrt“. Vergangene Blöcke werden nicht mehr genannt.
- **Vollständige Sitzungsenergie:** Der Halo-Zähler kommt per Cloud nur alle ~30 s. Die
  Sitzung beginnt jetzt beim Zählerstand der Freigabe und wartet nach dem Ende gut eine
  Minute auf die letzten Werte (auch über einen Neustart). Die erste Nacht hätte 3,43 statt
  3,31 kWh gezählt; Kosten und Wirkungsgrad stimmen damit.
- **Panel nach Update ohne Skriptfehler:** Das Panel wird als JavaScript-Modul geladen.
  Ein nach einem Update noch offener Tab meldete sonst „Identifier 'DOMAIN' has already
  been declared“.

## 0.19.8 – 2026-10-18

Texte und Doku aus dem Prüfbericht vom 18.10.:
- **Push-Nachrichten auf Deutsch statt Codes:** „Systemzustand: eingeschränkt
  (Ladestand veraltet)“ statt „System-Health DEGRADED (SOC_STALE)“. Die CP-Warnung nennt
  den Grund, und „Ladestart fehlgeschlagen – das Auto ließ sich nicht wecken“ ersetzt den
  Fachbegriff „Kaskade“.
- **PDF-Bericht:** Ort („Öffentlich“ statt „public“), Ergebnis („Start fehlgeschlagen“),
  Qualität („gut“/„geschätzt“) und die Gründe stehen auf Deutsch. Die Fußzeile nennt den
  Fahrzeugnamen.
- **Panel:** „Manuell: bis Kabel ab“ statt „Override: until_unplugged“, Qualität und
  Temperaturbereiche auf Deutsch, „Einmalige Abfahrt löschen“ statt „One-Shot löschen“.
- **Einheitliche Begriffe:** „Einmalige Abfahrt“ (statt „Heute Nacht“/„One-Shot“),
  „Probebetrieb (Dry-Run)“, „Preis-Entität“. Der Sensor `executor_state` heißt jetzt
  „Ladeablauf“, weil „Ladezustand“ den SOC meint.
- **Fehlermeldungen der Dienste** auf Deutsch; Mailtext „(unterwegs bezahlt, nicht Teil
  des Hausstroms)“.
- Der Dienst „Jetzt laden“ hat keinen vorbelegten Modus mehr und nutzt damit wie der Knopf
  das manuelle Ladeziel.
- Der Einstellungsdialog erlaubt eine Akkukapazität bis 150 kWh, wie das Panel.
- **Doku:** README (OVMS-Befehle, Taper 80 %, Entitäten, alle 26 Dienste, Mail,
  Ladestrom, Test-Center), ROADMAP bis v0.19, Projektnotizen, Prüfbericht mit Status.

## 0.19.7 – 2026-10-18

Korrekturen aus dem Prüfbericht vom 18.10., Stufe 3 (Randfälle):
- **Halo-Status „Unavailable“ wird erkannt.** Der Pilot hielt den echten Halo-Status
  „Unavailable“ (Ladepunkt gesperrt) für das HA-interne „nicht verfügbar“. Ohne
  OVMS-Stecker gilt „kein Kabel“ der gesperrten Halo jetzt als unbekannt, und der
  Ladeplan startet trotzdem.
- **Kein Weckversuch bei unbekanntem Kabel**, z. B. direkt nach einem Neustart.
- **Eingefrorener Leistungswert:** Meldet die Wallbox-Cloud keine neuen Werte mehr, gilt
  das nicht mehr als „Strom fließt“, und ein Abbruch wird erkannt.
- **Keine Endlosschleife**, wenn die Wallbox „aus“ nie bestätigt. Neuer Versuch nach
  30 Minuten.
- **Preise:** €/MWh ohne Einheit werden erkannt, Zeitstempel als Text gelesen. Bei
  gleichem Preis startet die Ladung so spät wie möglich statt sofort.
- **Statistik:** Wochenrückblick und Monat zählen abgebrochene Ladungen gleich.
  Erkannte Fremdladungen markieren den Monat als „geschätzt“. Ein unplausibler
  Ladeverlust wird verworfen.
- **Mail:** verständlichere Fehlermeldungen (z. B. „Mailserver meldet 552 …“). Das
  Passwort erscheint nie in Logs.
- **Datenschutz:** Mail-Adressen erscheinen nicht mehr im Ereignisprotokoll, und
  Nicht-Admins sehen sie in den Einstellungen nur maskiert.
- Ein absichtlich geleertes OVMS-Stecker-Feld wird beim Start nicht wieder befüllt.
  Eine Fehler-Push zum Bericht ersetzt nicht mehr die „Bericht fertig“-Push. Der
  Foto-Upload blockiert HA nicht mehr.

## 0.19.6 – 2026-10-18

Korrekturen aus dem Prüfbericht vom 18.10., Panel (Stufe 2 und 3):
- **U1 – Meldungen bleiben sichtbar:** „Gespeichert“, „Preis gespeichert“ und
  Fehlermeldungen verschwanden beim nächsten Neuzeichnen sofort wieder.
- **U2 – Änderungen erscheinen sofort:** Nach einer Auswahl in einem Dropdown (Filter,
  Ladestrom, Vorklimatisierung) blieb die Ansicht stehen, bis man woanders hinklickte.
- **U3 – „Speichern“ in den Einstellungen klappt mit einem Klick.** Ein Klick auf den
  bereits offenen Reiter verwirft keine ungespeicherten Änderungen mehr. Die Leiste
  verschwindet sofort nach dem Speichern. Ein geleertes Zahlenfeld wird nicht als 0
  gespeichert, und eine unveränderte Uhrzeit gilt nicht mehr als Änderung.
- **U4 – PDF-Berichte öffnen sich über einen signierten Link**, auch in der iPhone-App.
  Ist ein Pop-up blockiert, erscheint ein Link zum Antippen.
- **U5 – „Ergänzen“ bei Fremdladungen:** Ein leeres Kostenfeld bedeutet „unverändert“
  statt 0 €, und Ladestand, Kilometerstand und Preis der Erkennung bleiben erhalten.
  „Foto entfernen“ meldet einen Fehler, wenn es nicht geklappt hat.
- Bei einem fehlgeschlagenen Start steht im Cockpit der Hinweis, was zu prüfen ist.
  Fehlercodes erscheinen als deutscher Text („Ladestart fehlgeschlagen“).
- Die Zeitleiste bleibt lesbar, wenn das nächste Ladefenster Tage entfernt ist.
- Kleinigkeiten: Die Replay-Auswahl springt nicht mehr zurück, das Systemtest-Ergebnis
  bleibt nach anderen Aktionen sichtbar, Datumsangaben stimmen auch in anderen
  Zeitzonen, und Jahr/Monat sind beim Wiederkommen aktuell.

## 0.19.5 – 2026-10-18

Korrekturen aus dem Prüfbericht vom 18.10., Stufe 2 (Statistik und HA):
- **S1 – Fremdladungen bekommen das lokale Datum.** Eine Ladung bis 00:30 Uhr am 1.
  landete bisher im Vortag bzw. Vormonat.
- **S2 – zusammengefasste Fahrten verlieren keine Energie mehr**, wenn OVMS seine Zähler
  pro Fahrt zurücksetzt.
- **S3 – Kilometer bleiben erhalten**, wenn HA während einer Fahrt neu startet, und die
  letzten Meter nach dem Abschalten zählen mit.
- **S4 – der Monatsbericht wartet auf eine noch laufende Nachtladung**, holt einen
  verpassten Bericht nach (HA um 06:00 am 1. aus) und meldet Fehler per Push, statt still
  auszufallen.
- **S5 – seltene manuelle Kilometerstände** werden anteilig auf die Monate verteilt, statt
  einem Monat die ganze Lücke zuzuschlagen.
- **S6 – PDF:** Eine Ladung über das Monatsende zählt in der Tabelle mit ihrem Monatsanteil
  und passt damit zur Monatssumme.
- **S7 – keine falsche Fremdladung**, wenn der Ladestand springt, während das Auto zu Hause
  eingesteckt ist, oder wenn der Wallbox-Zähler hängt.
- **S8 – €/100 km** rechnet mit demselben Ladestand-Ausgleich wie kWh/100 km.
- **H3 – kleinere Datenbank:** Das Attribut `updated_at` wird nicht mehr bei jedem Poll
  aufgezeichnet.
- **H4 – sauberes Aufräumen:** Schlägt der Start der Integration fehl, bleibt keine
  verwaiste Instanz zurück. Nach dem Entladen handelt die alte Instanz nicht mehr.
- **H5 – kein ERROR mehr im Log** beim ersten Speichern der Einstellungen nach einem
  HA-Start.
- **H6 – Admin-Rechte:** Shelly konfigurieren, Bericht mailen, Export und Replay sind
  Admins vorbehalten. Automationen dürfen weiterhin.

## 0.19.4 – 2026-10-18

Korrekturen aus dem Prüfbericht vom 18.10., Stufe 2 (Lade-Kern und Preise):
- **K9 – eine Unterbrechung ist kein „Auto fertig“:** Meldet das Auto „lädt nicht“ weit
  unter dem Ziel (z. B. FI-Auslösung, Wallbox-Störung), gilt das jetzt als Abbruch mit
  einem Neustartversuch und einer Meldung. Als eigenes Ladeende zählt es nur nahe voll
  oder nahe am Ziel. Nach einem Ladeende wird ein neuer Wunsch wie „Jetzt laden“ wieder
  bedient.
- **K11 – Automatik aus:** Endet „Jetzt laden“ (Ziel erreicht, Zeit abgelaufen), wird die
  Wallbox trotzdem gesperrt. Vorher lud das Auto bis 100 % weiter.
- **K12 – Lernen** rechnet mit der echten Intervalllänge statt fest mit 15 Minuten.
- **K13 – Außentemperatur:** Die letzte Temperatur des schlafenden Autos dient als letzte
  Rückfallquelle, statt nachts „Systemzustand eingeschränkt“ auszulösen.
- **P1 – zwei Ladeblöcke:** Die Suche findet jetzt immer die günstigste Kombination
  (vorher teils bis doppelt so teuer) und braucht Millisekunden statt rund einer Sekunde
  pro Takt.
- **P2 – Cent oder Euro** wird einmal pro Preisliste entschieden (Einheit, Feldname, sonst
  typischer Wert). Günstige Preise unter 5 ct und negative Preise werden nicht mehr als
  Euro gelesen. Bei der Preiseingabe wird „4 ct“ jetzt verstanden.
- **P3 – Lücken in Preislisten** bleiben Lücken, statt mit einem erfundenen Preis
  aufgefüllt zu werden.
- **P4 – unerwartete Fehler beim Tibber-Abruf** (z. B. Zeitüberschreitung) werden jetzt
  wiederholt und gemeldet.
- **P5 – Wechsel des Preisrasters** (15 Minuten ↔ Stunde): Alte Werte bleiben nicht
  mehr tagelang stehen.
- Halbstündliche Preislisten werden erkannt.

## 0.19.3 – 2026-10-18

Korrekturen aus dem Prüfbericht vom 18.10., Stufe 1 (HA):
- **H1 – Monatswechsel in der Langzeitstatistik:** Die Monats- und Jahres-Sensoren
  (Energie, Fremdenergie, Strecke, Kosten) wechselten den Rücksetzzeitpunkt nach der Uhr,
  den Wert aber erst bis zu 60 s später. HA verbuchte dadurch bei jedem Monatswechsel den
  Vormonat als negativen Betrag in der Langzeitstatistik und im Energie-Dashboard. Jetzt
  wechseln Werte und Rücksetzzeitpunkt im selben Takt.
- **H2 – Zeitlimit für Befehle an Wallbox und Auto:** Hängt ein Cloud-Aufruf (Halo,
  OVMS), wird er nach 30 s abgebrochen und gemeldet („keine Antwort nach 30 s“). Vorher
  konnte er die Steuerung (Zielabschaltung, Abbrucherkennung) blockieren.

## 0.19.2 – 2026-10-18

Korrekturen aus dem Prüfbericht vom 18.10., Stufe 1 (Lade-Kern):
- **K2 – kein Wecken nach einem Neustart, wenn das Auto schon fertig geladen hat.** Bisher
  hielt der Pilot nach einem HA-Neustart „Wallbox an, kein Strom“ für einen neuen
  Ladestart und weckte das Auto per OVMS und CP-Puls. Jetzt merkt er sich, dass das Auto
  in diesem Fenster fertig ist.
- **K3 – nach einem fehlgeschlagenen Start wird die Wallbox gesperrt.** Vorher blieb sie
  an, und das Auto hätte später unkontrolliert ohne Zielabschaltung geladen.
- **K4 – kein zweiter Weckversuch durch die Vorklimatisierung.** Die Vorklimatisierung
  weckt das Auto ohnehin über den OVMS-Befehl. Das Wecken durch die Wallbox läuft jetzt
  nur noch einmal pro Fenster.
- **K5 – ein Neustart nach einem fehlgeschlagenen Start zählt nicht als zweiter
  Fehlschlag.** Keine doppelte Push-Nachricht, keine Sicherheitssperre.
- **K6 – ein CP-Puls beendet „Jetzt laden“ und den Ladetest nicht mehr**, auch wenn die
  Wallbox während des Pulses kurz „kein Fahrzeug“ meldet.
- **K8 – jede Ladung ist eine eigene Sitzung.** Hat das Auto selbst fertig geladen, wird
  die Sitzung geschlossen. Mehrere Nächte verschmelzen nicht mehr.
- **K10 – keine Phantom-Sitzungen mehr**, wenn kurz nach dem Einschalten gestoppt wird,
  z. B. am Ende des Ladetests.

## 0.19.1 – 2026-10-18

Erste Korrekturen aus dem Prüfbericht vom 18.10. (Stufe 1):
- **K1 – Ladestand gilt nach dem Laden nicht mehr als „veraltet“:** Die Wallbox meldet ihre
  letzte Leistung oft ein paar Minuten nach der letzten Ladestand-Meldung des Autos. Das
  machte den Ladestand nach jeder Ladung „veraltet“. Folgen waren „System eingeschränkt“,
  eine nächtliche Push und eine blockierte Vorklimatisierung. Laden zählt jetzt erst als
  neue Aktivität, wenn es mehr als 15 Minuten nach der letzten Meldung weiterlief.
- **K7 – Ziel der einmaligen Abfahrt wird eingehalten:** Bisher lud sie über ihr eigenes
  Ziel hinaus, z. B. bis ~95 % statt 70 %. Sie stoppt jetzt wie ein Wochenplan am Ziel.

## 0.19.0 – 2026-10-18

- **Mehr Preis-Sensoren werden verstanden.** Bei der Preisquelle „Preis-Entität“ liest
  der Pilot jetzt zusätzlich:
  - Paare `[[Zeitstempel, Preis], …]` unter beliebigem Namen (z. B. `daten`), mit
    Zeitstempeln in Sekunden oder Millisekunden
  - ENTSO-e (`prices_today` / `prices_tomorrow` mit `time` / `price`)
  - weitere Feldnamen (`time`, `from`, `till`, `marketprice` …)
  - Preise in €/MWh, erkannt an der Einheit
  - als letzte Möglichkeit jede Liste, aus der sich Preise lesen lassen
- **Neu: „Preisquelle prüfen“** im Einstellungen-Reiter → Strompreis. Ein Klick zeigt, ob
  die gewählte Quelle eine brauchbare Preisliste liefert, z. B. „192 Preise bis
  Mo., 19.10., 00:00 · 15-Minuten-Raster · 0,386–0,498 €/kWh · am günstigsten
  So., 18.10., 06:00“. Das geht auch vor dem Speichern. Liefert eine Entität nur den
  aktuellen Preis, erklärt der Pilot, warum er damit keine günstigen Zeiten planen kann.

## 0.18.0 – 2026-10-17

- **Neu: Monatsbericht per E-Mail.** Am 1. des Monats geht der PDF-Bericht des Vormonats an
  bis zu zwei Empfänger. Der Betreff nennt schon das Wichtigste, z. B. „Smarty –
  Ladebericht September 2026: 40,2 kWh = 16,48 €“. Im Mailtext stehen die zu Hause
  geladenen kWh, die Kosten mit Ø-Preis, Fremdladungen und gefahrene Kilometer.
- **Einrichtung im Einstellungen-Reiter → „Monatsbericht per E-Mail“:** Anbieter wählen
  (Gmail, GMX, web.de, T-Online, iCloud, Outlook oder eigener Server), Benutzername,
  Passwort und Empfänger eintragen. Bei Gmail und iCloud wird ein **App-Passwort**
  benötigt. Das Passwort wird nie zurück ins Panel geschickt; ein leeres Feld behält das
  gespeicherte.
- **Betrag zusätzlich per Push:** Weitere Handys (z. B. `notify.mobile_app_…`) bekommen am
  1. die kWh und den Betrag des Vormonats.
- **Test-Center:** neue Karte „Monatsbericht per E-Mail“ mit „Test-Mail senden“. Sie zeigt
  das Ergebnis oder einen verständlichen Fehler, z. B. „Anmeldung abgelehnt – App-Passwort
  verwenden“. Schlägt der automatische Versand fehl, kommt eine Push-Nachricht.
- Neuer Dienst `ev_charging_pilot.send_report_mail` (year, month, test).
- Mail-Zugangsdaten und Empfänger werden in der Diagnose-Datei geschwärzt.

## 0.17.3 – 2026-10-17

- **Panel startet immer im Cockpit:** Bisher merkte sich das Panel den zuletzt offenen
  Reiter dauerhaft im Browser. Wer z. B. im Ladeplan war, eine andere HA-Seite öffnete und
  zurückkam, landete wieder im Ladeplan. Jetzt beginnt jeder Besuch im Cockpit. Nur wenn
  in den Einstellungen noch ungespeicherte Änderungen offen sind, bleibt dieser Reiter
  geöffnet, damit nichts verloren geht.

## 0.17.2 – 2026-10-17

- **Test-Center im Diagnose-Reiter:** Systemtest, Ladetest und Push-Test der Preisabfrage
  stehen jetzt gemeinsam am Ende des Reiters in einem einklappbaren Bereich
  „Test-Center“. Er ist standardmäßig zugeklappt und bleibt offen, solange du ihn nutzt.
  Läuft gerade ein Ladetest oder wartet ein Push-Test auf Antwort, öffnet er sich von
  selbst.

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
