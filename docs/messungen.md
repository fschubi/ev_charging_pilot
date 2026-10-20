# Messergebnisse Phase 0

Hier landen die Ergebnisse aus [`phase0/README.md`](../phase0/README.md).
Jede Zeile nennt Datum, Wert und welchen Default sie ersetzt.

| # | Datum | Ergebnis | Ersetzt Default |
| --- | --- | --- | --- |
| M1 | 2026-10-18 | Halo-Leistung/Zähler alle 30 s (Cloud); stabil beim 1. Leistungswert 30 s nach Bestätigung | `stable_samples`, `charging_stable_min_s`, `max_age_s.halo_power` |
| M1 | 2026-10-19 | bestätigt: stabil 30 s nach Bestätigung (02:30:15 → 02:30:45) | – |
| M2 | 2026-10-18 | Freigabe bestätigt nach 10 s, Abschaltung nach 5 s (14 A) | `confirm_timeout_s`, `min_switch_interval_s` |
| M2 | 2026-10-19 | Freigabe 11 s, Abschaltung 5 s. **Ladestrom 14 → 12 A** übernahm die Halo erst nach dem zweiten Setzen (02:30:04, 02:32:04 → 02:33:05), die ersten 3 min liefen mit 14 A | Wiederholung `CURRENT_SET` |
| M3 | 2026-10-19 | offen: Pilot schaltete bei Anzeige-SOC 100 % ab (03:34:57), das Auto beendete nicht selbst; Halo-Status „Charging“ bis zur Abschaltung, danach „Unavailable“ | `finished_statuses` |
| M3 | 2026-10-20 | **Auto beendet selbst** (v0.22.3): Anzeige 100 % um 03:42:23 (real 94,5 %), weitergeladen mit ~5,5 kW bis 03:50:31 (real 96,2 %); Halo-Status dann **„SuspendedEV“**, OVMS „lädt nicht“ 03:51:28; Wallbox aus 3 min später | `finished_statuses` = SuspendedEV |
| M4 | | | `cp_mask_grace_s` |
| M5 | | | – |
| M6 | | | RFID-Variante |
| M7 | | | RFID-Variante |
| M8 | 2026-10-18 | Auto lud ohne Wecken: Halo „Charging“ 10 s, OVMS „lädt“ 16 s nach Freigabe (SOC 71 %, 12 °C Akku) | `start_detection_wait_s` |
| M8 | 2026-10-17 | Testladung: wach 16 s nach Freigabe, kein Wecken | – |
| M8 | 2026-10-19 | wach/lädt 17 s nach Freigabe nach 7 h Schlaf (SOC 58 %), kein Wecken – dritter Start in Folge ohne Weckkette | `start_detection_wait_s` |
| M8 | 2026-10-20 | wach 16 s nach Freigabe (SOC 55 %), kein Wecken – vierter Start in Folge | – |

## Ladekurve und Energie (Feld)

| Datum | Ergebnis | Bedeutung |
| --- | --- | --- |
| 2026-10-19 | 58 → 100 % (Anzeige) in 64 min, 7,92 kWh aus dem Netz = **0,189 kWh je %**, Ø 7,4 kW, Spitze 9,0 kW (14 A), danach 7,8 kW (12 A) | Lernmodell / Prognose |
| 2026-10-19 | Leistung sinkt ab ~85–89 % Anzeige-SOC auf 6,4–7,0 kW | Restdauer oberhalb 85 % |
| 2026-10-19 | Anzeige-SOC 100 % bei `real_soc` ≈ 93 % (91,3 % um 03:28) – die Anzeige läuft oben schneller | Ziel-SOC-Abschaltung |
| 2026-10-19 | OVMS `charger_power` ≈ Halo-Leistung (7,91 vs. 7,92 kWh): misst die Netzseite, nicht den Akku – Ladeverlust daraus nicht bestimmbar | Eingang `ovms_charge_power` |
| 2026-10-19 | Vorklimatisierung bei vollem Akku: Halo-Leistung 5,0–5,3 kW, Zähler +0,10 kWh in 5 min (≈ 1,6 kW), Akku ≈ 0 kW – Halo-Leistung bei einphasiger Last ×3 überhöht | Klima-Energie aus dem Zähler |
| 2026-10-19 | Halo bestätigt Freigabe für Klima nach 5 s (Vortag 7 s) | `CLIMATE_CONFIRM_TIMEOUT` 60 s reicht |
| 2026-10-19 | OVMS-Außentemperatur 13,2–13,8 °C während der Fahrt, Wetterstation zur selben Zeit 9,5–10,1 °C (+3–4 °C); schlafend eingefroren (13,1 °C ab 16:08) | Quelle Außentemperatur |
| 2026-10-20 | 55 → 100 % (Anzeige) in 79 min, 8,99 kWh = 0,20 kWh je % inkl. Nachladen nach Anzeige-100 % (~0,7 kWh), max. 7,9 kW (12 A), ab ~90 % ~6 kW | Lernmodell / Prognose |
| 2026-10-20 | Ladeverlust: OVMS `charge_energy` 7,68 kWh in den Akku bei 8,99 kWh Halo-Zähler → ~14,6 % | `charge_efficiency` (0,88 → ~0,85) |
| 2026-10-20 | Fahrzeugverbrauch 16.–20.10.: (18,98 − 1,79) kWh / 104 km = 16,5 kWh/100 km bei 5–13 °C | Plausibilität |
