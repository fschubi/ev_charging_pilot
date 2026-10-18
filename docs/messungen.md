# Messergebnisse Phase 0

Hier landen die Ergebnisse aus [`phase0/README.md`](../phase0/README.md).
Jede Zeile nennt Datum, Wert und welchen Default sie ersetzt.

| # | Datum | Ergebnis | Ersetzt Default |
| --- | --- | --- | --- |
| M1 | 2026-10-18 | Halo-Leistung/Zähler alle 30 s (Cloud); stabil beim 1. Leistungswert 30 s nach Bestätigung | `stable_samples`, `charging_stable_min_s`, `max_age_s.halo_power` |
| M2 | 2026-10-18 | Freigabe bestätigt nach 10 s, Abschaltung nach 5 s (14 A) | `confirm_timeout_s`, `min_switch_interval_s` |
| M3 | | | `finished_statuses` |
| M4 | | | `cp_mask_grace_s` |
| M5 | | | – |
| M6 | | | RFID-Variante |
| M7 | | | RFID-Variante |
| M8 | 2026-10-18 | Auto lud ohne Wecken: Halo „Charging“ 10 s, OVMS „lädt“ 16 s nach Freigabe (SOC 71 %, 12 °C Akku) | `start_detection_wait_s` |
