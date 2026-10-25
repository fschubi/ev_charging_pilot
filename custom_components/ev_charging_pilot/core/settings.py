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
from .mail import MailConfig, mail_config
from .prices import parse_price_list


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    LIVE = "live"
    REPLAY = "replay"


class ClimateAfterTarget(StrEnum):
    ALLOW_TOPUP = "allow_topup"
    BATTERY_ONLY = "battery_only"
    ENFORCE_TARGET = "enforce_target"


class PriceSource(StrEnum):
    FIXED = "fixed"
    ENTITY = "entity"
    TIBBER = "tibber"


class OdometerSource(StrEnum):
    # From the vehicle data when an OVMS odometer is mapped, else manual readings.
    AUTO = "auto"
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
OPT_PRICE_SOURCE = "price_source"
OPT_PRICE_ENTITY = "price_entity"
OPT_PRICE_OPTIMIZATION = "price_optimization"
OPT_PRICE_BLOCKS = "price_blocks"
OPT_EXTERNAL_DETECTION = "external_detection"
OPT_EXTERNAL_MIN_KWH = "external_min_kwh"
OPT_EXTERNAL_SOC_JUMP = "external_soc_jump_pct"
OPT_EXTERNAL_PRICE = "external_price_eur_kwh"
OPT_EXTERNAL_PRICE_BUTTONS = "external_price_buttons"
OPT_MAIL_ENABLED = "mail_enabled"
OPT_MAIL_PROVIDER = "mail_provider"
OPT_MAIL_HOST = "mail_host"
OPT_MAIL_PORT = "mail_port"
OPT_MAIL_SECURITY = "mail_security"
OPT_MAIL_USER = "mail_user"
OPT_MAIL_PASSWORD = "mail_password"
OPT_MAIL_FROM = "mail_from"
OPT_MAIL_TO_1 = "mail_to_1"
OPT_MAIL_TO_2 = "mail_to_2"
OPT_REPORT_PUSH_TARGETS = "report_push_targets"
OPT_NOTIFY_EXTERNAL = "notify_external"
OPT_REPORT_AUTO = "report_auto_monthly"
OPT_NOTIFY_REPORT = "notify_report"
OPT_NOTIFY_WEEKLY = "notify_weekly"
OPT_MANUAL_TARGET_SOC = "manual_target_soc"
OPT_LEARN_CHARGING = "learn_charging"
OPT_TAPER_FROM_PCT = "taper_from_pct"
OPT_FULL_SOC_PCT = "full_soc_pct"
OPT_PHASES = "phases"
OPT_DEFAULT_CURRENT_A = "default_current_a"
OPT_MANUAL_CURRENT_A = "manual_current_a"
OPT_FULL_HOLD_MAX_H = "full_hold_max_h"
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
    OPT_ODOMETER_SOURCE: OdometerSource.AUTO.value,
    OPT_TRIP_MERGE_GAP_MIN: 10,
    OPT_EVENT_RETENTION_DAYS: 90,
    OPT_HV_CYCLES_WARN_PER_DAY: 10,
    OPT_PRICE_HISTORY: [{"valid_from": "2026-10-01", "eur_per_kwh": 0.29}],
    OPT_INTERVAL_MIN: 15,
    OPT_PRICE_SOURCE: PriceSource.FIXED.value,
    OPT_PRICE_ENTITY: "",
    OPT_PRICE_OPTIMIZATION: True,
    OPT_PRICE_BLOCKS: 1,
    OPT_EXTERNAL_DETECTION: True,
    OPT_EXTERNAL_MIN_KWH: 1.0,
    OPT_EXTERNAL_SOC_JUMP: 5,
    OPT_EXTERNAL_PRICE: 0.59,
    # Quick-pick buttons in the price push of a detected external charge.
    OPT_EXTERNAL_PRICE_BUTTONS: "0,39; 0,49; 0,59; 0,69",
    # Monthly report by e-mail (sent on the 1st together with the PDF).
    OPT_MAIL_ENABLED: False,
    OPT_MAIL_PROVIDER: "gmail",
    OPT_MAIL_HOST: "",
    OPT_MAIL_PORT: 587,
    OPT_MAIL_SECURITY: "starttls",
    OPT_MAIL_USER: "",
    OPT_MAIL_PASSWORD: "",
    OPT_MAIL_FROM: "",
    OPT_MAIL_TO_1: "",
    OPT_MAIL_TO_2: "",
    # Extra push targets for the monthly amount, e.g. notify.mobile_app_<phone>.
    OPT_REPORT_PUSH_TARGETS: "",
    OPT_NOTIFY_EXTERNAL: True,
    OPT_REPORT_AUTO: True,
    OPT_NOTIFY_REPORT: True,
    OPT_NOTIFY_WEEKLY: True,
    # "Jetzt laden" stops here (100 = until the car is full / unplugged).
    OPT_MANUAL_TARGET_SOC: 100,
    # Learn kWh per % and the real charging power from the own sessions.
    OPT_LEARN_CHARGING: True,
    # Above this SOC the car charges slower (smart 453: from about 80 %).
    OPT_TAPER_FROM_PCT: 80,
    # A target above this SOC is reached at most this many hours before departure,
    # even when the electricity is cheaper earlier: a full battery should not stand.
    OPT_FULL_SOC_PCT: 90,
    # Charging current: plans may set their own; 0 = leave the wallbox setting alone.
    OPT_PHASES: 3,
    OPT_DEFAULT_CURRENT_A: 0,
    OPT_MANUAL_CURRENT_A: 0,
    OPT_FULL_HOLD_MAX_H: 2.0,
    # Ready-made OVMS v3 shell commands. Nothing is sent until the user switches the
    # vehicle access to "read & write" (ovms_enabled) – §1.2.
    # "auto": "xsq wakeup" on a smart 453 (OVMS docs), the generic "wakeup" otherwise.
    OPT_OVMS_WAKEUP_COMMAND: "auto",
    OPT_OVMS_CLIMATE_COMMAND: "homelink {level}",
    OPT_OVMS_CLIMATE_STOP_COMMAND: "climatecontrol off",
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
    external: bool = True
    report: bool = True
    weekly: bool = True


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
    climate_enabled: bool = False
    climate_min_soc_pct: float = 35
    climate_after_target: ClimateAfterTarget = ClimateAfterTarget.ALLOW_TOPUP
    climate_profiles: ClimateProfiles = field(default_factory=ClimateProfiles)
    max_ages: MaxAges = field(default_factory=MaxAges)
    plug_reminder_time: time = time(21, 0)
    notify: NotifyCategories = field(default_factory=NotifyCategories)
    odometer_source: OdometerSource = OdometerSource.AUTO
    trip_merge_gap_min: int = 10
    event_retention_days: int = 90
    hv_cycles_warn_per_day: int = 10
    price_history: tuple[PricePoint, ...] = (PricePoint(date(2026, 10, 1), 0.29),)
    interval_min: int = 15
    price_source: PriceSource = PriceSource.FIXED
    price_entity: str = ""
    price_optimization: bool = True
    price_blocks: int = 1
    external_detection: bool = True
    external_min_kwh: float = 1.0
    external_soc_jump_pct: float = 5
    external_price_eur_kwh: float = 0.59
    external_price_buttons: tuple[float, ...] = (0.39, 0.49, 0.59, 0.69)
    mail_enabled: bool = False
    mail: MailConfig = field(default_factory=lambda: mail_config(
        "gmail", "", 587, "starttls", "", "", "", []))
    report_push_targets: tuple[str, ...] = ()
    report_auto_monthly: bool = True
    manual_target_soc: int = 100
    learn_charging: bool = True
    taper_from_pct: float = 80
    full_soc_pct: float = 90
    phases: int = 3
    default_current_a: int = 0
    manual_current_a: int = 0
    full_hold_max_h: float = 2.0
    ovms_wakeup_command: str = "auto"
    ovms_climate_command: str = "homelink {level}"
    ovms_climate_stop_command: str = "climatecontrol off"

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
                external=bool(o[OPT_NOTIFY_EXTERNAL]),
                report=bool(o[OPT_NOTIFY_REPORT]),
                weekly=bool(o[OPT_NOTIFY_WEEKLY]),
            ),
            odometer_source=OdometerSource(o[OPT_ODOMETER_SOURCE]),
            trip_merge_gap_min=int(o[OPT_TRIP_MERGE_GAP_MIN]),
            event_retention_days=int(o[OPT_EVENT_RETENTION_DAYS]),
            hv_cycles_warn_per_day=int(o[OPT_HV_CYCLES_WARN_PER_DAY]),
            price_history=prices,
            interval_min=_interval_divisor(int(o[OPT_INTERVAL_MIN])),
            price_source=PriceSource(o[OPT_PRICE_SOURCE]),
            price_entity=str(o[OPT_PRICE_ENTITY] or ""),
            price_optimization=bool(o[OPT_PRICE_OPTIMIZATION]),
            price_blocks=int(o[OPT_PRICE_BLOCKS]),
            external_detection=bool(o[OPT_EXTERNAL_DETECTION]),
            external_min_kwh=float(o[OPT_EXTERNAL_MIN_KWH]),
            external_soc_jump_pct=float(o[OPT_EXTERNAL_SOC_JUMP]),
            external_price_eur_kwh=float(o[OPT_EXTERNAL_PRICE]),
            external_price_buttons=parse_price_list(str(o[OPT_EXTERNAL_PRICE_BUTTONS] or "")),
            mail_enabled=bool(o[OPT_MAIL_ENABLED]),
            mail=mail_config(
                str(o[OPT_MAIL_PROVIDER] or "custom"), str(o[OPT_MAIL_HOST] or ""),
                int(o[OPT_MAIL_PORT] or 587), str(o[OPT_MAIL_SECURITY] or "starttls"),
                str(o[OPT_MAIL_USER] or ""), str(o[OPT_MAIL_PASSWORD] or ""),
                str(o[OPT_MAIL_FROM] or ""),
                [str(o[OPT_MAIL_TO_1] or ""), str(o[OPT_MAIL_TO_2] or "")]),
            report_push_targets=tuple(
                t.strip() for t in str(o[OPT_REPORT_PUSH_TARGETS] or "").split(",")
                if t.strip().startswith("notify.")),
            report_auto_monthly=bool(o[OPT_REPORT_AUTO]),
            manual_target_soc=int(o[OPT_MANUAL_TARGET_SOC]),
            learn_charging=bool(o[OPT_LEARN_CHARGING]),
            taper_from_pct=float(o[OPT_TAPER_FROM_PCT]),
            full_soc_pct=float(o[OPT_FULL_SOC_PCT]),
            phases=int(o[OPT_PHASES]),
            default_current_a=int(o[OPT_DEFAULT_CURRENT_A] or 0),
            manual_current_a=int(o[OPT_MANUAL_CURRENT_A] or 0),
            full_hold_max_h=float(o[OPT_FULL_HOLD_MAX_H]),
            ovms_wakeup_command=str(o[OPT_OVMS_WAKEUP_COMMAND] or ""),
            ovms_climate_command=str(o[OPT_OVMS_CLIMATE_COMMAND] or ""),
            ovms_climate_stop_command=str(o[OPT_OVMS_CLIMATE_STOP_COMMAND] or ""),
        )


def _interval_divisor(minutes: int) -> int:
    """Energy intervals sit on the full hour: 45 min would overlap (00:45–01:30, then
    01:00–01:45). The nearest divisor of 60 is used instead."""
    return min((5, 10, 15, 20, 30, 60), key=lambda d: (abs(d - minutes), d))
