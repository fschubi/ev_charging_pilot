"""Constants: config keys, defaults, events. The single reference for names."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "smart_eq_charging"
NAME: Final = "Smart EQ Charging Center"

PLATFORMS: Final = ["sensor", "binary_sensor", "switch", "button"]

STORAGE_VERSION: Final = 1
STORAGE_KEY_STATE: Final = f"{DOMAIN}.state"
STORAGE_KEY_EVENTS: Final = f"{DOMAIN}.events"

TICK_SECONDS: Final = 5
EVENT_RETENTION_DAYS: Final = 90
BUS_EVENT: Final = f"{DOMAIN}_event"

# --- Config flow: entities (§2). Always chosen via selector, never hard-coded.
CONF_CHARGER_ENABLE: Final = "charger_enable"
CONF_CABLE_CONNECTED: Final = "cable_connected"
CONF_CHARGE_POWER: Final = "charge_power"
CONF_TOTAL_ENERGY: Final = "total_energy"
CONF_CHARGER_STATUS: Final = "charger_status"
CONF_INTERNAL_SCHEDULE: Final = "internal_schedule"
CONF_CP_RELAY: Final = "cp_relay"
CONF_SHELLY_HOST: Final = "shelly_host"
CONF_OVMS_SOC: Final = "ovms_soc"
CONF_OVMS_CHARGING: Final = "ovms_charging"
CONF_NOTIFY_SERVICE: Final = "notify_service"

# --- Options flow: plan (§5.1)
CONF_PLAN_ENABLED: Final = "plan_enabled"
CONF_WEEKDAYS: Final = "weekdays"
CONF_MODE: Final = "mode"
CONF_CHARGE_START_TIME: Final = "charge_start_time"
CONF_DEPARTURE_TIME: Final = "departure_time"
CONF_READY_BUFFER_MIN: Final = "ready_buffer_min"
CONF_MIN_SOC: Final = "minimum_departure_soc_pct"
CONF_PREFERRED_SOC: Final = "preferred_departure_soc_pct"

# --- Options flow: vehicle and charger (§5.6)
CONF_CAPACITY_KWH: Final = "usable_capacity_kwh"
CONF_EFFICIENCY: Final = "charge_efficiency"
CONF_VEHICLE_CHARGER_KW: Final = "vehicle_charger_kw"
CONF_GRID_LIMIT_KW: Final = "grid_limit_kw"

# --- Options flow: executor (§6) and CP (§3)
CONF_POWER_THRESHOLD_W: Final = "power_threshold_w"
CONF_MIN_SWITCH_INTERVAL_S: Final = "min_switch_interval_s"
CONF_START_DETECTION_WAIT_S: Final = "start_detection_wait_s"
CONF_CP_PULSE_S: Final = "cp_pulse_s"
CONF_CP_FAILSAFE_VERIFIED: Final = "cp_failsafe_verified"
CONF_FINISHED_STATUSES: Final = "finished_statuses"

# --- Options flow: costs (§11)
CONF_PRICE_EUR_KWH: Final = "price_eur_kwh"

DEFAULTS: Final = {
    CONF_PLAN_ENABLED: True,
    CONF_WEEKDAYS: ["mon", "tue", "wed", "thu", "fri"],
    CONF_MODE: "departure_based",
    CONF_CHARGE_START_TIME: "03:00:00",
    CONF_DEPARTURE_TIME: "05:30:00",
    CONF_READY_BUFFER_MIN: 30,
    CONF_MIN_SOC: 80,
    CONF_PREFERRED_SOC: 90,
    CONF_CAPACITY_KWH: 16.7,
    CONF_EFFICIENCY: 0.9,
    CONF_VEHICLE_CHARGER_KW: 4.6,
    CONF_GRID_LIMIT_KW: 0.0,
    CONF_POWER_THRESHOLD_W: 300,
    CONF_MIN_SWITCH_INTERVAL_S: 120,
    CONF_START_DETECTION_WAIT_S: 60,
    CONF_CP_PULSE_S: 10,
    CONF_CP_FAILSAFE_VERIFIED: False,
    CONF_FINISHED_STATUSES: "",
    CONF_PRICE_EUR_KWH: 0.29,
}

CP_PULSE_MIN_S: Final = 5
CP_PULSE_MAX_S: Final = 15

# Event codes that trigger a push notification (§8.3) → priority.
PUSH_EVENTS: Final = {
    "CHARGE_START_FAILED": "high",
    "CHARGER_NOT_CONFIRMED": "high",
    "CHARGE_INTERRUPTED": "high",
    "CP_NOT_RESTORED": "critical",
}
HEALTH_PUSH_DEBOUNCE_S: Final = 300
