"""System health: HEALTHY / DEGRADED / ERROR (§7.5, §3.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class HealthInputs:
    """Everything health looks at. ``None`` means "not configured / unknown"."""

    halo_available: bool
    in_charge_window: bool = False
    cp_configured: bool = False
    shelly_available: bool | None = None
    cp_relay_on: bool | None = None
    cp_pulse_running: bool = False
    cp_not_restored: bool = False
    ovms_configured: bool = False
    ovms_available: bool | None = None
    soc_stale: bool = False
    temperature_missing: bool = False
    halo_internal_schedule_on: bool | None = None
    shelly_auto_on_ok: bool | None = None
    consecutive_start_failures: int = 0


@dataclass(frozen=True, slots=True)
class Health:
    status: HealthStatus
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def blocks_automation(self) -> bool:
        """Freeze all switching? An unreachable Shelly alone does not (§8.2): only
        the CP wakeup is locked, time-based charging over the Halo goes on."""
        return self.status is HealthStatus.ERROR and any(
            reason not in CP_WAKEUP_ONLY for reason in self.reasons)

    @property
    def blocks_soc_functions(self) -> bool:
        return self.status is not HealthStatus.HEALTHY and any(
            reason not in CP_WAKEUP_ONLY for reason in self.reasons)


# Errors that lock nothing but the CP wakeup (§8.2 "Shelly": charging, target SOC
# and climate continue; the executor refuses a pulse while health is ERROR).
CP_WAKEUP_ONLY = frozenset({"CP_STATE_UNKNOWN"})


REPEATED_START_FAILURES = 2


def evaluate(inputs: HealthInputs) -> Health:
    errors: list[str] = []
    degraded: list[str] = []

    if inputs.cp_configured:
        if inputs.cp_not_restored:
            errors.append("CP_NOT_RESTORED")
        elif inputs.shelly_available is False or inputs.cp_relay_on is None:
            # §3.3: an unreachable Shelly means the CP state is unknown – that
            # is an error, not a warning.
            errors.append("CP_STATE_UNKNOWN")
        elif inputs.cp_relay_on is False and not inputs.cp_pulse_running:
            errors.append("CP_OPEN")
        if inputs.shelly_auto_on_ok is False:
            degraded.append("SHELLY_CONFIG_DRIFT")
        # An unverified failsafe is not a health issue: it only keeps the CP
        # wakeup locked, which the executor enforces on its own (§3.6).

    if not inputs.halo_available:
        if inputs.in_charge_window:
            errors.append("CHARGER_UNAVAILABLE")
        else:
            degraded.append("CHARGER_UNAVAILABLE")
    if inputs.halo_internal_schedule_on:
        degraded.append("HALO_SCHEDULE_ON")

    if inputs.ovms_configured:
        if inputs.ovms_available is False:
            degraded.append("OVMS_OFFLINE")
        if inputs.soc_stale:
            degraded.append("SOC_STALE")
    if inputs.temperature_missing:
        degraded.append("TEMPERATURE_MISSING")

    if inputs.consecutive_start_failures >= REPEATED_START_FAILURES:
        errors.append("REPEATED_START_FAILURE")

    if errors:
        return Health(HealthStatus.ERROR, tuple(errors + degraded))
    if degraded:
        return Health(HealthStatus.DEGRADED, tuple(degraded))
    return Health(HealthStatus.HEALTHY)


# Plain German for pushes, events and the PDF (the panel has its own longer texts).
REASON_TEXT = {
    "CP_STATE_UNKNOWN": "Shelly (CP-Relais) nicht erreichbar",
    "CP_OPEN": "CP-Leitung offen",
    "CP_NOT_RESTORED": "CP-Relais nach dem Puls nicht zurückgestellt",
    "CHARGER_UNAVAILABLE": "Wallbox nicht erreichbar",
    "REPEATED_START_FAILURE": "mehrere Ladestarts fehlgeschlagen",
    "HALO_SCHEDULE_ON": "interner Zeitplan der Wallbox ist an",
    "SHELLY_CONFIG_DRIFT": "Shelly-Konfiguration weicht ab",
    "OVMS_OFFLINE": "Fahrzeugdaten (OVMS) fehlen",
    "SOC_STALE": "Ladestand veraltet",
    "TEMPERATURE_MISSING": "keine Außentemperatur",
}
STATUS_TEXT = {"HEALTHY": "in Ordnung", "DEGRADED": "eingeschränkt", "ERROR": "Fehler"}


def reasons_text(reasons) -> str:
    return ", ".join(REASON_TEXT.get(r, r) for r in reasons) or "keine Auffälligkeiten"
