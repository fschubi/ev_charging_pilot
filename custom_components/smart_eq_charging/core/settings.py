"""All tunable settings of masterplan §13.2 as one typed object.

The options flow stores a flat dict; :func:`Settings.from_options` turns it
into typed values with defaults. Replay uses the very same function, so a
replay runs with exactly the settings the live system had.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from typing import Any

from .costs import PricePoint


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    LIVE = "live"
    REPLAY = "replay"


class ClimateAfterTarget(StrEnum):
    ALLOW_TOPUP = "allow_topup"
    BATTERY_ONLY = "battery_only"
    ENFORCE_TARGET = "enforce_target"


class OdometerSource(StrEnum):
    MANUAL = "manual"
    OVMS = "ovms"


# Flat option keys – the single reference for the options flow.
OPT_MODE = "mode"
OPT_CP_PULSE_S = "cp_pulse_s"
OPT_CP_MASK_GRACE_S = "cp_mask_grace_s"
OPT_CP_FAILSAFE_VERIFIED = "cp_failsafe_verified"
OPT_POWER_THRESHOLD_W = "power_threshold_w"
OPT_STABLE_SAMPLES = "stable_samples"
OPT_STABLE_MIN_S = "stable_min_s"
OPT_LOSS_TIMEOUT_S = "loss_timeout_s"
OPT_MIN_SWITCH_INTERVAL_S = "min_switch_interval_s"
OPT_CONFIRM_TIMEOUT_S = "confirm_timeout_s"
OPT_FINISHED_STATUSES = "finished_statuses"
OPT_START_DETECTION_WAIT_S = "start_detection_wait_s"
OPT_OVMS_ENABLED = "ovms_enabled"
OPT_OVMS_WAIT_S = "ovms_wait_s"
OPT_CP_FALLBACK_ENABLED = "cp_fallback_enabled"
OPT_POST_CP_WAIT_S = "post_cp_wait_s"
OPT_MAX_OVMS_ATTEMPTS = "max_ovms_attempts_per_window"
OPT_MAX_CP_ATTEMPTS = "max_cp_attempts_per_window"
OPT_MIN_GAP_WAKEUPS_S = "min_gap_between_wakeups_s"
OPT_CAPACITY_KWH = "usable_capacity_kwh"
OPT_EFFICIENCY = "charge_efficiency"
OPT_MAX_POWER_KW = "max_power_kw"
OPT_VEHICLE_CHARGER_KW = "vehicle_charger_kw"
OPT_GRID_LIMIT_KW = "grid_limit_kw"
OPT_SAFETY_MARGIN_MIN = "safety_margin_min"
OPT_CLIMATE_ENABLED = "climate_enabled"
OPT_CLIMATE_MIN_SOC = "climate_min_soc_pct"
OPT_CLIMATE_AFTER_TARGET = "climate_after_target_soc"
OPT_CLIMATE_VERY_COLD_BELOW = "climate_very_cold_below_c"
OPT_CLIMATE_COLD_BELOW = "climate_cold_below_c"
OPT_CLIMATE_COOL_BELOW = "climate_cool_below_c"
OPT_CLIMATE_WARM_ABOVE = "climate_warm_above_c"
OPT_CLIMATE_VERY_COLD_MIN = "climate_very_cold_min"
OPT_CLIMATE_COLD_MIN = "climate_cold_min"
OPT_CLIMATE_COOL_MIN = "climate_cool_min"
OPT_CLIMATE_WARM_MIN = "climate_warm_min"
OPT_MAX_AGE_HALO_POWER_S = "max_age_halo_power_s"
OPT_MAX_AGE_HALO_ENERGY_S = "max_age_halo_energy_s"
OPT_MAX_AGE_VEHICLE_CHARGING_S = "max_age_vehicle_charging_s"
OPT_MAX_AGE_SOC_S = "max_age_soc_s"
OPT_MAX_AGE_ODOMETER_S = "max_age_odometer_s"
OPT_MAX_AGE_TEMPERATURE_S = "max_age_temperature_s"
OPT_PLUG_REMINDER_TIME = "plug_reminder_time"
OPT_NOTIFY_START_FAILED = "notify_start_failed"
OPT_NOTIFY_CP = "notify_cp"
OPT_NOTIFY_PLAN_INFEASIBLE = "notify_plan_infeasible"
OPT_NOTIFY_PLUG_REMINDER = "notify_plug_reminder"
OPT_NOTIFY_HEALTH = "notify_health"
OPT_NOTIFY_HV_CYCLES = "notify_hv_cycles"
OPT_NOTIFY_PLUG_IN = "notify_plug_in_action"
OPT_ODOMETER_SOURCE = "odometer_source"
OPT_TRIP_MERGE_GAP_MIN = "trip_merge_gap_min"
OPT_EVENT_RETENTION_DAYS = "event_retention_days"
OPT_HV_CYCLES_WARN_PER_DAY = "hv_cycles_warn_per_day"
OPT_PRICE_HISTORY = "price_history"
OPT_INTERVAL_MIN = "interval_min"
OPT_OVMS_WAKEUP_COMMAND = "ovms_wakeup_command"
OPT_OVMS_CLIMATE_COMMAND = "ovms_climate_command"
OPT_OVMS_CLIMATE_STOP_COMMAND = "ovms_climate_stop_command"

DEFAULT_OPTIONS: dict[str, Any] = {
    OPT_MODE: RunMode.DRY_RUN.value,
    OPT_CP_PULSE_S: 10,
    OPT_CP_MASK_GRACE_S: 30,
    OPT_CP_FAILSAFE_VERIFIED: False,
    OPT_POWER_THRESHOLD_W: 300,
    OPT_STABLE_SAMPLES: 2,
    OPT_STABLE_MIN_S: 20,
    OPT_LOSS_TIMEOUT_S: 180,
    OPT_MIN_SWITCH_INTERVAL_S: 120,
    OPT_CONFIRM_TIMEOUT_S: 90,
    OPT_FINISHED_STATUSES: "",
    OPT_START_DETECTION_WAIT_S: 60,
    OPT_OVMS_ENABLED: False,
    OPT_OVMS_WAIT_S: 45,
    OPT_CP_FALLBACK_ENABLED: True,
    OPT_POST_CP_WAIT_S: 60,
    OPT_MAX_OVMS_ATTEMPTS: 1,
    OPT_MAX_CP_ATTEMPTS: 1,
    OPT_MIN_GAP_WAKEUPS_S: 120,
    OPT_CAPACITY_KWH: 16.7,
    OPT_EFFICIENCY: 0.88,
    OPT_MAX_POWER_KW: 11.0,
    OPT_VEHICLE_CHARGER_KW: 4.6,
    OPT_GRID_LIMIT_KW: 0.0,
    OPT_SAFETY_MARGIN_MIN: 20,
    OPT_CLIMATE_ENABLED: False,
    OPT_CLIMATE_MIN_SOC: 35,
    OPT_CLIMATE_AFTER_TARGET: ClimateAfterTarget.ALLOW_TOPUP.value,
    OPT_CLIMATE_VERY_COLD_BELOW: 0.0,
    OPT_CLIMATE_COLD_BELOW: 8.0,
    OPT_CLIMATE_COOL_BELOW: 15.0,
    OPT_CLIMATE_WARM_ABOVE: 24.0,
    OPT_CLIMATE_VERY_COLD_MIN: 15,
    OPT_CLIMATE_COLD_MIN: 10,
    OPT_CLIMATE_COOL_MIN: 5,
    OPT_CLIMATE_WARM_MIN: 10,
    OPT_MAX_AGE_HALO_POWER_S: 300,
    OPT_MAX_AGE_HALO_ENERGY_S: 600,
    OPT_MAX_AGE_VEHICLE_CHARGING_S: 300,
    OPT_MAX_AGE_SOC_S: 600,
    OPT_MAX_AGE_ODOMETER_S: 3600,
    OPT_MAX_AGE_TEMPERATURE_S: 900,
    OPT_PLUG_REMINDER_TIME: "21:00:00",
    OPT_NOTIFY_START_FAILED: True,
    OPT_NOTIFY_CP: True,
    OPT_NOTIFY_PLAN_INFEASIBLE: True,
    OPT_NOTIFY_PLUG_REMINDER: True,
    OPT_NOTIFY_HEALTH: True,
    OPT_NOTIFY_HV_CYCLES: True,
    OPT_NOTIFY_PLUG_IN: True,
    OPT_ODOMETER_SOURCE: OdometerSource.MANUAL.value,
    OPT_TRIP_MERGE_GAP_MIN: 10,
    OPT_EVENT_RETENTION_DAYS: 90,
    OPT_HV_CYCLES_WARN_PER_DAY: 10,
    OPT_PRICE_HISTORY: [{"valid_from": "2026-10-01", "eur_per_kwh": 0.29}],
    OPT_INTERVAL_MIN: 15,
    # OVMS commands stay unused until ovms_enabled – never send untested ones (§1.2).
    OPT_OVMS_WAKEUP_COMMAND: "",
    OPT_OVMS_CLIMATE_COMMAND: "homelink {level}",
    OPT_OVMS_CLIMATE_STOP_COMMAND: "",
}


@dataclass(frozen=True, slots=True)
class ClimateProfiles:
    """Outside temperature → duration in minutes (§9.3). 0 = no climate."""

    very_cold_below_c: float = 0.0
    cold_below_c: float = 8.0
    cool_below_c: float = 15.0
    warm_above_c: float = 24.0
    very_cold_min: int = 15
    cold_min: int = 10
    cool_min: int = 5
    warm_min: int = 10

    def duration_for(self, outside_c: float) -> int:
        if outside_c < self.very_cold_below_c:
            return self.very_cold_min
        if outside_c < self.cold_below_c:
            return self.cold_min
        if outside_c < self.cool_below_c:
            return self.cool_min
        if outside_c > self.warm_above_c:
            return self.warm_min
        return 0


@dataclass(frozen=True, slots=True)
class MaxAges:
    halo_power_s: float = 300
    halo_energy_s: float = 600
    vehicle_charging_s: float = 300
    soc_s: float = 600
    odometer_s: float = 3600
    temperature_s: float = 900


@dataclass(frozen=True, slots=True)
class NotifyCategories:
    start_failed: bool = True
    cp: bool = True
    plan_infeasible: bool = True
    plug_reminder: bool = True
    health: bool = True
    hv_cycles: bool = True
    plug_in_action: bool = True


@dataclass(frozen=True, slots=True)
class Settings:
    mode: RunMode = RunMode.DRY_RUN
    cp_pulse_s: int = 10
    cp_mask_grace_s: float = 30
    cp_failsafe_verified: bool = False
    power_threshold_w: float = 300
    stable_samples: int = 2
    stable_min_s: float = 20
    loss_timeout_s: float = 180
    min_switch_interval_s: float = 120
    confirm_timeout_s: float = 90
    finished_statuses: tuple[str, ...] = ()
    start_detection_wait_s: float = 60
    ovms_enabled: bool = False
    ovms_wait_s: float = 45
    cp_fallback_enabled: bool = True
    post_cp_wait_s: float = 60
    max_ovms_attempts: int = 1
    max_cp_attempts: int = 1
    min_gap_between_wakeups_s: float = 120
    usable_capacity_kwh: float = 16.7
    charge_efficiency: float = 0.88
    max_power_kw: float = 11.0
    vehicle_charger_kw: float = 4.6
    grid_limit_kw: float | None = None
    safety_margin_min: int = 20
    climate_enabled: bool = False
    climate_min_soc_pct: float = 35
    climate_after_target: ClimateAfterTarget = ClimateAfterTarget.ALLOW_TOPUP
    climate_profiles: ClimateProfiles = field(default_factory=ClimateProfiles)
    max_ages: MaxAges = field(default_factory=MaxAges)
    plug_reminder_time: time = time(21, 0)
    notify: NotifyCategories = field(default_factory=NotifyCategories)
    odometer_source: OdometerSource = OdometerSource.MANUAL
    trip_merge_gap_min: int = 10
    event_retention_days: int = 90
    hv_cycles_warn_per_day: int = 10
    price_history: tuple[PricePoint, ...] = (PricePoint(date(2026, 10, 1), 0.29),)
    interval_min: int = 15
    ovms_wakeup_command: str = ""
    ovms_climate_command: str = "homelink {level}"
    ovms_climate_stop_command: str = ""

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> Settings:
        o = {**DEFAULT_OPTIONS, **{k: v for k, v in options.items() if v is not None}}
        grid = float(o[OPT_GRID_LIMIT_KW] or 0)
        prices = tuple(
            PricePoint(date.fromisoformat(str(p["valid_from"])), float(p["eur_per_kwh"]))
            for p in o[OPT_PRICE_HISTORY]
        ) or (PricePoint(date(2026, 10, 1), 0.29),)
        return cls(
            mode=RunMode(o[OPT_MODE]),
            cp_pulse_s=int(o[OPT_CP_PULSE_S]),
            cp_mask_grace_s=float(o[OPT_CP_MASK_GRACE_S]),
            cp_failsafe_verified=bool(o[OPT_CP_FAILSAFE_VERIFIED]),
            power_threshold_w=float(o[OPT_POWER_THRESHOLD_W]),
            stable_samples=int(o[OPT_STABLE_SAMPLES]),
            stable_min_s=float(o[OPT_STABLE_MIN_S]),
            loss_timeout_s=float(o[OPT_LOSS_TIMEOUT_S]),
            min_switch_interval_s=float(o[OPT_MIN_SWITCH_INTERVAL_S]),
            confirm_timeout_s=float(o[OPT_CONFIRM_TIMEOUT_S]),
            finished_statuses=tuple(
                s.strip() for s in str(o[OPT_FINISHED_STATUSES]).split(",") if s.strip()
            ),
            start_detection_wait_s=float(o[OPT_START_DETECTION_WAIT_S]),
            ovms_enabled=bool(o[OPT_OVMS_ENABLED]),
            ovms_wait_s=float(o[OPT_OVMS_WAIT_S]),
            cp_fallback_enabled=bool(o[OPT_CP_FALLBACK_ENABLED]),
            post_cp_wait_s=float(o[OPT_POST_CP_WAIT_S]),
            max_ovms_attempts=int(o[OPT_MAX_OVMS_ATTEMPTS]),
            max_cp_attempts=int(o[OPT_MAX_CP_ATTEMPTS]),
            min_gap_between_wakeups_s=float(o[OPT_MIN_GAP_WAKEUPS_S]),
            usable_capacity_kwh=float(o[OPT_CAPACITY_KWH]),
            charge_efficiency=float(o[OPT_EFFICIENCY]),
            max_power_kw=float(o[OPT_MAX_POWER_KW]),
            vehicle_charger_kw=float(o[OPT_VEHICLE_CHARGER_KW]),
            grid_limit_kw=grid if grid > 0 else None,
            safety_margin_min=int(o[OPT_SAFETY_MARGIN_MIN]),
            climate_enabled=bool(o[OPT_CLIMATE_ENABLED]),
            climate_min_soc_pct=float(o[OPT_CLIMATE_MIN_SOC]),
            climate_after_target=ClimateAfterTarget(o[OPT_CLIMATE_AFTER_TARGET]),
            climate_profiles=ClimateProfiles(
                very_cold_below_c=float(o[OPT_CLIMATE_VERY_COLD_BELOW]),
                cold_below_c=float(o[OPT_CLIMATE_COLD_BELOW]),
                cool_below_c=float(o[OPT_CLIMATE_COOL_BELOW]),
                warm_above_c=float(o[OPT_CLIMATE_WARM_ABOVE]),
                very_cold_min=int(o[OPT_CLIMATE_VERY_COLD_MIN]),
                cold_min=int(o[OPT_CLIMATE_COLD_MIN]),
                cool_min=int(o[OPT_CLIMATE_COOL_MIN]),
                warm_min=int(o[OPT_CLIMATE_WARM_MIN]),
            ),
            max_ages=MaxAges(
                halo_power_s=float(o[OPT_MAX_AGE_HALO_POWER_S]),
                halo_energy_s=float(o[OPT_MAX_AGE_HALO_ENERGY_S]),
                vehicle_charging_s=float(o[OPT_MAX_AGE_VEHICLE_CHARGING_S]),
                soc_s=float(o[OPT_MAX_AGE_SOC_S]),
                odometer_s=float(o[OPT_MAX_AGE_ODOMETER_S]),
                temperature_s=float(o[OPT_MAX_AGE_TEMPERATURE_S]),
            ),
            plug_reminder_time=time.fromisoformat(str(o[OPT_PLUG_REMINDER_TIME])),
            notify=NotifyCategories(
                start_failed=bool(o[OPT_NOTIFY_START_FAILED]),
                cp=bool(o[OPT_NOTIFY_CP]),
                plan_infeasible=bool(o[OPT_NOTIFY_PLAN_INFEASIBLE]),
                plug_reminder=bool(o[OPT_NOTIFY_PLUG_REMINDER]),
                health=bool(o[OPT_NOTIFY_HEALTH]),
                hv_cycles=bool(o[OPT_NOTIFY_HV_CYCLES]),
                plug_in_action=bool(o[OPT_NOTIFY_PLUG_IN]),
            ),
            odometer_source=OdometerSource(o[OPT_ODOMETER_SOURCE]),
            trip_merge_gap_min=int(o[OPT_TRIP_MERGE_GAP_MIN]),
            event_retention_days=int(o[OPT_EVENT_RETENTION_DAYS]),
            hv_cycles_warn_per_day=int(o[OPT_HV_CYCLES_WARN_PER_DAY]),
            price_history=prices,
            interval_min=int(o[OPT_INTERVAL_MIN]),
            ovms_wakeup_command=str(o[OPT_OVMS_WAKEUP_COMMAND] or ""),
            ovms_climate_command=str(o[OPT_OVMS_CLIMATE_COMMAND] or ""),
            ovms_climate_stop_command=str(o[OPT_OVMS_CLIMATE_STOP_COMMAND] or ""),
        )
