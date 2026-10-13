"""A simulated Halo + Shelly + smart for engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.smart_eq_charging.core.engine import Engine, EngineConfig, TickResult
from custom_components.smart_eq_charging.core.inputs import Inp, RawState
from custom_components.smart_eq_charging.core.ports import CommandKind
from custom_components.smart_eq_charging.core.settings import Settings

TZ = ZoneInfo("Europe/Berlin")

HALO = frozenset({Inp.CHARGER_ENABLE, Inp.CABLE_CONNECTED, Inp.CHARGE_POWER, Inp.TOTAL_ENERGY,
                  Inp.CHARGER_STATUS})
WITH_CP = HALO | {Inp.CP_RELAY}
WITH_OVMS = WITH_CP | {Inp.OVMS_SOC, Inp.OVMS_CHARGING, Inp.OVMS_ODOMETER,
                       Inp.OVMS_VEHICLE_ON, Inp.OVMS_HV_CYCLES, Inp.OVMS_OUTSIDE_TEMP,
                       Inp.OVMS_ENERGY_USED, Inp.OVMS_CHARGE_POWER}


class World:
    def __init__(self, start: datetime, *, configured=HALO, cp_pulse=False, ovms_port=False,
                 **options) -> None:
        self.now = start
        self.settings = Settings.from_options(options)
        self.engine = Engine(EngineConfig(self.settings, TZ, frozenset(configured),
                                          cp_pulse_available=cp_pulse,
                                          ovms_command_available=ovms_port))
        self.states: dict[Inp, tuple[str, dict]] = {
            Inp.CHARGER_ENABLE: ("off", {}),
            Inp.CABLE_CONNECTED: ("on", {}),
            Inp.CHARGE_POWER: ("0", {"unit_of_measurement": "W"}),
            Inp.TOTAL_ENERGY: ("1000.0", {"unit_of_measurement": "kWh"}),
            Inp.CHARGER_STATUS: ("Available", {}),
            Inp.CP_RELAY: ("on", {}),
        }
        self.updated: dict[Inp, datetime] = {k: start for k in self.states}
        self.reported: dict[Inp, datetime] = dict(self.updated)
        self.car_charges_when_enabled = True
        self.charging_power = 2300.0
        self.results: list[TickResult] = []
        self.commands: list[CommandKind] = []
        self.events: list[str] = []
        self.notifications: list[str] = []

    def set(self, key: Inp, state: str, **attributes) -> None:
        if self.states.get(key, (None,))[0] != state:
            self.updated[key] = self.now
        self.states[key] = (state, attributes or self.states.get(key, ("", {}))[1])
        self.reported[key] = self.now

    def raw(self) -> dict[Inp, RawState]:
        return {k: RawState(s, self.updated[k], self.reported[k], dict(a))
                for k, (s, a) in self.states.items()}

    def tick(self, seconds: float = 5) -> TickResult:
        self.now += timedelta(seconds=seconds)
        # The physical world: power flows while enabled and the car accepts it.
        enabled = self.states[Inp.CHARGER_ENABLE][0] == "on"
        plugged = self.states[Inp.CABLE_CONNECTED][0] == "on"
        watts = self.charging_power if enabled and plugged and self.car_charges_when_enabled \
            else 0.0
        self.set(Inp.CHARGE_POWER, f"{watts:.0f}", unit_of_measurement="W")
        energy = float(self.states[Inp.TOTAL_ENERGY][0]) + watts / 1000 * seconds / 3600
        self.set(Inp.TOTAL_ENERGY, f"{energy:.4f}", unit_of_measurement="kWh")
        result = self.engine.tick(self.now, self.raw())
        self.apply(result)
        return result

    def apply(self, result: TickResult) -> None:
        self.results.append(result)
        for command in result.commands:
            self.commands.append(command.kind)
            if command.kind is CommandKind.ENABLE_CHARGER:
                self.set(Inp.CHARGER_ENABLE, "on")
            elif command.kind is CommandKind.DISABLE_CHARGER:
                self.set(Inp.CHARGER_ENABLE, "off")
        self.events += [e.code for e in result.events]
        self.notifications += [n.category for n in result.notifications]

    def run(self, seconds: float, step: float = 5) -> None:
        for _ in range(int(seconds / step)):
            self.tick(step)
