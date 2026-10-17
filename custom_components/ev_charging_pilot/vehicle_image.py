"""Own vehicle photo for the cockpit: upload (admin), serve (logged-in users), delete."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN

IMAGE_URL = f"/api/{DOMAIN}/vehicle_image"
MAX_BYTES = 8 * 1024 * 1024
TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAGIC = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"RIFF": "webp"}


def image_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(DOMAIN))


def find_image(folder: Path) -> Path | None:
    for ext in ("png", "jpg", "webp"):
        path = folder / f"vehicle.{ext}"
        if path.is_file():
            return path
    return None


def image_version(hass: HomeAssistant) -> int | None:
    """Modification time as cache buster – None without a photo (call in executor)."""
    path = find_image(image_dir(hass))
    return int(path.stat().st_mtime) if path else None


def _sniff(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            if ext == "webp" and data[8:12] != b"WEBP":
                return None
            return ext
    return None


class VehicleImageView(HomeAssistantView):
    url = IMAGE_URL
    name = f"api:{DOMAIN}:vehicle_image"
    requires_auth = True

    async def get(self, request: web.Request) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        path = await hass.async_add_executor_job(find_image, image_dir(hass))
        if path is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not request["hass_user"].is_admin:
            return web.Response(status=HTTPStatus.FORBIDDEN)
        form = await request.post()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "file"):
            return web.json_response({"error": "Keine Datei"}, status=HTTPStatus.BAD_REQUEST)
        data = await hass.async_add_executor_job(upload.file.read, MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return web.json_response({"error": "Datei größer als 8 MB"},
                                     status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        ext = _sniff(data)
        if ext is None:
            return web.json_response({"error": "Nur PNG, JPG oder WebP"},
                                     status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        folder = image_dir(hass)

        def save() -> int:
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob("vehicle.*"):
                old.unlink()
            path = folder / f"vehicle.{ext}"
            path.write_bytes(data)
            return int(path.stat().st_mtime)

        version = await hass.async_add_executor_job(save)
        _notify(hass, version)
        return web.json_response({"url": f"{IMAGE_URL}?v={version}", "bytes": len(data)})

    async def delete(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not request["hass_user"].is_admin:
            return web.Response(status=HTTPStatus.FORBIDDEN)

        def remove() -> None:
            for old in image_dir(hass).glob("vehicle.*"):
                old.unlink()

        await hass.async_add_executor_job(remove)
        _notify(hass, None)
        return web.json_response({"deleted": True})


def _notify(hass: HomeAssistant, version: int | None) -> None:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        entry.runtime_data.vehicle_image_version = version
