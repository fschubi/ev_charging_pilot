# Phase 0 – einfache Automation und Messphase

Vor der Integration wird gemessen, nicht geraten (Masterplan Grundsatz 11).
Phase 0 ersetzt evcc durch eine minimale Zeitautomation und sammelt die
Werte, von denen die Zeitkonstanten der Integration abhängen.

## Einrichten

1. evcc so abschalten, dass es die Halo nicht mehr schaltet. Halo-internen
   Zeitplan ausschalten.
2. [`smart_eq_phase0.yaml`](smart_eq_phase0.yaml) als Package einbinden,
   Entity-IDs prüfen, `SHELLY_IP` ersetzen.
3. `input_boolean.smart_eq_p0_enabled` einschalten.
4. Halo-Zähler im Energy Dashboard als Einzelverbraucher eintragen.

## Messprotokoll

Die Ergebnisse kommen in [`docs/messungen.md`](../docs/messungen.md); sie
ersetzen danach die vorläufigen Defaults im Options-Flow.

| # | Messung | Wofür (Masterplan) | Wie |
| --- | --- | --- | --- |
| M1 | Update-Intervall Halo-Leistung und -Status | §6.2 N/Mindestdauer, §7.3 `halo_power` | Logbuch „Smart EQ Messung“, Abstände der Leistungswerte während einer Ladung |
| M2 | Latenz Schaltbefehl → Zustand | `confirm_timeout_s`, `min_switch_interval_s` | Halo manuell schalten, Zeit bis Switch- und Statuswechsel |
| M3 | Alle Werte von `status_raw` | §6.3 Ladeende, `finished_statuses` | Statushistorie über mehrere Nächte inkl. „voll“ |
| M4 | Halo während des CP-Pulses | §3.4 Maskierung, `cp_mask_grace_s` | Script `smart_eq_cp_pulse_test` bei gestecktem Auto, Logbuch auswerten |
| M5 | Lädt die Halo nach dem Puls ohne neue Autorisierung weiter? Kabellock? | §3.4 | wie M4, mit laufender Ladung |
| M6 | RFID bei deaktiviertem Connector | §5.4 Variante A/B/C | Halo aus, Karte vorhalten, Status beobachten |
| M7 | Startet der Smart beim Einstecken selbst? | §5.4 Variante B | Halo an, Auto anstecken |
| M8 | Wie lange bis der schlafende Smart Leistung zieht | `start_detection_wait_s` | Halo nachts einschalten, Zeit bis Leistung > 300 W |

## Checkliste CP-Failsafe (§3.6)

Erst wenn alles abgehakt ist, darf im Options-Flow
`cp_failsafe_verified` gesetzt werden – vorher bleibt der CP-Wakeup gesperrt.

- [ ] `ON` entspricht elektrisch CP geschlossen
- [ ] `OFF` entspricht elektrisch CP unterbrochen
- [ ] `initial_state = on`
- [ ] `auto_on = true`, `auto_on_delay = 10`
- [ ] Puls per `toggle_after` getestet
- [ ] Auto-On ohne HA real getestet (HA während Puls stoppen)
- [ ] CP nach Shelly-Neustart geschlossen
- [ ] CP nach HA-Neustart geschlossen
- [ ] Halo-Verhalten während des Pulses dokumentiert (M4/M5)
- [ ] Elektrofachkraft hat Verdrahtung abgenommen
