# Roadmap (abgeleitet)

> Der Masterplan v1.3 nennt eine neue Phase 0 und eine „verschlankte v0.1“,
> die Roadmap selbst (und §12–§16) fehlt aber in der vorliegenden Datei.
> Diese Fassung ist aus den Abschnitten §1–§11 abgeleitet und muss mit der
> vollständigen Fassung abgeglichen werden.

| Phase | Inhalt | Status |
| --- | --- | --- |
| 0 | evcc aus, Zeitautomation, `utility_meter`, Messprotokoll M1–M8, CP-Checkliste | Package fertig, Messungen offen |
| v0.1 | HA-freier Kern, Executor im **Dry-Run**, Config-/Options-Flow, Health, Event-Log, Push | gebaut |
| v0.2 | Defaults aus Messungen übernehmen, Einzeltest ohne Dry-Run, Actionable Notification beim Einstecken (§8.4), Logbuch | offen |
| v0.3 | Lade-Sessions mit Energieintervallen und Kosten (§10.4, §11), Fremdladen (§10.5) | offen |
| v0.4 | OVMS-Anbindung (MQTT, §16): SOC/Qualität, SW-Wakeup, Ziel-SOC produktiv | offen |
| v0.5 | Drive & Energy Monitor: Trips, Monatsbilanz mit SOC-Ausgleich, Temperaturstatistik (§10) | offen |
| Phase 5 | Vorklimatisierung (§9) nach Test der `homelink`-Befehle | offen |
| später | Frontend/WebSocket-API (§12), Replay-Port, OCPP-Prüfauftrag, Tibber | offen |
