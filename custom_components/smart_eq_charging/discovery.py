"""Find the Halo, Shelly, OVMS and push entities automatically for the config flow.

Nothing is hard-coded into the integration (§1.1 rule 12): discovery only
*suggests* entities, the user confirms every field. Matching works on the
entity registry (integration platform), entity IDs, names, device classes
and units, so renamed entities are found as long as the integration is right.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_NOTIFY_SERVICE, CONF_SHELLY_HOST
from .core.inputs import Inp

HALO_PLATFORMS = ("chargeamps", "chargeamps_halo", "charge_amps")
HALO_WORDS = ("halo", "chargeamps", "charge_amps", "wallbox")
CP_WORDS = ("cp_unterbrechung", "cp_relay", "control_pilot", "_cp_", "cp ", "pilot")


@dataclass(frozen=True, slots=True)
class Candidate:
    entity_id: str
    platform: str | None = None
    device_class: str | None = None
    unit: str | None = None
    name: str = ""
    config_entry_id: str | None = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]

    @property
    def text(self) -> str:
        return f"{self.entity_id} {self.name}".lower().replace(" ", "_")

    def has(self, *words: str) -> bool:
        return any(w in self.text for w in words)


def _best(candidates: list[Candidate], score) -> Candidate | None:
    scored = [(score(c), c) for c in candidates]
    scored = [(s, c) for s, c in scored if s > 0]
    if not scored:
        return None
    scored.sort(key=lambda sc: (-sc[0], sc[1].entity_id))
    return scored[0][1]


def _halo(c: Candidate) -> bool:
    # The Shelly in the CP line is often named after the wallbox – never take it.
    if c.platform == "shelly" or c.has(*CP_WORDS):
        return False
    return (c.platform or "") in HALO_PLATFORMS or c.has(*HALO_WORDS)


def _phase(c: Candidate) -> bool:
    return c.has("_l1", "_l2", "_l3", "phase")


# Each rule returns a score > 0 for a plausible entity; higher is better.
HALO_RULES = {
    Inp.CHARGER_ENABLE: lambda c: c.domain == "switch" and _halo(c) and not c.has(
        "schedule", "zeitplan", "light", "dimmer", "led", "lock") and (
        3 if c.has("connector") else 1),
    Inp.CABLE_CONNECTED: lambda c: c.domain == "binary_sensor" and _halo(c) and c.has(
        "cable", "kabel", "plug", "connected") and (3 if c.has("cable", "kabel") else 1),
    Inp.CHARGE_POWER: lambda c: c.domain == "sensor" and _halo(c) and not _phase(c) and (
        c.device_class == "power" or c.unit in ("W", "kW") or c.has("power", "leistung")) and (
        3 if c.has("connector") else 2),
    Inp.TOTAL_ENERGY: lambda c: c.domain == "sensor" and _halo(c) and (
        c.device_class == "energy" or c.unit in ("kWh", "Wh")) and (
        3 if c.has("total", "gesamt") else 1),
    Inp.CHARGER_STATUS: lambda c: c.domain == "sensor" and _halo(c) and c.has("status") and (
        3 if c.has("connector") else 1),
    Inp.MAX_CURRENT: lambda c: c.domain in ("number", "sensor") and _halo(c) and c.has(
        "max_current", "maximum_current", "current_limit") and (3 if c.domain == "number" else 1),
    Inp.CABLE_LOCK: lambda c: _halo(c) and (c.domain == "lock" or c.has("cable_lock")) and (
        3 if c.domain == "lock" else 1),
    Inp.INTERNAL_SCHEDULE: lambda c: c.domain == "switch" and _halo(c) and c.has(
        "schedule", "zeitplan") and 2,
}

# Standard OVMS v3 metric names as they appear in MQTT entity IDs.
OVMS_RULES: dict[Inp, tuple[str, ...]] = {
    Inp.OVMS_SOC: ("v_b_soc", "_soc"),
    Inp.OVMS_SOH: ("v_b_soh", "xsq_bms_soh", "_soh"),
    Inp.OVMS_RANGE: ("v_b_range_est", "v_b_range_ideal", "range"),
    Inp.OVMS_ODOMETER: ("v_p_odometer", "odometer"),
    Inp.OVMS_CHARGING: ("v_c_charging", "charging"),
    Inp.OVMS_CHARGE_POWER: ("xsq_v_charge_bcb_power", "v_c_power", "xsq_obl_power"),
    Inp.OVMS_BATTERY_TEMP: ("v_b_temp", "battery_temp"),
    Inp.OVMS_HV_CYCLES: ("xsq_bms_contactor_cycles", "contactor_cycles"),
    Inp.OVMS_VEHICLE_ON: ("v_e_on", "v_e_awake"),
    Inp.OVMS_OUTSIDE_TEMP: ("v_e_temp", "ambient", "outside"),
    Inp.OVMS_ENERGY_USED: ("xsq_v_energy_used", "v_b_energy_used"),
    Inp.OVMS_ENERGY_RECD: ("xsq_v_energy_recd", "v_b_energy_recd"),
    Inp.OVMS_AUX_CONSUMPTION: ("xsq_v_aux_consumption", "aux"),
    Inp.OVMS_12V: ("v_b_12v_voltage", "12v"),
}


def _ovms_rule(inp: Inp, words: tuple[str, ...]):
    def score(c: Candidate) -> int:
        if not c.has("ovms") or c.domain not in ("sensor", "binary_sensor"):
            return 0
        if inp is Inp.OVMS_SOC and c.has("soh"):
            return 0
        for rank, word in enumerate(words):
            if word in c.text.replace(".", "_"):
                return len(words) - rank + 1
        return 0
    return score


def suggest(candidates: list[Candidate]) -> dict[str, str]:
    """Pure matching: map config keys to the most plausible entity IDs."""
    found: dict[str, str] = {}
    used: set[str] = set()
    for inp, rule in {**HALO_RULES,
                      **{i: _ovms_rule(i, w) for i, w in OVMS_RULES.items()}}.items():
        best = _best([c for c in candidates if c.entity_id not in used], rule)
        if best is not None:
            found[inp.value] = best.entity_id
            used.add(best.entity_id)
    relay = _best(candidates, lambda c: c.domain == "switch" and c.platform in (
        "shelly", None) and c.has(*CP_WORDS) and (3 if c.platform == "shelly" else 1))
    if relay is not None:
        found[Inp.CP_RELAY.value] = relay.entity_id
    weather = [c for c in candidates if c.domain == "weather"]
    if len(weather) == 1:
        found[Inp.WEATHER.value] = weather[0].entity_id
    return found


def async_discover(hass: HomeAssistant) -> dict[str, Any]:
    """Collect candidates from the registry and the state machine, then suggest."""
    registry = er.async_get(hass)
    candidates: list[Candidate] = []
    for state in hass.states.async_all():
        entry = registry.async_get(state.entity_id)
        candidates.append(Candidate(
            entity_id=state.entity_id,
            platform=entry.platform if entry else None,
            device_class=state.attributes.get("device_class"),
            unit=state.attributes.get("unit_of_measurement"),
            name=str(state.attributes.get("friendly_name") or ""),
            config_entry_id=entry.config_entry_id if entry else None,
        ))
    found: dict[str, Any] = suggest(candidates)

    relay = found.get(Inp.CP_RELAY.value)
    if relay:
        entry_id = next((c.config_entry_id for c in candidates if c.entity_id == relay), None)
        config_entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if config_entry and config_entry.domain == "shelly" and config_entry.data.get("host"):
            found[CONF_SHELLY_HOST] = config_entry.data["host"]

    phones = sorted(name for name in hass.services.async_services().get("notify", {})
                    if name.startswith("mobile_app_"))
    if len(phones) == 1:
        found[CONF_NOTIFY_SERVICE] = f"notify.{phones[0]}"
    return found
