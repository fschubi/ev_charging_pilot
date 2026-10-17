"""PDF monthly and yearly reports (formerly "später" in §15).

The report is meant for the private household split of the charging cost:
home kWh from the Halo meter, cost per session, external charges, distance
and consumption with their quality flags.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .monitor import Monitor
from .pdf import PdfDocument
from .settings import Settings

MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]
REASONS = {"schedule": "Wochenplan", "one_shot": "Einmalig", "override": "Override",
           "rfid": "RFID", "climate": "Klima", "target_soc_reached": "Ziel-SOC",
           "default_off": "–", "automation_off": "–", "safety_lock": "–"}
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
ACCENT = (0.0, 0.53, 0.82)
GREY = (0.42, 0.42, 0.42)
LIGHT = (0.95, 0.96, 0.98)
MARGIN = 48


def _n(value: Any, digits: int = 1, unit: str = "") -> str:
    if value is None:
        return "–"
    text = f"{float(value):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} {unit}".strip()


class _Writer:
    """Keeps the cursor and adds pages when a block does not fit."""

    def __init__(self, title: str, subtitle: str, generated: str) -> None:
        self.doc = PdfDocument(title=title)
        self.title, self.subtitle, self.generated = title, subtitle, generated
        self.y = 0.0
        self._header()

    def _header(self) -> None:
        d = self.doc
        d.rect(0, d.height - 92, d.width, 92, fill=ACCENT)
        d.text(MARGIN, d.height - 48, self.title, 20, bold=True, color=(1, 1, 1))
        d.text(MARGIN, d.height - 70, self.subtitle, 11, color=(1, 1, 1))
        d.text(d.width - MARGIN, 28, f"Seite {d.page_count}", 8, color=GREY, align="right")
        d.text(MARGIN, 28, f"EV Charging Pilot · erstellt {self.generated}", 8, color=GREY)
        self.y = d.height - 120

    def ensure(self, height: float) -> None:
        if self.y - height < 60:
            self.doc.new_page()
            self._header()

    def heading(self, text: str) -> None:
        self.ensure(40)
        self.y -= 8
        self.doc.text(MARGIN, self.y, text, 13, bold=True, color=ACCENT)
        self.y -= 18

    def figures(self, items: Sequence[tuple[str, str]], columns: int = 3) -> None:
        width = (self.doc.width - 2 * MARGIN) / columns
        rows = (len(items) + columns - 1) // columns
        self.ensure(rows * 44 + 8)
        for index, (label, value) in enumerate(items):
            col, row = index % columns, index // columns
            x = MARGIN + col * width
            top = self.y - row * 44
            self.doc.rect(x + 2, top - 38, width - 6, 40, fill=LIGHT)
            self.doc.text(x + 10, top - 13, label, 8, color=GREY)
            self.doc.text(x + 10, top - 30, value, 13, bold=True)
        self.y -= rows * 44 + 8

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[str]],
              widths: Sequence[float], right: Sequence[int] = ()) -> None:
        total = sum(widths)
        scale = (self.doc.width - 2 * MARGIN) / total
        cols = [w * scale for w in widths]

        def head() -> None:
            self.doc.rect(MARGIN, self.y - 6, self.doc.width - 2 * MARGIN, 18, fill=LIGHT)
            x = MARGIN
            for i, title in enumerate(headers):
                align = "right" if i in right else "left"
                self.doc.text(x + (cols[i] - 4 if align == "right" else 4), self.y, title, 8,
                              bold=True, color=GREY, align=align)
                x += cols[i]
            self.y -= 18

        self.ensure(40)
        head()
        if not rows:
            self.doc.text(MARGIN + 4, self.y, "keine Einträge", 9, color=GREY)
            self.y -= 16
            return
        for row in rows:
            if self.y < 70:
                self.doc.new_page()
                self._header()
                head()
            x = MARGIN
            for i, cell in enumerate(row):
                align = "right" if i in right else "left"
                self.doc.text(x + (cols[i] - 4 if align == "right" else 4), self.y, str(cell), 8.5,
                              align=align)
                x += cols[i]
            self.doc.line(MARGIN, self.y - 5, self.doc.width - MARGIN, self.y - 5, 0.3)
            self.y -= 15
        self.y -= 6

    def bars(self, labels: Sequence[str], values: Sequence[float], unit: str,
             label_every: int = 1) -> None:
        height = 120
        self.ensure(height + 30)
        left, right = MARGIN + 30, self.doc.width - MARGIN
        base = self.y - height
        peak = max(values, default=0) or 1
        step = (right - left) / max(1, len(values))
        for frac in (0, 0.5, 1):
            y = base + frac * height
            self.doc.line(left, y, right, y, 0.3)
            self.doc.text(left - 4, y - 3, _n(peak * frac, 0), 7, color=GREY, align="right")
        for i, value in enumerate(values):
            h = value / peak * height
            if h > 0:
                self.doc.rect(left + i * step + step * 0.15, base, step * 0.7, h, fill=ACCENT)
            if i % label_every == 0:
                self.doc.text(left + i * step + step / 2, base - 11, labels[i], 7, color=GREY,
                              align="center")
        self.doc.text(left - 30, self.y + 6, unit, 7, color=GREY)
        self.y = base - 26

    def note(self, text: str) -> None:
        self.ensure(16)
        self.doc.text(MARGIN, self.y, text, 8, color=GREY)
        self.y -= 13


def _local(moment: datetime, tz: ZoneInfo) -> datetime:
    return moment.astimezone(tz)


def month_report(monitor: Monitor, settings: Settings, year: int, month: int,
                 now: datetime, title_name: str = "EV Charging Pilot") -> bytes:
    tz = monitor.tz
    today = now.astimezone(tz).date()
    summary = monitor.month(year, month, settings, today)
    start = datetime.combine(date(year, month, 1), time(0), tzinfo=tz)
    days = calendar.monthrange(year, month)[1]
    end = start + timedelta(days=days)
    w = _Writer(f"{title_name} – Monatsbericht", f"{MONTHS[month - 1]} {year}",
                now.astimezone(tz).strftime("%d.%m.%Y %H:%M"))

    w.heading("Hausabrechnung")
    w.figures([
        ("Heimladen (Wallbox-Zähler)", _n(summary["home_energy_kwh"], 2, "kWh")),
        ("Kosten Heimladen", _n(summary["home_cost_eur"], 2, "€")),
        ("Ø Preis", _n(summary["home_cost_eur"] / summary["home_energy_kwh"], 3, "€/kWh")
         if summary["home_energy_kwh"] else "–"),
        ("Fremdladen", _n(summary["external_energy_kwh"], 2, "kWh")),
        ("Kosten Fremdladen", _n(summary["external_cost_eur"], 2, "€")),
        ("Kosten gesamt", _n(summary["cost_eur"], 2, "€")),
    ])

    w.heading("Fahren und Verbrauch")
    w.figures([
        ("Strecke", _n(summary["distance_km"], 0, "km")),
        ("Netzverbrauch", _n(summary["grid_consumption_kwh_100km"], 1, "kWh/100 km")),
        ("Kosten pro 100 km", _n(summary["cost_per_100km_eur"], 2, "€")),
        ("Ladeverlust", _n(summary["charging_loss_pct"], 1, "%")),
        ("SOC-Änderung im Monat", _n(summary["delta_soc_pct"], 1, "%")),
        ("Ø Außentemperatur", _n(summary["outside_temp_avg_c"], 1, "°C")),
    ])

    daily = [0.0] * days
    sessions = [s for s in monitor.data.sessions
                if start <= _local(s.started_at, tz) < end]
    for session in monitor.data.sessions:
        for interval in session.energy_intervals:
            moment = _local(datetime.fromisoformat(interval["start"]), tz)
            if start <= moment < end:
                daily[moment.day - 1] += float(interval["kwh"])
    w.heading("Heimladen pro Tag")
    w.bars([str(d) for d in range(1, days + 1)], daily, "kWh", label_every=2)

    w.heading(f"Lade-Sessions ({len(sessions)})")
    rows = []
    for s in sessions:
        begin = _local(s.started_at, tz)
        finish = _local(s.ended_at, tz) if s.ended_at else None
        avg = s.cost_eur / s.grid_energy_kwh if s.grid_energy_kwh else None
        wake = "+".join(x for x, used in (("OVMS", s.ovms_wakeup_used), ("CP", s.cp_wakeup_used))
                        if used) or "–"
        rows.append([f"{WEEKDAYS[begin.weekday()]} {begin:%d.%m.}", begin.strftime("%H:%M"),
                     finish.strftime("%H:%M") if finish else "–", _n(s.grid_energy_kwh, 2),
                     _n(s.cost_eur, 2), _n(avg, 3), REASONS.get(s.reason, s.reason), wake,
                     "ok" if s.success else (s.failure_code or "Fehler")])
    w.table(["Tag", "Start", "Ende", "kWh", "€", "€/kWh", "Grund", "Wakeup", "Ergebnis"], rows,
            [48, 32, 32, 38, 38, 40, 55, 40, 112], right=(3, 4, 5))

    external = [e for e in monitor.data.external if start.date() <= e.date < end.date()]
    w.heading(f"Fremdladungen ({len(external)})")
    w.table(["Datum", "Ort", "kWh", "€", "Anbieter", "Hinweis"],
            [[e.date.strftime("%d.%m."), e.source, _n(e.energy_kwh, 2), _n(e.total_cost, 2),
              e.provider or "–", "geschätzt" if e.detected else ""] for e in external],
            [45, 70, 45, 45, 110, 70], right=(2, 3))

    w.heading("Hinweise")
    w.note(f"Qualität der Bilanz: {summary['quality']}"
           f"{' · Datenlücken im Monat' if not summary['complete'] else ''}.")
    w.note("Heim-kWh stammen aus dem internen Zähler der Wallbox – für die private Aufteilung im "
           "Haushalt geeignet.")
    w.note("Für Erstattung durch Arbeitgeber oder steuerliche Abrechnung wäre ein "
           "MID-geeichter Zähler nötig.")
    if any(e.detected for e in external):
        w.note("Automatisch erkannte Fremdladungen sind Schätzungen aus OVMS-Daten.")
    return w.doc.to_bytes()


def year_report(monitor: Monitor, settings: Settings, year: int, now: datetime,
                title_name: str = "EV Charging Pilot") -> bytes:
    tz = monitor.tz
    today = now.astimezone(tz).date()
    summary = monitor.year(year, settings, today)
    months = summary["months"]
    w = _Writer(f"{title_name} – Jahresbericht", str(year),
                now.astimezone(tz).strftime("%d.%m.%Y %H:%M"))
    w.heading("Jahresbilanz")
    w.figures([
        ("Heimladen", _n(summary["home_energy_kwh"], 1, "kWh")),
        ("Kosten Heimladen", _n(summary["home_cost_eur"], 2, "€")),
        ("Fremdladen", _n(summary["external_energy_kwh"], 1, "kWh")),
        ("Strecke", _n(summary["distance_km"], 0, "km")),
        ("Netzverbrauch", _n(summary["grid_consumption_kwh_100km"], 1, "kWh/100 km")),
        ("Kosten pro 100 km", _n(summary["cost_per_100km_eur"], 2, "€")),
    ])
    w.heading("Heimladen pro Monat")
    w.bars([m[:3] for m in MONTHS], [m["home_energy_kwh"] or 0 for m in months], "kWh")
    w.heading("Monate")
    w.table(["Monat", "Heim kWh", "Heim €", "Fremd kWh", "km", "kWh/100 km", "€/100 km",
             "Qualität"],
            [[MONTHS[i], _n(m["home_energy_kwh"], 1), _n(m["home_cost_eur"], 2),
              _n(m["external_energy_kwh"], 1), _n(m["distance_km"], 0),
              _n(m["grid_consumption_kwh_100km"], 1), _n(m["cost_per_100km_eur"], 2),
              m["quality"]] if date(year, i + 1, 1) <= today else [MONTHS[i]] + ["–"] * 7
             for i, m in enumerate(months)],
            [70, 55, 55, 55, 45, 60, 55, 70], right=(1, 2, 3, 4, 5, 6))
    temps = monitor.temperatures(settings, year)
    w.heading("Verbrauch nach Außentemperatur")
    w.table(["Gruppe", "km", "Fahrzeug kWh/100", "Netz kWh/100*", "Rekuperation %"],
            [[f"{name} °C", _n(g["distance_km"], 0), _n(g["vehicle_kwh_100km"], 1),
              _n(g["grid_kwh_100km"], 1), _n(g["recuperation_share_pct"], 0)]
             for name, g in temps["bands"].items()],
            [80, 60, 90, 90, 90], right=(1, 2, 3, 4))
    w.note("* Netzverbrauch je Gruppe ist aus Fahrzeugverbrauch und Ladeverlust geschätzt.")
    return w.doc.to_bytes()
