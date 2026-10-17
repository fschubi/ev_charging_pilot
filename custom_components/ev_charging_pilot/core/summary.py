"""Plain-language status for the cockpit: what is happening and what comes next.

The panel shows technical states elsewhere; this module turns them into one
headline and one sentence a user understands without knowing the masterplan.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .engine import FAILURE_HINTS, Engine
from .executor import ExecState
from .health import HealthStatus
from .inputs import Inp
from .model import Value
from .planner import OverrideMode

WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _at(moment: datetime | None, engine: Engine, now: datetime) -> str:
    """"04:27" today, "Mo 05:30" on another day."""
    if moment is None:
        return "–"
    local = moment.astimezone(engine.tz)
    if local.date() == now.astimezone(engine.tz).date():
        return f"{local:%H:%M}"
    return f"{WEEKDAYS[local.weekday()]} {local:%H:%M}"


def _span(a: datetime, b: datetime, engine: Engine, now: datetime) -> str:
    """"Mi 02:00–03:12" – the day only once."""
    same_day = a.astimezone(engine.tz).date() == b.astimezone(engine.tz).date()
    end = f"{b.astimezone(engine.tz):%H:%M}" if same_day else _at(b, engine, now)
    return f"{_at(a, engine, now)}–{end}"


def _kw(value: Value | None) -> float | None:
    if value is None or not value.available or value.normalized is None:
        return None
    return float(value.normalized) / 1000


def summary(engine: Engine, now: datetime, live: bool) -> dict[str, Any]:
    headline, detail, tone = _describe(engine, now)
    if not live:
        detail = f"{detail} Probebetrieb: es wird nichts geschaltet, nur protokolliert.".strip()
    return {"headline": headline, "detail": detail, "tone": tone}


def _describe(engine: Engine, now: datetime) -> tuple[str, str, str]:
    ex = engine.executor
    state = ex.state
    window = engine.next_window
    at = lambda moment: _at(moment, engine, now)  # noqa: E731

    if engine.health.status is HealthStatus.ERROR:
        return ("Automatik gesperrt",
                "Aus Sicherheitsgründen wird nichts geschaltet – Details unter „System“.", "bad")
    if not engine.automation_enabled:
        return "Automatik aus", "Die Wallbox wird nicht geschaltet, Pläne ruhen.", "warn"
    if state is ExecState.START_FAILED and ex.failure_code:
        title = "Ladung abgebrochen" if ex.failure_code == "CHARGE_INTERRUPTED" \
            else "Ladestart fehlgeschlagen"
        return title, FAILURE_HINTS.get(ex.failure_code, "") + ".", "bad"
    if state is ExecState.DISCONNECTED:
        if window is None:
            return "Nicht eingesteckt", "Kein Ladeplan aktiv.", "info"
        when = "jetzt" if window.start <= now else f"bis {at(window.start)}"
        return ("Nicht eingesteckt",
                f"Nächste Abfahrt {at(window.departure)} („{window.name}“) – bitte {when} "
                "einstecken.", "info")
    if state in (ExecState.CHARGING, ExecState.CHARGE_STABILIZING):
        kw = _kw(engine.values.get(Inp.CHARGE_POWER))
        headline = f"Lädt mit {kw:.1f} kW".replace(".", ",") if kw else "Lädt"
        override = engine.override
        if override is not None and override.charger_enabled:
            target = f"bis {override.target_soc} %" if override.mode is OverrideMode.UNTIL_SOC \
                else "bis das Kabel gezogen wird"
            return headline, f"„Jetzt laden“ {target}.", "ok"
        if window is not None:
            finish = window.estimate.finish_at
            return (headline, f"Ziel {window.preferred_soc_pct} %"
                    + (f", fertig ca. {at(finish)}" if finish else "")
                    + f" – Abfahrt {at(window.departure)}.", "ok")
        return headline, "", "ok"
    if state is ExecState.WAKEUP_OVMS:
        return "Weckt das Auto", "Software-Wakeup über das Fahrzeugmodul läuft.", "info"
    if state is ExecState.WAKEUP_CP:
        return "Weckt das Auto", "Kurzer CP-Puls über das Relais läuft.", "info"
    if state in (ExecState.ENABLING, ExecState.WAITING_FOR_CHARGE):
        return "Ladestart läuft", "Die Wallbox ist freigegeben, das Auto beginnt gleich.", "info"
    if state is ExecState.CHARGE_ENDED:
        return "Ladung beendet", "Das Auto hat selbst aufgehört – der Akku ist voll.", "ok"
    if engine.target_held and window is not None:
        return (f"Ziel {window.preferred_soc_pct} % erreicht",
                f"Das Auto ruht bis zur Abfahrt {at(window.departure)}.", "ok")
    if window is None:
        return "Bereit", "Kein Ladeplan aktiv – „Jetzt laden“ startet sofort.", "info"
    return _upcoming(engine, window, at, lambda a, b: _span(a, b, engine, now))


def _upcoming(engine: Engine, window, at, span) -> tuple[str, str, str]:
    e = window.estimate
    detail = f"Abfahrt {at(window.departure)}, fertig vor {at(window.ready_at)}."
    tone = "info"
    if e.minimum_reachable is False:
        detail += (f" Mindestens {window.minimum_soc_pct} % werden voraussichtlich nicht "
                   f"erreicht (erwartet {e.expected_soc_at_departure:.0f} %).")
        tone = "warn"
    if window.blocks:
        times = ", ".join(span(a, b) for a, b in window.blocks)
        return f"Lädt in der günstigsten Zeit {times}", detail, tone
    if window.fallback_without_soc:
        return (f"Lädt ab {at(window.start)}",
                f"Fester Start, weil kein aktueller Ladestand bekannt ist. {detail}", tone)
    if e.duration is not None and e.duration.total_seconds() <= 0:
        return (f"Kein Laden nötig – schon {e.soc_pct:.0f} %",
                f"Ziel {window.preferred_soc_pct} % ist erreicht. {detail}", "ok")
    if e.finish_at is not None:
        return (f"Lädt {span(window.start, e.finish_at)} auf {window.preferred_soc_pct} %",
                detail, tone)
    return f"Lädt ab {at(window.start)} auf {window.preferred_soc_pct} %", detail, tone


def _de(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def weekly_text(week: dict[str, Any]) -> str:
    """One line for the Sunday push."""
    parts = [f"{_de(week['home_kwh'], 1)} kWh zu Hause für {_de(week['cost_eur'], 2)} €",
             f"{week['charges']} {'Ladung' if week['charges'] == 1 else 'Ladungen'}"]
    if week["failed"]:
        parts.append(f"{week['failed']} fehlgeschlagen")
    parts.append(f"{week['wakeups']}× geweckt")
    if week["external_kwh"]:
        parts.append(f"{_de(week['external_kwh'], 1)} kWh unterwegs")
    if week["km"] is not None:
        parts.append(f"{week['km']} km")
    return " · ".join(parts)
