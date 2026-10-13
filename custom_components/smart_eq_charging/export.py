"""CSV / JSON export of the monitor data (§12.3 export)."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Any

from .core.monitor import Monitor
from .core.settings import Settings

DATASETS = ("sessions", "trips", "external", "months")


def _in_range(moment: datetime | date, start: date | None, end: date | None) -> bool:
    day = moment.date() if isinstance(moment, datetime) else moment
    return (start is None or day >= start) and (end is None or day <= end)


def rows(monitor: Monitor, settings: Settings, dataset: str, start: date | None,
         end: date | None) -> list[dict[str, Any]]:
    data = monitor.data
    tz = monitor.tz
    if dataset == "sessions":
        out = [s.as_dict() for s in data.sessions
               if _in_range(s.started_at.astimezone(tz), start, end)]
        for row in out:
            row.pop("energy_intervals", None)
        return out
    if dataset == "trips":
        return [t.as_dict() for t in data.trips
                if _in_range(t.started_at.astimezone(tz), start, end)]
    if dataset == "external":
        return [e.as_dict() for e in data.external if _in_range(e.date, start, end)]
    if dataset == "months":
        first = start or min((d for d in data.days_seen), default=date.today())
        last = end or date.today()
        months, year, month = [], first.year, first.month
        while (year, month) <= (last.year, last.month):
            months.append(monitor.month(year, month, settings, last))
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return months
    raise ValueError(f"unknown dataset {dataset}")


def render(items: list[dict[str, Any]], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(items, indent=1, ensure_ascii=False, default=str)
    buffer = io.StringIO()
    fields: list[str] = []
    for item in items:
        fields += [k for k in item if k not in fields]
    writer = csv.DictWriter(buffer, fieldnames=fields, delimiter=";", extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow({k: v for k, v in item.items()})
    return buffer.getvalue()
