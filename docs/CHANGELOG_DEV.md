# Entwickler-Changelog (vollständige Historie)

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
