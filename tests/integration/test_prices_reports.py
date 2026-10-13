"""Tibber / price entity, PDF reports with authenticated download, options."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from homeassistant.core import SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_eq_charging.const import DOMAIN

from .conftest import DATA


async def _setup(hass, options):
    entry = MockConfigEntry(domain=DOMAIN, data=dict(DATA), version=2,
                            options={"mode": "dry_run", **options})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _register_tibber(hass, calls):
    start = dt_util.start_of_local_day()

    async def get_prices(call):
        calls.append(call.data)
        return {"prices": {"Zuhause": [
            {"start_time": (start + timedelta(hours=h)).isoformat(),
             "price": 0.15 if h in (26, 27) else 0.30}
            for h in range(48)]}}

    hass.services.async_register("tibber", "get_prices", get_prices,
                                 supports_response=SupportsResponse.ONLY)


async def test_tibber_prices_feed_the_engine(hass, halo):
    calls: list = []
    _register_tibber(hass, calls)
    entry = await _setup(hass, {"price_source": "tibber"})
    await hass.async_block_till_done()
    center = entry.runtime_data
    assert calls
    assert center.engine.dynamic_prices
    assert len(center.engine.price_schedule.slots) == 48
    assert hass.states.get("sensor.smart_eq_current_price").state == "0.3"
    response = await hass.services.async_call(DOMAIN, "refresh_prices", {}, blocking=True,
                                              return_response=True)
    assert response["slots"] == 48


async def test_missing_tibber_falls_back_and_logs(hass, halo):
    entry = await _setup(hass, {"price_source": "tibber"})
    await hass.async_block_till_done()
    center = entry.runtime_data
    assert not center.engine.dynamic_prices
    assert any(e["code"] == "PRICE_SOURCE_PROBLEM" for e in center.events)
    assert hass.states.get("sensor.smart_eq_current_price").state == "0.29"


async def test_price_entity_with_nordpool_attributes(hass, halo):
    start = dt_util.start_of_local_day()
    hass.states.async_set("sensor.nordpool", "25.0", {"raw_today": [
        {"start": (start + timedelta(hours=h)).isoformat(),
         "end": (start + timedelta(hours=h + 1)).isoformat(), "value": 20 + h}
        for h in range(24)]})
    entry = await _setup(hass, {"price_source": "entity", "price_entity": "sensor.nordpool"})
    await hass.async_block_till_done()
    schedule = entry.runtime_data.engine.price_schedule
    assert len(schedule.slots) == 24
    assert schedule.slots[0].eur_per_kwh == 0.2


async def test_report_service_and_authenticated_download(hass, halo, hass_client, tmp_path,
                                                         hass_ws_client):
    entry = await _setup(hass, {})
    center = entry.runtime_data
    with patch.object(type(center), "data_dir", new=tmp_path), \
            patch.object(hass.config, "path", side_effect=lambda *p: str(tmp_path.joinpath(
                *p[1:]))):
        result = await hass.services.async_call(
            DOMAIN, "create_report", {"period": "month", "year": 2026, "month": 10},
            blocking=True, return_response=True)
        assert result["file"] == "smart-eq-2026-10.pdf"
        year = await hass.services.async_call(
            DOMAIN, "create_report", {"period": "year", "year": 2026}, blocking=True,
            return_response=True)
        assert year["file"] == "smart-eq-2026.pdf"
        client = await hass_client()
        response = await client.get(result["url"])
        assert response.status == 200
        assert (await response.read()).startswith(b"%PDF")
        assert (await client.get("/api/smart_eq_charging/report/..%2Fsecrets.yaml")).status \
            in (400, 404)
        ws = await hass_ws_client(hass)
        await ws.send_json({"id": 1, "type": f"{DOMAIN}/list_reports"})
        msg = await ws.receive_json()
        assert {i["file"] for i in msg["result"]["items"]} == {"smart-eq-2026-10.pdf",
                                                              "smart-eq-2026.pdf"}


async def test_download_requires_auth(hass, halo, hass_client_no_auth):
    await _setup(hass, {})
    client = await hass_client_no_auth()
    response = await client.get("/api/smart_eq_charging/report/smart-eq-2026-10.pdf")
    assert response.status == 401


async def test_monthly_report_on_the_first(hass, halo, tmp_path):
    entry = await _setup(hass, {})
    center = entry.runtime_data
    with patch.object(type(center), "data_dir", new=tmp_path):
        first = dt_util.now().replace(year=2026, month=11, day=1, hour=6, minute=0)
        report = await center.async_monthly_report(first)
    assert report["file"] == "smart-eq-2026-10.pdf"
    assert any(e["code"] == "REPORT_CREATED" for e in center.events)


async def test_options_prices_step_validates(hass, halo):
    entry = await _setup(hass, {})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "prices"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "price_source": "tibber", "price_optimization": True, "price_blocks": 1})
    assert result["errors"] == {"base": "tibber_missing"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "price_source": "entity", "price_optimization": True, "price_blocks": 1})
    assert result["errors"] == {"base": "price_entity_missing"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "price_source": "fixed", "price_optimization": True, "price_blocks": 2})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["price_blocks"] == 2
