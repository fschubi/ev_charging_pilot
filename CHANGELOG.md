# Changelog

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
