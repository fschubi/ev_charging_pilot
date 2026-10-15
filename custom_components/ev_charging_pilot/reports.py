"""PDF reports: create, list, serve (authenticated) and the automatic monthly report."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .core.report import month_report, year_report

if TYPE_CHECKING:
    from .coordinator import ChargingCenter

REPORT_URL = f"/api/{DOMAIN}/report"
NAME_RE = re.compile(r"^ev-pilot-(\d{4})(-\d{2})?\.pdf$")


def report_name(year: int, month: int | None) -> str:
    return f"ev-pilot-{year}-{month:02d}.pdf" if month else f"ev-pilot-{year}.pdf"


def previous_month(now: datetime) -> tuple[int, int]:
    first = now.replace(day=1)
    last = first - timedelta(days=1)
    return last.year, last.month


async def async_create_report(center: ChargingCenter, year: int,
                              month: int | None = None) -> dict[str, Any]:
    now = datetime.now(center.tz)
    folder = center.data_dir / "reports"
    name = report_name(year, month)

    def build() -> int:
        data = (month_report(center.monitor, center.settings, year, month, now, center.name)
                if month else year_report(center.monitor, center.settings, year, now,
                                          center.name))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        return len(data)

    size = await center.hass.async_add_executor_job(build)
    return {"file": name, "url": f"{REPORT_URL}/{name}", "bytes": size}


async def async_list_reports(center: ChargingCenter) -> list[dict[str, Any]]:
    folder = center.data_dir / "reports"

    def scan() -> list[dict[str, Any]]:
        if not folder.exists():
            return []
        return [{"file": p.name, "url": f"{REPORT_URL}/{p.name}", "bytes": p.stat().st_size}
                for p in sorted(folder.glob("ev-pilot-*.pdf"), reverse=True)]

    return await center.hass.async_add_executor_job(scan)


class ReportView(HomeAssistantView):
    """Download a report. Requires a logged-in user – reports contain cost data."""

    url = REPORT_URL + "/{name}"
    name = f"api:{DOMAIN}:report"
    requires_auth = True

    async def get(self, request: web.Request, name: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        if not NAME_RE.match(name):
            return web.Response(status=HTTPStatus.BAD_REQUEST)
        path = Path(hass.config.path(DOMAIN, "reports", name))
        if not await hass.async_add_executor_job(path.is_file):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        return web.FileResponse(path, headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": f'inline; filename="{name}"',
        })
