"""Config and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_eq_charging.const import DOMAIN

from .conftest import DATA


async def test_user_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(DATA))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA


async def test_options_flow_rejects_preferred_below_minimum(hass, entry, halo):
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "plan_enabled": True, "weekdays": ["mon"], "mode": "fixed_start",
        "departure_time": "06:00:00", "charge_start_time": "02:00:00",
        "ready_buffer_min": 30, "minimum_departure_soc_pct": 80,
        "preferred_departure_soc_pct": 70,
    })
    assert result["step_id"] == "technical"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "preferred_below_minimum"}
