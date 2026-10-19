"""Automatic entity discovery for the config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.ev_charging_pilot.const import DOMAIN
from custom_components.ev_charging_pilot.discovery import Candidate, suggest

# The entity IDs from masterplan §2 – the real installation.
HALO = [
    Candidate("switch.halo_wallbox_connector_1", "chargeamps"),
    Candidate("switch.halo_wallbox_connector_1_schedule", "chargeamps"),
    Candidate("switch.halo_wallbox_light", "chargeamps"),
    Candidate("binary_sensor.halo_wallbox_connector_1_cable_connected", "chargeamps"),
    Candidate("sensor.halo_wallbox_connector_1_power", "chargeamps", "power", "W"),
    Candidate("sensor.halo_wallbox_connector_1_l1_current", "chargeamps", "current", "A"),
    Candidate("sensor.halo_wallbox_connector_1_status", "chargeamps"),
    Candidate("sensor.halo_wallbox_total_energy", "chargeamps", "energy", "kWh"),
    Candidate("sensor.halo_wallbox_connector_1_energy", "chargeamps", "energy", "kWh"),
    Candidate("number.halo_wallbox_connector_1_max_current", "chargeamps"),
    Candidate("lock.halo_wallbox_connector_1_cable_lock", "chargeamps"),
    Candidate("switch.mini_1_wallbox_wallbox_cp_unterbrechung", "shelly",
              name="Mini 1 Wallbox Wallbox CP-Unterbrechung"),
    Candidate("sensor.mini_1_wallbox_wallbox_cp_unterbrechung_temperatur", "shelly",
              "temperature", "°C"),
    Candidate("switch.kitchen_light", "hue"),
    Candidate("sensor.house_power", "shelly", "power", "W"),
    # Sensors of another charging integration that mention the wallbox.
    Candidate("sensor.evcc_cstotal_wallbox_halo_charging_sessions_loadpoint_chargedenergy",
              "evcc_intg", "energy", "kWh"),
    Candidate("sensor.wallbox_halo_charge_power", "evcc_intg", "power", "kW"),
    Candidate("switch.wallbox_halo_loadpoint_enable", "evcc_intg"),
]
OVMS = [
    Candidate("sensor.ovms_smart_v_b_soc", "mqtt", "battery", "%"),
    Candidate("sensor.ovms_smart_v_b_soh", "mqtt", None, "%"),
    Candidate("sensor.ovms_smart_v_p_odometer", "mqtt", "distance", "km"),
    Candidate("binary_sensor.ovms_smart_v_c_charging", "mqtt"),
    Candidate("binary_sensor.ovms_smart_v_e_on", "mqtt"),
    Candidate("sensor.ovms_smart_xsq_bms_contactor_cycles", "mqtt"),
]


def test_suggest_maps_masterplan_entities():
    found = suggest(HALO)
    assert found == {
        "charger_enable": "switch.halo_wallbox_connector_1",
        "internal_schedule": "switch.halo_wallbox_connector_1_schedule",
        "cable_connected": "binary_sensor.halo_wallbox_connector_1_cable_connected",
        "charge_power": "sensor.halo_wallbox_connector_1_power",
        "total_energy": "sensor.halo_wallbox_total_energy",
        "charger_status": "sensor.halo_wallbox_connector_1_status",
        "max_current": "number.halo_wallbox_connector_1_max_current",
        "cable_lock": "lock.halo_wallbox_connector_1_cable_lock",
        "cp_relay": "switch.mini_1_wallbox_wallbox_cp_unterbrechung",
    }


def test_suggest_maps_ovms_metrics():
    found = suggest(HALO + OVMS)
    assert found["ovms_soc"] == "sensor.ovms_smart_v_b_soc"
    assert found["ovms_soh"] == "sensor.ovms_smart_v_b_soh"
    assert found["ovms_odometer"] == "sensor.ovms_smart_v_p_odometer"
    assert found["ovms_charging"] == "binary_sensor.ovms_smart_v_c_charging"
    assert found["ovms_vehicle_on"] == "binary_sensor.ovms_smart_v_e_on"
    assert found["ovms_hv_cycles"] == "sensor.ovms_smart_xsq_bms_contactor_cycles"


def test_suggest_maps_ovms_plug_and_location_of_the_hacs_integration():
    found = suggest([
        Candidate("sensor.car_charge_plug_detected_smart_fortwo", "ovms"),
        Candidate("binary_sensor.car_charge_port", "ovms"),
        Candidate("device_tracker.car_location", "ovms"),
        Candidate("device_tracker.franks_iphone", "mobile_app"),
    ])
    assert found["ovms_plug"] == "sensor.car_charge_plug_detected_smart_fortwo"
    assert found["ovms_location"] == "device_tracker.car_location"


def test_suggest_maps_ovms_hvac_of_the_hacs_integration():
    found = suggest([
        Candidate("switch.car_climate_control", "ovms"),
        Candidate("binary_sensor.car_hvac_active", "ovms"),
        Candidate("sensor.car_cabin_fan", "ovms"),
    ])
    assert found["ovms_hvac"] == "binary_sensor.car_hvac_active"


async def test_existing_installation_gets_the_new_ovms_inputs_once(hass):
    from custom_components.ev_charging_pilot.discovery import (
        BATTERY_POWER_DISCOVERY_DONE,
        CABIN_DISCOVERY_DONE,
        HVAC_DISCOVERY_DONE,
        LOCKED_DISCOVERY_DONE,
        PLUG_DISCOVERY_DONE,
        SPEED_DISCOVERY_DONE,
        async_discover_late,
    )

    registry = er.async_get(hass)
    registry.async_get_or_create("binary_sensor", "ovms", "hvac",
                                 suggested_object_id="car_hvac_active")
    registry.async_get_or_create("sensor", "ovms", "bpower",
                                 suggested_object_id="car_battery_power")
    registry.async_get_or_create("sensor", "ovms", "speed", suggested_object_id="car_vehicle_speed")
    registry.async_get_or_create("sensor", "ovms", "gps", suggested_object_id="car_gps_speed")
    registry.async_get_or_create("binary_sensor", "ovms", "lockbin",
                                 suggested_object_id="car_vehicle_locked")
    registry.async_get_or_create("lock", "ovms", "lock", suggested_object_id="car_vehicle_lock")
    registry.async_get_or_create("sensor", "ovms", "cabin",
                                 suggested_object_id="car_cabin_temperature")
    data = {"ovms_soc": "sensor.car_battery_level", PLUG_DISCOVERY_DONE: True}
    late = async_discover_late(hass, data)
    assert late == {"ovms_hvac": "binary_sensor.car_hvac_active", HVAC_DISCOVERY_DONE: True,
                    "ovms_battery_power": "sensor.car_battery_power",
                    BATTERY_POWER_DISCOVERY_DONE: True,
                    "ovms_speed": "sensor.car_vehicle_speed", SPEED_DISCOVERY_DONE: True,
                    "ovms_locked": "lock.car_vehicle_lock", LOCKED_DISCOVERY_DONE: True,
                    "ovms_cabin_temp": "sensor.car_cabin_temperature",
                    CABIN_DISCOVERY_DONE: True}
    assert async_discover_late(hass, {**data, **late}) == {}


def test_nothing_found_without_wallbox():
    assert suggest([Candidate("switch.kitchen_light", "hue")]) == {}


async def test_config_flow_prefills_discovered_entities(hass):
    registry = er.async_get(hass)
    shelly = MockConfigEntry(domain="shelly", data={"host": "192.0.2.44"})
    shelly.add_to_hass(hass)
    for c in HALO:
        domain, object_id = c.entity_id.split(".")
        entry = registry.async_get_or_create(
            domain, c.platform, object_id, suggested_object_id=object_id,
            config_entry=shelly if c.platform == "shelly" else None)
        attrs = {"device_class": c.device_class, "unit_of_measurement": c.unit}
        hass.states.async_set(entry.entity_id, "on" if domain == "switch" else "1",
                              {k: v for k, v in attrs.items() if v})
    async_mock_service(hass, "notify", "mobile_app_franks_iphone")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"vehicle_name": "Smarty", "dry_run": True})
    assert result["step_id"] == "halo"
    assert "9 von 8" not in result["description_placeholders"]["found"]
    assert result["description_placeholders"]["found"].startswith("8 von 8")
    # Accept the suggestions unchanged (what the user does when everything is right).
    defaults = {str(k): k.default() for k in result["data_schema"].schema
                if callable(getattr(k, "default", None)) and k.default() is not None}
    suggested = {str(k): (k.description or {}).get("suggested_value")
                 for k in result["data_schema"].schema}
    halo = {**{k: v for k, v in suggested.items() if v}, **defaults}
    assert halo["charger_enable"] == "switch.halo_wallbox_connector_1"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], halo)
    assert result["step_id"] == "shelly"
    shelly_suggest = {str(k): (k.description or {}).get("suggested_value")
                      for k in result["data_schema"].schema}
    assert shelly_suggest["cp_relay"] == "switch.mini_1_wallbox_wallbox_cp_unterbrechung"
    assert shelly_suggest["shelly_host"] == "192.0.2.44"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {k: v for k, v in shelly_suggest.items() if v})
    assert result["step_id"] == "notify"
    notify = {str(k): (k.description or {}).get("suggested_value")
              for k in result["data_schema"].schema}
    assert notify["notify_service"] == "notify.mobile_app_franks_iphone"
