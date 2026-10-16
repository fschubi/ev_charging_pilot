# Entwickler-Changelog (vollständige Historie)

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
