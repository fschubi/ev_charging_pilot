# Entwickler-Changelog (vollständige Historie)

- **2026-10-25 – v0.27.16 SOC-Ausreißer.** `Engine._track_soc_jumps`: GOOD-SOC-Sprung >
  `SOC_JUMP_PCT` (5) → `_confirmed` hält die Ziel-Abschaltung `TARGET_CONFIRM` (3 min) zurück;
  `_topping_up` (gespeichert): nach `fresh_below` kein „held“ mehr bis Ziel erreicht. Tests mit
  synthetischen SOC-Sprüngen aufs Ziel laufen jetzt über einen Zwischenschritt. Prüfbericht M3.
- **2026-10-25 – v0.27.15 Panel-Details.** `_call` behält `check`, `tempHistory/tempAt`,
  `sessionDetail`, `tripDetail` im Cache; neues `_resetCache()` (Reiter, Monat, Rückkehr)
  schließt `_sessionOpen/_tripOpen/_tempOpen` mit. Prüfbericht M11.
- **2026-10-25 – v0.27.14 Klima ohne Kabel.** `summary._describe`: Zweig „Vorklimatisierung
  läuft“ vor `DISCONNECTED` (sonst `_climate_source` „aus dem Akku“ nie erreicht). Prüfbericht M10.
- **2026-10-25 – v0.27.13 Nicht endliche Werte.** `inputs._float` → None bei inf/nan/Overflow;
  `to_value` → INVALID, wenn die Umrechnung (kW→W) überläuft. Vorher `round(inf)` in
  `sessions._sample`/`trips._trace` → Tick-Exception. Prüfbericht M7.
- **2026-10-25 – v0.27.12 Einheit normalisiert.** `inputs.to_value`: nach kW→W bzw. Wh→kWh
  trägt `Value.unit` die normalisierte Einheit (WS `_value`, Systemtest); Panel-Diagnose
  rundet Zahlen auf 3 Stellen, „–“ ohne „ s“. Prüfbericht M2 (live 24.10.: 9139.37 „kW“).
- **2026-10-25 – v0.27.11 HV-Zyklen MEASUREMENT.** `sensor.hv_contactor_cycles` state_class
  TOTAL_INCREASING → MEASUREMENT (Franks Quelle: `…_hv_contactor_cycles_remaining`, fallend).
  Prüfbericht Mittel M1; Tests HA-Seite in `tests/integration/test_review_2026_10_24.py`.
- **2026-10-25 – v0.27.10 Klima-Stopp.** `Executor.request_climate_stop` sendet nur mit
  `climate_available` (enthält `ovms_enabled`), sonst Event `CLIMATE_UNAVAILABLE`. Prüfbericht
  H7; Bericht-Stand aktualisiert (K1–H7 behoben, Mittel/Niedrig offen).
- **2026-10-25 – v0.27.9 Zähler-Plausibilität.** `costs.plausible_rise` (≤ 25 kW × Zeit seit
  letzter Änderung + 1 kWh); `IntervalAccumulator.last_at` (Zeit der letzten Änderung,
  gespeichert) verwirft unplausible Anstiege; `grid_energy_kwh` = Intervall-Summe statt
  Ende − Start; Klima-Zähler ebenso; Klimakosten mit kWh skaliert, wenn > Netz. Prüfbericht H6.
- **2026-10-25 – v0.27.8 Halo eingefroren.** `Executor._vehicle_charging(snap)` (OVMS-Flag
  GOOD): in `_in_charging` gilt Leistung als fließend, wenn `_halo_power_frozen` (LKV/STALE/
  unavailable in `_ingest_power`) und Auto lädt; `_escalate` weckt nie bei Auto lädt.
  Prüfbericht H5 (Pause → PAUSE_WAKE → CP-Puls mitten in der Ladung).
- **2026-10-25 – v0.27.7 Dry-Run → Live.** `Executor.set_shadow`: beim Wechsel in den
  Probebetrieb Live-Stand (`_attempts`, `_failed_window`, `_ended_window`, `failure_code`) in
  `_live_windows` sichern, Probebetrieb arbeitet auf Kopie; zurück zu Live → gesicherter Stand,
  Pause gelöscht, `state=None`. `Engine.set_shadow` delegiert. Prüfbericht H4.
- **2026-10-25 – v0.27.6 Fehlstart-Sperre.** `Engine._release_repeated_failures`: merkt das
  Fenster beim Erreichen von `REPEATED_START_FAILURES` (`_failure_window`, gespeichert), neues
  `active_window` → Zähler 0 + Event `START_FAILURES_RELEASED`; `executor._on_unplugged`
  setzt `consecutive_start_failures` zurück (§8.1). Prüfbericht H3.
- **2026-10-25 – v0.27.5 Shelly-Ausfall.** `health.CP_WAKEUP_ONLY = {CP_STATE_UNKNOWN}`:
  `blocks_automation`/`blocks_soc_functions` ignorieren ihn; Executor-Safety-Hold über
  `blocks_automation`, Klima-Sperre über `blocks_soc_functions`, Summary „Automatik gesperrt“
  nur bei `blocks_automation`. CP-Puls bleibt bei ERROR gesperrt. Prüfbericht H2.
- **2026-10-25 – v0.27.4 Pause ohne neues Budget.** `Desired.held_key`: `window_key` liefert
  ihn vor `reason|source|until`; Engine-Pause-Halten setzt `held_key=hold[1].window_key`
  (vorher `valid_until=None` → neuer Schlüssel → frische `WindowAttempts`). Prüfbericht H1.
- **2026-10-25 – v0.27.3 Volles Auto schläft.** `Engine._target_known_reached`: SOC nicht GOOD,
  aber planbar (LKV/ESTIMATED) ≥ min(Ziel, 99) → `wake_allowed=False` für SCHEDULE/ONE_SHOT
  → `TOPUP_SKIPPED` statt Weckkette. Prüfbericht 24.10. K2 (`docs/pruefbericht-2026-10-24.md`).
- **2026-10-25 – v0.27.2 Store sicher.** `ChargeSession/Trip.from_dict` filtern auf
  Dataclass-Felder; `Monitor.restore` überspringt kaputte Datensätze (`skipped_records`, Log);
  Coordinator speichert erst nach erfolgreichem `async_setup`-Restore (`_restored`), auch nicht
  im Shutdown nach Fehler. Prüfbericht 24.10.: Downgrade löschte die Historie.
- **2026-10-22 – v0.27.1 Reichweiten-Regel 2.** Start = Max in `RANGE_START_WINDOW` (3 min),
  Ende = letzter Wert bei Fahrzeug an (kein Nachlauf); `Trip.range_rule`, Backfill rechnet
  Regel < `RANGE_RULE` neu. Grund: smart rechnet laufende Heizung ein (101/112 km beim Start,
  Sprung 88→98 nach Aus). Panel `rangeVs()` „x % weiter/kürzer“.
- **2026-10-22 – v0.27.0 Fahrstil.** `trips.driving_style(trace)` (gentle/steady/anticipating,
  Mittel = score; Schwellen `STRONG_DRIVE_W` 25 kW + ≥ 10 km/h, `STEADY_MAX_DELTA_KMH` 5,
  `HARD_BRAKE_KMH` 40 je 15 s); `Trip.style` beim Schließen, `async_backfill_trip_style`,
  WS-Detail rechnet aus Recorder-Kurve; Gruppen `style_score` (km-gewichtet). Kein OVMS-Eco-Score.
- **2026-10-22 – v0.26.0 Reichweite je Fahrt.** `Trip.range_start_km/range_end_km` (OVMS_RANGE,
  Ende bis 2 min nach Aus), Properties `range_used_km`, `range_accuracy_pct` (km ÷ Anzeige-km);
  `temperature_statistics` → `range_accuracy_pct` je Gruppe; `async_backfill_trip_range`
  (Recorder, 10 Tage); Panel-Spalte „Reichweite“ + Gruppen-Spalte „Reichweite stimmt“.
- **2026-10-22 – v0.25.2 Eingefrorene Ladeleistung.** `ExternalChargeDetector`: Leistung nur
  bei Änderung binnen `POWER_FRESH` (10 min) oder frischem Flag, nie bei Flag „aus“;
  `_finish_live` verwirft ohne `charge_energy`-Anstieg und < `MIN_SOC_RISE_PCT` (2 %). Feld:
  OVMS wiederholte 5,695 kW nach Lidl, Cockpit zeigte den ganzen 22.10. „Lädt unterwegs“.
- **2026-10-21 – v0.25.1 Fremdladen live.** `ExternalChargeDetector`: laden = OVMS-Flag GOOD
  oder OVMS-Ladeleistung GOOD > Schwelle; kein SOC-Sprung, solange „lädt“ (auch gealtert);
  Energie über `_charge_battery_kwh` (erster/kleinster/letzter `charge_energy`); `status` →
  `summary` „Lädt unterwegs“; kein `DATA_CONFLICT` bei Kabel aus; HV-Aktivität inkl. Laden
  unterwegs; `CLIMATE_GAP` 10 s. Feld: Lidl 4,35 kWh Akku / 4,9 kWh bezahlt (89 %).
- **2026-10-20 – v0.25.0 Verbrauch realistisch.** `period_summary`: Start-SOC = erster SOC im
  Zeitraum, `grid_consumption` ohne Klima (+ `…_incl_climate`, `vehicle_consumption`), Kosten
  fürs Fahren; `Inp.OVMS_CHARGE_ENERGY` (v.c.kwh) → `plausible_charge_energy` (geändert,
  0,5–1,02 × Netz), `vehicle_energy_source`; `measured_sessions` bevorzugt echte Werte;
  `async_backfill_charge_energy` (Recorder, 10 Tage) beim Start.
- **2026-10-20 – v0.24.1 Klima-Blöcke.** `AFTER_DEPARTURE_MIN` = 5; Phasen sent→running→gap
  →(Neustart `executor.request_climate_restart`, `homelink 1`, nach `CLIMATE_GAP` 30 s, max.
  `MAX_RESTARTS` 3, nur wenn ≥ 2 min übrig)→finished; Wunsch hält bis `until` (nur „done“ =
  manueller Stopp beendet früher). OVMS-Anleitung: smart nur 5-min-Blöcke, homelink 2/3
  mit Auto-Neustart – am 20.10. fehlte der 3. Block.
- **2026-10-20 – v0.24.0 Ladepause.** `ExecState.PAUSED`: Leistung weg bei SOC < Ziel →
  `CHARGE_PAUSED`, nach `PAUSE_WAIT` (15 min) einmal Weckkette (`_pause_recovery`, CP-Nachlauf
  `PAUSE_POST_CP_WAIT_S` 300 s), sonst `PAUSE_HOLD`; `Snapshot.below_target`; Engine
  `_pause_hold` hält den Wunsch über Fensterende bis Ziel/abgesteckt; `_full_charge_ended`
  nur bei SOC ≥ 99. Pushes `PAUSE_HOLD`/`PAUSE_RESUMED`. Pausen-Zustand übersteht keinen Neustart.
- **2026-10-20 – v0.23.3 Klima hält die Wallbox.** `executor._escalate` und Leistungsverlust in
  `_in_charging` ignorieren `Reason.CLIMATE` (kein `TOPUP_SKIPPED`/`INTERRUPTED`). Feld 20.10.:
  Wallbox aus 05:18:06, HVAC an 05:18:12 → Akku. Klima lief nur ~10 statt 15 min (homelink 3).
- **2026-10-19 – v0.23.2 Fahrten löschen.** Dienst `delete_trip` (`monitor.delete_trip`),
  Panel-Knopf in der Fahrt-Detailzeile; `monitor._repair_trips` (Verbrauch None < 1 km);
  `temperature_statistics` ohne Fahrten < `MIN_CONSUMPTION_KM`. Außentemperatur seit
  19.10. von der Gartenstation `sensor.hmip_swo_b_…_actual_temperature` (Reconfigure).
- **2026-10-19 – v0.23.1 Temperaturquellen.** `outside_temperature`: HA-Sensor → Auto (GOOD)
  → Wetter; `Engine._changed` (Store `changed`) merkt echte Wertänderungen für
  `CHANGE_TRACKED`, unverändert > `UNCHANGED_STALE` (30 min) → LAST_KNOWN_VALID;
  `cabin_changed_at` daraus. OVMS-Außensensor 3–4 °C zu hoch (Feld 19.10.).
- **2026-10-19 – v0.23.0 Temperaturen im Cockpit.** `Inp.OVMS_CABIN_TEMP`;
  `engine.cabin_changed_at` (RawState.last_updated, weil OVMS schlafend wiederholt) →
  Snapshot; WS `get_temperature_history` (Recorder, 60/120/300 s); Panel `_sohChip`-Plakette
  `temp-toggle` + `tempSvg` (unveränderte Strecken > 30 min gestrichelt).
- **2026-10-19 – v0.22.5 Klima-Zeitfenster.** `climate.AFTER_DEPARTURE_MIN` = 2: Klima endet
  2 min nach Abfahrt (`until` > Abfahrt, Lock hält es über das Fensterende); Summary nennt
  die Abfahrt aus `next_window`; `climate_blocked` entfällt, solange `climate_active`.
  Feld 19.10.: Klima 05:23–05:28, Einstieg 05:33, Innenraum 23 → 15 °C, nur ~1,3 kW.
- **2026-10-19 – v0.22.4 Klima-Feldtest 2.** Klima-Energie aus Zählerdelta − Akku/η je Slot
  (`SessionTracker._climate`, Nachlauf `CLIMATE_TAIL`), Halo-Leistung ×3 bei einphasiger Last;
  `executor.session_id = None` bei `SESSION_END`; kein `DATA_CONFLICT` bei `_climate_heating`;
  `monitor._repair_sessions` (doppelte IDs, Klima ≤ Netz).
- **2026-10-19 – v0.22.3 Ziel 100 %.** `Engine._full_charge_ended`: bei Ziel ≥ 100
  (`FULL_TARGET_PCT`) kein `target_soc_wish`, sondern Aus nach `FULL_END_WAIT` (3 min) in
  `CHARGE_ENDED`. Nacht 19.10.: 58 → 100 % ohne Wecken (M8 17 s), Anzeige 100 % ≈ real 93 %,
  `CURRENT_SET` griff erst beim 2. Mal, OVMS `charger_power` = Netzseite (Messprotokoll).
- **2026-10-18 – v0.22.2 Cockpit-Beschriftungen.** `batterySvg`: Textbreite geschätzt,
  bei Kollision Ziel über dem Akku (viewBox oben erweitert); `timelineSvg.marker` mit
  Belegungsliste (Seite wechseln, sonst Zeile tiefer), Reihenfolge jetzt/Abfahrt/fertig/Klima.
  Live-Check v0.22.1: Log sauber, alle Eingänge GOOD, Details live ok.
- **2026-10-18 – v0.22.1 Fahrtende per Verriegelung.** `Inp.OVMS_LOCKED` (lock bevorzugt;
  binary_sensor mit device_class lock: on = entriegelt); `TripTracker`: aus + entriegelt
  (`unlocked_after_off`) + verriegelt → sofort schließen, sonst `trip_merge_gap_min`.
- **2026-10-18 – v0.22.0 Fahrt-Details.** `Trip.trace` ([s, km/h, Akku-W wie OVMS: + in den
  Akku/Rekup, − Antrieb, SOC], 15 s, im offenen Trip-Store); `Inp.OVMS_SPEED`;
  `get_trip_detail` (Recorder-Fallback 15 s via `async_recorder_minutes(step_s)`, Kosten
  über `monitor.home_price`); Panel `tripSvg`, Zeile `data-trip`. Mushroom-Karte umgestellt
  (Backup der alten Dashboard-Config im Browser-localStorage `ev_pilot_smarthome_backup_20261018`).
- **2026-10-18 – v0.21.1 Shelly-Aussetzer.** `Engine._relay_closed_at` +
  `_shelly_dropout_tolerated`: unerreichbarer Shelly gilt `SHELLY_DROPOUT_GRACE` (3 min) als
  „CP zu“, nicht nach CP-Puls (`executor.last_pulse_at`, 10 min) oder offener CP. Rückfahrt
  18.10. sauber erfasst (Fahrt schließt erst nach `trip_merge_gap_min` = 10 min).
- **2026-10-18 – v0.21.0 Klima-Energie.** `Inp.OVMS_BATTERY_POWER`; `SessionTracker._climate`
  (Halo − Akku/η je 15-min-Slot, nur bei `Engine._climate_heating`), `ChargeSession.
  climate_energy_kwh/climate_cost_eur`; Statistik, Panel-Spalte „Klima“, PDF-Zeile.
- **2026-10-18 – v0.20.2 Statussensor.** `sensor.ev_pilot_status` = `summary()`-Headline
  (Attribute detail/tone/climate_*); `summary._with_climate`/`_climate_note`/
  `_climate_running`; „Kein Laden mehr geplant“ nach letztem Block; `sensor._next_start`.
- **2026-10-18 – v0.20.1 Klima nach Feldtest.** Executor wartet mit `CLIMATE_START` auf
  Halo „an“ (`CLIMATE_CONFIRM_TIMEOUT` 60 s, sonst `CLIMATE_SKIPPED` + Push); Engine
  `_climate_lock`/`climate_phase` (due→sent→running→done|skipped, im Store), Ende bei
  `Inp.OVMS_HVAC` aus; `climate_sent` im Executor-Store; HV-Aktivität inkl. Start/Klima;
  `discovery.async_discover_late` (`LATE_DISCOVERY`) statt Steckererkennung allein.
- **2026-10-18 – v0.20.0 Ladekurve + Session-Details.** `ChargeSession.trace`
  ([s ab Start, Halo W, OVMS W, SOC], 1/min, max. 1440); `get_sessions` ohne `trace`,
  `get_session_detail` mit Ereignissen und Recorder-Fallback (`async_recorder_minutes`,
  auch fürs Cockpit); Panel: Zeile klickbar (`sess-*`-Klassen, `srow` ist Einstellungen).
- **2026-10-18 – v0.19.9 Erste echte Ladung.** Nacht sauber (Freigabe 10 s, kein Wecken,
  Aus bei 90 %). Fixes: `HvCycleMonitor` zählt Betrag (Restzähler fällt); `summary._upcoming`
  „Ziel erreicht“ bei `needed_kwh ≤ 0`, nur künftige Blöcke; `SessionTracker` Basis bei
  `CHARGER_ENABLE`, Nachlauf `TAIL_S` = 65 s (`closing`, im Store); Panel per `module_url`.
- **2026-10-18 – v0.19.8 Prüfbericht Texte/Doku.** `health.REASON_TEXT/STATUS_TEXT`,
  `OVERRIDE_TEXT`, `STATE_TEXT`, PDF-Labels, Panel-Labels, einheitliche Begriffe, README/ROADMAP.
  Prüfbericht vollständig abgearbeitet (Status oben im Bericht).
- **2026-10-18 – v0.19.7 Prüfbericht Stufe 3.** `MISSING_STATES` case-sensitiv (Halo
  „Unavailable“), `BLIND_WHEN_LOCKED`, kein Wecken bei unbekanntem Kabel, alte Leistung ≠ fließt,
  `OFF_RETRY_AFTER`, MWh-Schwelle 70, Gleichstand → spät, Verlust ≤ 40 %, Privatsphäre, `plug_discovery_done`.
- **2026-10-18 – v0.19.6 Prüfbericht Panel.** Render in `#app`, Toasts in `#toasts`;
  Signatur erst nach echtem Render; Select-Blur; Settings ohne Render bei offener Leiste;
  Berichte per `auth/sign_path`; `FAILURE_LABELS`/`failure_hint`; `dateOnly` lokal; Zeitleiste.
- **2026-10-18 – v0.19.5 Prüfbericht Stufe 2 Statistik/HA.** Externe Ladung lokales Datum;
  Fahrten mit `*_acc` bei Zählerreset und Odometer beim Schließen; `_report_due`/Catch-up/
  `_monthly_report_safe`; `_odometer_at` interpoliert; PDF-Monatsanteil; SOC-Sprung nur ohne
  Kabel; €/100 km SOC-korrigiert; `_unrecorded_attributes`; `_closed`; Admin-Dienste.
- **2026-10-18 – v0.19.4 Prüfbericht Stufe 2 Kern/Preise.** `_vehicle_finished` nur ≥ 95 %
  oder Ziel − 3; CHARGE_ENDED bedient neuen Wunsch; `_off_after_override`; Lernen mit
  Intervalllänge; Fahrzeugtemperatur LKV als Rückfall; Zwei-Block-Suche auf 5-min-Raster mit
  Präfixsummen; `_scaled` je Liste; `_close` mit typischer Slotlänge; breites except im Abruf.
- **2026-10-18 – v0.19.3 Prüfbericht Stufe 1 HA.** `statistics_month_start` (last_reset aus
  der berechneten Periode, Refresh bei Periodenwechsel vor `_handle`); `COMMAND_TIMEOUT_S` = 30 um
  `ports.execute`. Stufe 1 damit komplett.
- **2026-10-18 – v0.19.2 Prüfbericht Stufe 1 Kern.** Executor: `_ended_window` (persistiert)
  + `_failed_window` im `_initial_state`, `_fail` sperrt Halo, Disable im Cooldown → COOLDOWN;
  Sessions schließen bei CHARGE_ENDED; Klima `wake_allowed=False`; `_expire` CP-maskiert.
  Regressionstests `tests/core/test_review_fixes.py`.
- **2026-10-18 – v0.19.1 Prüfbericht Stufe 1 (Teil 1).** K1: `_charging_at` +
  `CHARGING_ACTIVITY_GRACE` (15 min) für die Qualität; K7: One-Shot-Wunsch entfällt bei
  erreichtem Ziel. Offen laut `docs/pruefbericht-2026-10-18.md`: K2–K6, K8, H1, H2, Stufe 2/3, Texte.
- **2026-10-18 – v0.19.0 Preisformate + Prüfung.** `prices.py`: Paare `[ts, preis]`
  (s/ms), ENTSO-e, mehr Schlüssel, €/MWh per Einheit, Fallback auf beliebige Liste;
  `describe_prices`; WS `check_prices` → `PriceFetcher.async_check`; Einstellungszeile
  „Preisquelle prüfen“. Frank nutzt Tibber-Dienst (nicht `sensor.tibber_preisprognose`).
- **2026-10-17 – v0.18.0 Monatsbericht per Mail.** `core/mail.py` (Presets, `monthly_mail`,
  `build_message`, `send` im Executor), Optionen `mail_*`/`report_push_targets`, Feldtyp
  `password` (nie zurück, leer = behalten), `async_send_report_mail` am 1. + Dienst
  `send_report_mail`, Push an Zusatzziele. Frank: Gmail (App-Passwort), Empfängerin Melanie.
- **2026-10-17 – v0.17.3 Start im Cockpit.** `localStorage` `ev-pilot-view` entfernt;
  `connectedCallback` nach `disconnectedCallback` setzt den Reiter auf Cockpit (außer bei
  offenem `_settingsDraft`). Frank wollte nach HA-Seitenwechsel nicht im alten Reiter landen.
- **2026-10-17 – v0.17.2 Test-Center.** Diagnose: System-, Lade- und Push-Test in
  `<details data-details="tests">` am Ende; offen bei laufendem Ladetest bzw. Push-Test < 10 min.
- **2026-10-17 – v0.17.1 Preis-Fenster.** Overlay deckend (Hintergrundfarbe), `.pform`/`.pbar`
  statt `.form`/`.bar` (Konflikt mit Grid bzw. 8-px-Fortschrittsbalken), Knöpfe 2×2.
  Frank: Knöpfe und Ziffernblock auf dem iPhone funktionieren.
- **2026-10-17 – v0.17.0 Preis per Knopf/Ziffernblock.** Push-Aktionen
  `EV_PILOT_EXT_PRICE|<id>|<preis>` aus Option `external_price_buttons` (`prices.parse_price_list`),
  Push-`url` `/ev-pilot?external_price=<id>` → Panel-Dialog (`inputmode=decimal`) → Dienst
  `set_external_price`. iOS-Textfeld entfernt (Tastatur nicht steuerbar). Frank wollte Ziffernblock.
- **2026-10-17 – v0.16.1 Push-Test Preisabfrage.** Dienst `test_price_push` →
  `Coordinator.async_test_price_push` (Aktion `ext_price:test-…`), Antwort in
  `price_push_test` (WS-State), Diagnose-Karte; Test-IDs ändern keine Fremdladung.
- **2026-10-17 – v0.16.0 Fremdladen-Preis per Push.** Notification-Aktion `ext_price:<id>` →
  `textInput`-Button `EV_PILOT_EXT_PRICE|<id>`; `reply_text` → `parse_price_input` (ct > 5) →
  `Coordinator._set_external_price`. Panel: `<details data-details>` mit `_openDetails`.
- **2026-10-17 – v0.15.1 Statistik-Korrekturen.** `OdometerSource.AUTO` (Default; OVMS wenn
  gemappt, `Monitor.ovms_odometer`), `trips.net_energy` (used − recd, None bei recd > used),
  kWh/100 km erst ab 1 km, Temperaturstatistik nur Fahrten mit Strecke+Energie, Preis =
  Ø echter Heimstrompreis.
- **2026-10-17 – v0.15.0 Ladestrom.** `charge_current_a` je Plan/One-Shot (None = Wallbox
  lassen), Optionen `default_current_a`/`manual_current_a` (live)/`phases`; `Desired.current_a`,
  `Engine._set_current` → `CommandKind.SET_CURRENT` → `number.set_value` (min/max geklemmt),
  nur wenn Halo an sein soll; `VehicleParams.current_a` begrenzt die Prognoseleistung.
- **2026-10-17 – v0.14.1 Kein Plug-Event nach Neustart.** `Engine.tick`: Kabel „aus“ zählt
  als unbekannt, solange `ovms_plug` konfiguriert, aber noch nicht verfügbar ist (auch für
  den Executor). Erster Ladetest bei Frank ok: ohne Wecken, 7,9 kW (Halo max. 12 A).
- **2026-10-17 – v0.14.0 Ladetest.** `core/charge_test.py` (ChargeTest: Schritte aus
  Executor-Events, Ende 60 s nach CHARGE_STABLE, max. 8 min, dann Halo-aus-Prüfung);
  `Engine.start_charge_test` = DURATION-Override, nur live/eingesteckt; Dienst `charge_test`,
  WS-State `charge_test`, Diagnose-Karte. `async_run` setzt Shadow vor der Aktion.
- **2026-10-17 – v0.13.9 Weiterladen nach Blockende.** `Engine._overrun`: letzter Block eines
  verriegelten Fensters wird bis `ready_at` gestreckt, solange der Executor CHARGING/
  CHARGE_STABILIZING ist und kein Target-Hold greift; `ChargeWindow.overrun`, Desired mit
  `wake_allowed=False`, Event `BLOCK_EXTENDED`.
- **2026-10-17 – v0.13.8 Voller Akku nicht lange stehen.** Optionen `full_soc_pct` (90) und
  `full_hold_max_h` (2 h) → `VehicleParams`; `_window` begrenzt die Preissuche bei Ziel >
  `full_soc_pct` auf ≥ ready − needed − hold. Frank: Büroplan 100 % im Winter.
- **2026-10-17 – v0.13.7 Formular-Entwürfe.** Panel merkt `[data-form] [name]`-Eingaben in
  `_formDrafts` und setzt sie nach jedem Render wieder ein; `_submit` löscht den Entwurf nur
  bei Erfolg. Vorher: Fokus weg → nächster Poll setzte One-Shot auf morgen 07:00/100 %.
- **2026-10-17 – v0.13.6 Kostenprognose, Name One-Shot.** `_window`: Kosten = Blockkosten
  / (Leistung × Blockdauer) × `needed_kwh` statt volle Leistung inkl. Reserve. One-Shot heißt
  „Einmalige Abfahrt“ (Planner, Report, Panel-Pill mit Datum).
- **2026-10-17 – v0.13.5 Latch nur eingesteckt.** `Engine._latch` friert Start/Blöcke nur
  ein, wenn `_cable is not False`; ein verpasster Block (Auto unterwegs) wird ab jetzt neu
  geplant. Frank: Büroplan Mo–Mi 05:20, Tagespreise liegen sonst im Bürozeitraum.
- **2026-10-17 – v0.13.4 Einstecken per OVMS.** Halo meldet Kabel nur bei freigegebenem
  Ladepunkt (Status `Unavailable` = gesperrt). Neue Inputs `ovms_plug`, `ovms_location`;
  `source_policy.plugged_in` verschmilzt sie mit `cable_connected` (unterwegs = nicht
  gesteckt). `async_discover_plug` ergänzt sie beim Start aus dem Entity-Registry.
- **2026-10-17 – v0.13.3 Preisabruf nach Neustart.** `PriceFetcher` wartet auf
  `EVENT_HOMEASSISTANT_STARTED`, wiederholt Fehlschläge nach 60/120/300 s
  (`RETRY_DELAYS_S`), meldet `PRICE_SOURCE_PROBLEM` erst danach (Tibber antwortet
  direkt nach dem Start leer).
- **2026-10-16 – v0.13.2 Anzeige-Maßstab.** Cockpit-Gauge/Kurve: max(Bordlader, gelernt,
  aktuell, 24-h-Spitze), gedeckelt durch Wallbox. Frank: Halo 11 kW 3-phasig, smart 22-kW-Lader.
- **2026-10-16 – v0.13.1 Akku-Grafik, Taper 80 %.** Neue `batterySvg` (Kapsel, Verlauf,
  Shimmer), Option `taper_from_pct` (80), Lernen: Leistung ≤ Wallbox statt Band um Nennwert
  (Frank: smart mit 22-kW-Lader; Wallbox meldet keinen Ladestand, Auto beendet selbst).
- **2026-10-16 – v0.13.0 Systemtest & Extras (Review Stufe 3b).** `system_check.py` +
  WS `run_system_check` (nichts schalten, nie wecken), `start_one_shot` mit `departure_at`/
  `target_soc`, Wochenrückblick So 18:00 (`notify_weekly`, `Monitor.week`, `weekly_text`).
- **2026-10-16 – v0.12.0 Lernendes Lade-Modell (Review Stufe 3a).** `core/learning.py`
  (Median aus ≤15 Sessions, ≥3 nötig, Plausibilitätsband 0,6–1,5), `VehicleParams`
  mit `learned_*` und Taper ab 90 % (Faktor 0,6), `soc_after`, Option `learn_charging`.
- **2026-10-16 – v0.11.0 Oberfläche (Review Stufe 2b).** `core/summary.py` (Statussatz,
  getestet), neue Ladeplan-Karte (`plan-day`, `plan-mode`), Zeitleiste im Ladeplan,
  Ereignisfilter „Wichtiges“, Render nur bei Änderung (Signatur ohne `age_s`).
- **2026-10-16 – v0.10.0 Robustheit (Review Stufe 2a).** Fremdladen nur bei Kabel=aus bzw.
  bekanntem Zähler, `safety_margin_min` entfernt (Migration minor 2, Reserve 10 %/≥5 min),
  `set_plans`/`set_manual_target` ohne Admin, Push-Aktionen an Einstecken gebunden
  (`plug_offer_valid`), `ACTION_RETRY`, Chart-Backfill aus Recorder.

- **2026-10-16 – v0.9.3 Übergänge sicher (Review Stufe 1).** Ziel-SOC je Fenster gehalten
  (`_target_hold`, Nachladen nur frisch −3 %, `wake_allowed=False`), Ladeende per
  Leistungsabfall/OVMS/99 %, Dry-Run = Schattenbetrieb (`set_shadow`, virtuelle Wallbox),
  Konflikt-Karenz 180 s, `tests/core/test_scenarios.py`.

- **2026-10-16 – v0.9.2 Neustartfestigkeit.** Leere Planliste wird wiederhergestellt (vorher
  Standardplan), Pläne speichern automatisch, Regressionstest Neustart (Pläne + ovms_enabled).

- **2026-10-16 – v0.9.0/v0.9.1 Fahrzeugzugriff & Einstellungen.** Ein Schalter
  „Lesen & Schreiben“, OVMS-Befehlsweg automatisch (`ovms.send_command`), Ladeziel je Plan
  und für „Jetzt laden“ (nur im Ladeplan). Einstellungen als Akkordeon mit Einfach/Experte,
  `show_if`, Speichern-Leiste. OVMS-Doku-Abgleich: `xsq wakeup` auto beim 453,
  HV-Zyklen-Vektor. 141 Tests grün.

- **2026-10-15 – v0.8.0 Umbenennung in „EV Charging Pilot“.** Domain/Repo/Entitäten neu
  (`ev_charging_pilot`, `ev_pilot_*`), frei wählbarer Fahrzeugname → „<Name> Charging Pilot“
  überall, Texte herstellerneutral (Wallbox statt Halo, Fahrzeug statt OVMS).

- **2026-10-13 – v0.6.1–v0.7.0 nach erstem Test bei Frank.** Auto-Erkennung im
  Config Flow, grafisches Cockpit, Shelly per Klick konfigurieren, Reiter
  Einstellungen, eigenes Fahrzeugfoto statt Zeichnung (Frank: Zeichnung war „kein 453“),
  Ladeziel-Regler, Icon. 133 Tests grün.

- **2026-10-13 – v0.6.0 Tibber, PDF, Fremdladeerkennung.** Repo öffentlich, evcc
  aus der Doku entfernt, Release für HACS-Testinstallation. 121 Tests grün.

- **2026-10-13 – v0.5.0 komplette Integration.** Entitäten/Services/WS nach §12,
  Config-/Options-Flow nach §13, Push mit Rückfrage, Panel mit 5 Ansichten,
  YAML-Dashboard, Replay mit Poll-Nachbildung. ~100 Tests grün.

Ältere Einträge aus dem Fortschritts-Log in CLAUDE.md landen hier, neueste oben.

- **2026-10-13 – Phase 0 + Kern-Engine.** Wakeup-Kette im Package, `core/engine.py`
  als HA-freie Tick-Pipeline, Replay, Sessions, Trips, Statistik, Klima.

- **2026-10-13 – Masterplan vollständig.** Fassung mit §12–§16 übernommen,
  Defaults an §13.2 angeglichen.

- **2026-10-13 – v0.1.0 Grundgerüst.** Repo, Kern (Planner, Arbiter, Executor,
  Health, Kosten), Integration im Dry-Run, Phase-0-Package.
