# Auswertung der ersten zwei Wochen (15.–31.10.2026)

Stand 31.10.2026, v0.27.32. Quellen: Sitzungen, Ereignisprotokoll (380 Einträge ab 15.10.),
HA-Systemlog, Monatsstatistik. Der Recorder hält Rohdaten nur 10 Tage – Woche 1 ist nur
über die gespeicherten Sitzungen (15-min-Energieintervalle) auswertbar.

## Überblick Oktober

499 km, 29 Fahrten, 20 Sitzungen, **0 Fehlstarts**, nie geweckt werden müssen (OVMS/CP-
Wakeup in keiner Sitzung). 84,8 kWh aus dem Netz (4,9 kWh fremd, Lidl), 17,6 kWh/100 km ab
Netz, 14,6 kWh/100 km im Auto, 34,08 € (7,07 €/100 km), Ladeverlust gesamt 12,3 %.

## Ladeverluste nach Ladeleistung

Verlust = (Halo-Zähler − OVMS `charge_energy`) / Halo-Zähler.

| Datum | SOC | Netz kWh | Akku kWh | Ø kW | Verlust |
| --- | --- | ---: | ---: | ---: | ---: |
| 19.10. | 58 → 100 | 7,92 | 6,84 | 7,4 | 13,6 % |
| 20.10. | 55 → 100 | 8,99 | 7,69 | 6,8 | 14,5 % |
| 21.10. | 51 → 100 | 9,72 | 8,34 | 7,2 | 14,2 % |
| 23.10. | 27 → 55 | 4,58 | 4,03 | 10,4 | 12,0 % |
| 24.10. | 52 → 76 | 4,40 | 3,92 | 10,4 | 11,0 % |
| 26.10. | 78 → 95 | 3,17 | 2,70 | 7,7 | 14,7 % |
| 27.10. | 44 → 95 | 9,10 | 8,07 | 9,7 | 11,3 % |
| 28.10. | 54 → 79 | 4,98 | 4,38 | 9,8 | 12,1 % |
| 29.10. | 37 → 95 | 10,19 | 9,04 | 10,1 | 11,3 % |
| 30.10. | 42 → 95 | 9,43 | 8,39 | 9,9 | 11,0 % |

- **12 A (~7,7 kW, Woche 1): 14,2 %** (29,8 kWh Netz). **16 A (~10,4 kW, ab 23.10.): 11,4 %**
  (42,7 kWh Netz). Woche 1 gesamt 13,2 %, Woche 2 11,6 %.
- Ein Teil des Unterschieds ist das Ladeende: In Woche 1 lud das Auto auf Anzeige 100 % und
  danach selbst mit ~5,5 kW weiter bis zum Balancing (M3); ab 26.10. ist das Ziel 95 %.
  Kurze Ladungen haben anteilig mehr Anlauf/Auslauf (26.10.: 17 % SOC, 14,7 %).
- 18.10. (6,6 %) ausgelassen: kurze Einmalladung, Werte unplausibel niedrig.
- Ersparnis 16 A gegenüber 12 A: ~0,28 kWh je 10 kWh, also ~0,09 € pro Nachtladung.
- Offen für eine saubere Trennung: eine Ladung mit 16 A auf 100 % oder mit 12 A auf 95 %.

## Fehler, die im Feld auftraten und behoben sind

- Klima: Wallbox erst nach Bestätigung, Halo-Bestätigung vor `CLIMATE_START` (v0.19.10–0.20.1),
  Nachstart ausgelassener 5-min-Blöcke, Ende nach Abfahrt + 5 min.
- Ladeende bei 100 %: Auto beendet selbst, Wallbox 3 min später aus (v0.22.3); Ladepause statt
  Abbruch (v0.24.0).
- Falsche „Lädt unterwegs“-Meldung durch eingefrorene OVMS-Leistung (v0.25.2).
- Reichweite pro Fahrt: Klima-Delle und Sprung nach Ausschalten (v0.27.1), Parkwert vor der
  Vorklimatisierung (v0.27.29).
- Prüfbericht 25.10. (v0.27.2–0.27.27), Zeitachse „NaN“ (v0.27.28).
- Schlafend eingesteckter smart nicht erkannt (27.10.) → Steckprobe (v0.27.30). **Seitdem
  zweimal im Einsatz und beide Male erfolgreich** (28.10. 17:39, 30.10. 15:02 „Kabel gesteckt
  (Steckprobe)“) – das Problem ist also kein Einzelfall.
- Nachtladung 28.10. ausgefallen durch Dauer-„Laden stoppen“ (v0.27.31); Sicherheitsfreigabe
  2 h vor Abfahrt (v0.27.32, im Feld noch nicht ausgelöst).

## Offen / zu beobachten

1. **Shelly-WLAN:** CP-Relais nicht erreichbar 16.10. (mehrfach), 18.10. (2×), 31.10.
   01:22–03:05; dazu `aioshelly` „Invalid Message“ im HA-Log. Sperrt nur den CP-Wakeup
   (v0.27.5), ist aber der einzige wiederkehrende Fehler → WLAN am Shelly verbessern.
2. **Charge-Amps-Cloud:** API-Timeouts (DNS) am 30.10. 06:08 (7×) – ohne Folgen, aber die Halo
   ist nur per Cloud steuerbar. Die Sicherheitsfreigabe hilft nur, wenn der Schaltbefehl
   ankommt.
3. **Klima-Energie** ungenau, wenn das Auto parallel nachlädt (27.10.: 0,03 kWh; 21.10.: Akku
   0,43 > Netz 0,15 kWh). Aufteilung Netz/Akku/Klima bei Klimasitzungen prüfen.
4. Sicherheitsfreigabe (v0.27.32) im Feld beobachten, sobald sie greift.
5. OVMS-Verbrauchszähler gegen SOC (26.10.: 11,4 statt ~16 kWh/100 km) weiter vergleichen.
6. `HV_CYCLE_WITHOUT_ACTIVITY` 21.10. und 23.10. (2×): Auto wach ohne Laden/Fahren – vermutlich
   App/Türen; beobachten.
