# Smart EQ 453 Charging Center

Home-Assistant-Integration, die das Laden eines **smart EQ fortwo 453** an
einer **Charge Amps Halo** komplett übernimmt: abfahrtsbasierte Ladeplanung,
Wakeup-Kaskade (OVMS → CP-Puls über Shelly), System-Health, Push-Meldungen
und – in späteren Versionen – Verbrauchs- und Kostenstatistik.

> **Status: v0.1 – Entwicklungsstand.** Die Integration startet immer im
> **Dry-Run** und protokolliert nur, was sie schalten würde. Vor dem
> produktiven Einsatz steht die Messphase (siehe [`phase0/`](phase0/README.md)).

## Was die Integration beantwortet

- Ist der Smart angeschlossen und lädt er stabil?
- Erreicht er bis zur Abfahrt den Mindest-SOC?
- Musste er geweckt werden?
- Wie viele kWh wurden diesen Monat zuhause geladen, was hat das gekostet?
- Ist das System gesund?

## Voraussetzungen

- Home Assistant ≥ 2025.1
- HACS-Integration **Chargeamps** (Halo)
- optional: Shelly 1 Mini Gen3 in der CP-Leitung (Wakeup), OVMS v3

## Installation (HACS, benutzerdefiniertes Repository)

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories* →
   `https://github.com/fschubi/smart453_charging_center`, Kategorie *Integration*.
2. „Smart EQ Charging Center“ installieren, HA neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → *Smart EQ Charging Center*.
4. Entitäten der Halo (und optional Shelly/OVMS) auswählen.

## Entitäten

| Entität | Bedeutung |
| --- | --- |
| `sensor.…_ladezustand` | Executor-Zustand (Nicht gesteckt, Lädt, Wakeup CP, …) |
| `sensor.…_soll_grund` | Warum die Halo an/aus sein soll (Wochenplan, Override, Ziel-SOC …) |
| `sensor.…_system_health` | Gesund / Eingeschränkt / Fehler mit Gründen |
| `sensor.…_nachster_ladestart` | Start des nächsten Ladefensters |
| `sensor.…_erwarteter_soc_bei_abfahrt` | Schätzung (nur mit SOC) |
| `binary_sensor.…_override_aktiv`, `…_datenkonflikt`, `…_problem` | Statusanzeigen |
| `switch.…_dry_run` | an = nur protokollieren |
| Buttons | Jetzt laden · Laden stoppen · Heute Nacht laden · Override aufheben · Fehler zurücksetzen |

## Sicherheit

Der CP-Wakeup greift in die Pilot-Leitung der Wallbox ein. Er bleibt
gesperrt, bis die Failsafe-Checkliste aus Masterplan §3.6 vollständig
abgehakt und die Verdrahtung von einer Elektrofachkraft abgenommen ist.

## Entwicklung

Spezifikation: [`docs/masterplan-v1.3.md`](docs/masterplan-v1.3.md) ·
Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)

```bash
uv venv -p 3.13 .venv
uv pip install -p .venv/bin/python -r requirements-test.txt
.venv/bin/python -m pytest
```

Lizenz: MIT
