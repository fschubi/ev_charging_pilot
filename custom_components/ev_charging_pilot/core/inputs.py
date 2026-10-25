"""Raw entity states → quality-tagged values.

The HA side (and replay) only delivers :class:`RawState` objects keyed by
:class:`Inp`. All parsing – booleans, units, unavailable states – lives here
so that live operation and replay interpret the data identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from .model import Quality, Value


class Kind(StrEnum):
    BOOL = "bool"
    POWER_W = "power_w"
    ENERGY_KWH = "energy_kwh"
    NUMBER = "number"
    TEXT = "text"
    WEATHER_TEMP = "weather_temp"


class Inp(StrEnum):
    """Every input the engine understands. Values are the config-entry keys."""

    CHARGER_ENABLE = "charger_enable"
    CABLE_CONNECTED = "cable_connected"
    CHARGE_POWER = "charge_power"
    TOTAL_ENERGY = "total_energy"
    CHARGER_STATUS = "charger_status"
    INTERNAL_SCHEDULE = "internal_schedule"
    MAX_CURRENT = "max_current"
    CABLE_LOCK = "cable_lock"
    CP_RELAY = "cp_relay"
    OVMS_SOC = "ovms_soc"
    OVMS_SOH = "ovms_soh"
    OVMS_RANGE = "ovms_range"
    OVMS_ODOMETER = "ovms_odometer"
    OVMS_CHARGING = "ovms_charging"
    OVMS_CHARGE_POWER = "ovms_charge_power"
    OVMS_BATTERY_TEMP = "ovms_battery_temp"
    OVMS_HV_CYCLES = "ovms_hv_cycles"
    OVMS_VEHICLE_ON = "ovms_vehicle_on"
    OVMS_OUTSIDE_TEMP = "ovms_outside_temp"
    OVMS_ENERGY_USED = "ovms_energy_used"
    OVMS_ENERGY_RECD = "ovms_energy_recd"
    OVMS_AUX_CONSUMPTION = "ovms_aux_consumption"
    OVMS_12V = "ovms_12v"
    OVMS_PLUG = "ovms_plug"
    OVMS_HVAC = "ovms_hvac"
    OVMS_BATTERY_POWER = "ovms_battery_power"
    OVMS_SPEED = "ovms_speed"
    OVMS_LOCKED = "ovms_locked"
    OVMS_CABIN_TEMP = "ovms_cabin_temp"
    OVMS_CHARGE_ENERGY = "ovms_charge_energy"
    OVMS_LOCATION = "ovms_location"
    OUTSIDE_TEMP = "outside_temp"
    WEATHER = "weather"


KINDS: dict[Inp, Kind] = {
    Inp.CHARGER_ENABLE: Kind.BOOL,
    Inp.CABLE_CONNECTED: Kind.BOOL,
    Inp.CHARGE_POWER: Kind.POWER_W,
    Inp.TOTAL_ENERGY: Kind.ENERGY_KWH,
    Inp.CHARGER_STATUS: Kind.TEXT,
    Inp.INTERNAL_SCHEDULE: Kind.BOOL,
    Inp.MAX_CURRENT: Kind.NUMBER,
    Inp.CABLE_LOCK: Kind.TEXT,
    Inp.CP_RELAY: Kind.BOOL,
    Inp.OVMS_SOC: Kind.NUMBER,
    Inp.OVMS_SOH: Kind.NUMBER,
    Inp.OVMS_RANGE: Kind.NUMBER,
    Inp.OVMS_ODOMETER: Kind.NUMBER,
    Inp.OVMS_CHARGING: Kind.BOOL,
    Inp.OVMS_CHARGE_POWER: Kind.POWER_W,
    Inp.OVMS_BATTERY_TEMP: Kind.NUMBER,
    Inp.OVMS_HV_CYCLES: Kind.NUMBER,
    Inp.OVMS_VEHICLE_ON: Kind.BOOL,
    Inp.OVMS_OUTSIDE_TEMP: Kind.NUMBER,
    Inp.OVMS_ENERGY_USED: Kind.ENERGY_KWH,
    Inp.OVMS_ENERGY_RECD: Kind.ENERGY_KWH,
    Inp.OVMS_AUX_CONSUMPTION: Kind.ENERGY_KWH,
    Inp.OVMS_12V: Kind.NUMBER,
    Inp.OVMS_PLUG: Kind.BOOL,
    Inp.OVMS_HVAC: Kind.BOOL,
    Inp.OVMS_BATTERY_POWER: Kind.POWER_W,
    Inp.OVMS_SPEED: Kind.NUMBER,
    Inp.OVMS_LOCKED: Kind.BOOL,
    Inp.OVMS_CABIN_TEMP: Kind.NUMBER,
    Inp.OVMS_CHARGE_ENERGY: Kind.ENERGY_KWH,
    Inp.OVMS_LOCATION: Kind.BOOL,
    Inp.OUTSIDE_TEMP: Kind.NUMBER,
    Inp.WEATHER: Kind.WEATHER_TEMP,
}

SOURCES: dict[str, str] = {"cp_relay": "shelly", "outside_temp": "ha", "weather": "weather"}

TRUE_STATES = {"on", "true", "1", "yes", "charging", "locked", "home"}
MISSING_STATES = {None, "unavailable", "unknown", "none", "None", ""}


def source_of(key: Inp) -> str:
    if key.value in SOURCES:
        return SOURCES[key.value]
    return "ovms" if key.value.startswith("ovms_") else "halo"


@dataclass(frozen=True, slots=True)
class RawState:
    """One entity state as Home Assistant (or a replay file) reports it."""

    state: str | None
    last_updated: datetime
    last_reported: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "last_updated": self.last_updated.isoformat(),
            "last_reported": self.last_reported.isoformat() if self.last_reported else None,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawState:
        reported = data.get("last_reported")
        return cls(
            state=data.get("state"),
            last_updated=datetime.fromisoformat(data["last_updated"]),
            last_reported=datetime.fromisoformat(reported) if reported else None,
            attributes=dict(data.get("attributes") or {}),
        )


def _float(text: Any) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _hv_cycles(state: Any) -> float | None:
    """smart 453: ``xsq.bms.contactor.cycles`` is a vector [max, now, consumed, diff, 1h].

    The consumed cycles (index 2) only ever rise – that is the counter to watch.
    """
    parts = [_float(p) for p in str(state).strip("[]() ").replace(";", ",").split(",")
             if p.strip()]
    if len(parts) >= 3 and parts[2] is not None:
        return parts[2]
    return parts[-1] if parts and parts[-1] is not None else None


def to_value(key: Inp, raw: RawState | None) -> Value:
    """Parse ``raw`` according to the kind of ``key``. Quality is GOOD or worse;
    age-based classification happens later in :mod:`.quality`."""
    source = source_of(key)
    if raw is None:
        return Value.unavailable(source)
    kind = KINDS[key]
    # Freshness comes from last_reported: a polled source often reports the
    # identical value again, which still proves it is current. Power samples
    # are also told apart by it (§6.2).
    stamp = raw.last_reported or raw.last_updated
    unit = raw.attributes.get("unit_of_measurement")

    if kind is Kind.WEATHER_TEMP:
        temperature = _float(raw.attributes.get("temperature"))
        if temperature is None:
            return Value.unavailable(source)
        return Value(raw.attributes.get("temperature"), temperature, source, stamp, unit="°C")

    # HA's own "unavailable"/"unknown" are always lower case. A device state such as the
    # Halo's "Unavailable" (connector locked) is a real value and must not vanish.
    original = raw.state.strip() if isinstance(raw.state, str) else raw.state
    if original in MISSING_STATES:
        return Value.unavailable(source)
    state = original.lower() if isinstance(original, str) else original
    if kind is Kind.BOOL:
        if key is Inp.OVMS_LOCKED and raw.attributes.get("device_class") == "lock" \
                and state in ("on", "off"):
            # A lock binary_sensor reports "on" for UNlocked.
            return Value(raw.state, state == "off", source, stamp)
        return Value(raw.state, state in TRUE_STATES, source, stamp)
    if kind is Kind.TEXT:
        return Value(raw.state, raw.state, source, stamp)

    number = _float(raw.state)
    if number is None and key is Inp.OVMS_HV_CYCLES:
        number = _hv_cycles(raw.state)
    if number is None:
        return Value(raw.state, None, source, stamp, Quality.INVALID, unit)
    if kind is Kind.POWER_W and unit == "kW":
        number *= 1000
        unit = "W"  # the unit always belongs to the normalized number
    elif kind is Kind.ENERGY_KWH and unit == "Wh":
        number /= 1000
        unit = "kWh"
    return Value(raw.state, number, source, stamp, unit=unit)
