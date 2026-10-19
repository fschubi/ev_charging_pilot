# Entwickler-Changelog (vollständige Historie)

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
