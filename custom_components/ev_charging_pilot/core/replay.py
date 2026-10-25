"""Replay: run recorded nights through the real engine (§4.3, §14.1, Gate v0.1).

A dataset holds the recorded state history of every mapped input. The
runner advances a simulated clock in fixed ticks, feeds the states that
were current at each moment into a fresh :class:`Engine` and records what
the engine *would* have done. Comparing that with the real Halo switching
in the same dataset answers the v0.1 gate question: do the decisions match
reality?
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .engine import Engine, EngineConfig
from .inputs import Inp, RawState
from .planner import WeeklySchedule
from .ports import CommandKind
from .settings import Settings

DATASET_VERSION = 1


@dataclass(slots=True)
class ReplayDataset:
    name: str
    timezone: str
    start: datetime
    end: datetime
    inputs: dict[Inp, list[RawState]]
    plans: list[dict[str, Any]] | None = None
    options: dict[str, Any] | None = None
    # The recorder stores a state only when it changes. The Halo, however, is
    # polled and re-reports identical values; stability is counted in such
    # reports (§6.2). The replay re-creates them at the measured poll rate.
    poll_interval_s: float = 60.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": DATASET_VERSION,
            "name": self.name,
            "timezone": self.timezone,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "inputs": {k.value: [r.as_dict() for r in v] for k, v in self.inputs.items()},
            "plans": self.plans,
            "options": self.options,
            "poll_interval_s": self.poll_interval_s,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplayDataset:
        if int(data.get("version", 0)) != DATASET_VERSION:
            raise ValueError(f"unsupported replay dataset version {data.get('version')}")
        inputs: dict[Inp, list[RawState]] = {}
        for key, states in (data.get("inputs") or {}).items():
            try:
                inp = Inp(key)
            except ValueError:
                continue
            inputs[inp] = sorted((RawState.from_dict(s) for s in states),
                                 key=lambda r: r.last_updated)
        return cls(
            name=str(data.get("name") or "replay"),
            timezone=str(data["timezone"]),
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            inputs=inputs,
            plans=data.get("plans"),
            options=data.get("options"),
            poll_interval_s=float(data.get("poll_interval_s") or 60.0),
        )


@dataclass(slots=True)
class ReplayResult:
    name: str
    ticks: int = 0
    commands: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    states: list[dict[str, Any]] = field(default_factory=list)
    actual_switches: list[dict[str, Any]] = field(default_factory=list)
    desired_changes: list[dict[str, Any]] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def agreement(self) -> float | None:
        total = len(self.matches) + len(self.mismatches)
        return round(len(self.matches) / total, 3) if total else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ticks": self.ticks,
            "agreement": self.agreement,
            "commands": self.commands,
            "events": self.events,
            "states": self.states,
            "actual_switches": self.actual_switches,
            "desired_changes": self.desired_changes,
            "matches": self.matches,
            "mismatches": self.mismatches,
            "sessions": self.sessions,
        }


class _Cursor:
    """The state of one input that was current at a given moment."""

    def __init__(self, states: list[RawState], poll_s: float) -> None:
        self.states = states
        self.stamps = [s.last_updated for s in states]
        self.poll = timedelta(seconds=poll_s) if poll_s > 0 else None

    def at(self, moment: datetime) -> RawState | None:
        index = bisect_right(self.stamps, moment) - 1
        if index < 0:
            return None
        state = self.states[index]
        reported = state.last_reported if state.last_reported and \
            state.last_reported <= moment else state.last_updated
        if self.poll is not None:
            polls = (moment - state.last_updated) // self.poll
            reported = max(reported, state.last_updated + polls * self.poll)
        return RawState(state.state, state.last_updated, reported, state.attributes)


def _switch_changes(states: list[RawState]) -> list[dict[str, Any]]:
    changes, previous = [], None
    for state in states:
        value = (state.state or "").lower()
        if value not in ("on", "off"):
            continue
        if previous is not None and value != previous:
            changes.append({"at": state.last_updated, "on": value == "on"})
        previous = value
    return changes


def run_replay(
    dataset: ReplayDataset,
    settings: Settings | None = None,
    *,
    tick_s: float = 5.0,
    tolerance: timedelta = timedelta(minutes=10),
    plans: list[WeeklySchedule] | None = None,
    poll_interval_s: float | None = None,
) -> ReplayResult:
    tz = ZoneInfo(dataset.timezone)
    settings = settings or Settings.from_options(dataset.options or {})
    engine = Engine(EngineConfig(
        settings=settings, tz=tz, configured=frozenset(dataset.inputs),
        cp_pulse_available=Inp.CP_RELAY in dataset.inputs))
    if plans is not None:
        engine.plans = plans
    elif dataset.plans:
        engine.plans = [WeeklySchedule.from_dict(p) for p in dataset.plans]

    poll = dataset.poll_interval_s if poll_interval_s is None else poll_interval_s
    cursors = {key: _Cursor(states, poll) for key, states in dataset.inputs.items()}
    last_desired: bool | None = None
    result = ReplayResult(dataset.name)
    # Count in UTC: local wall-clock steps skipped the extra hour of the DST change.
    now = dataset.start.astimezone(UTC)
    end = dataset.end.astimezone(UTC)
    last_state = None
    step = timedelta(seconds=tick_s)
    while now <= end:
        tick = engine.tick(now, {key: cursor.at(now) for key, cursor in cursors.items()})
        result.ticks += 1
        for command in tick.commands:
            result.commands.append({"at": now.isoformat(), "command": command.describe(),
                                    "kind": str(command.kind)})
        result.events += [e.as_dict() for e in tick.events]
        result.sessions += [s.as_dict() for s in tick.sessions]
        wanted = engine.desired.charger_enabled if engine.desired else None
        if wanted is not None and wanted != last_desired:
            result.desired_changes.append({"at": now.isoformat(), "on": wanted})
            last_desired = wanted
        state = str(engine.executor.state)
        if state != last_state:
            result.states.append({"at": now.isoformat(), "state": state,
                                  "desired": str(engine.desired.reason) if engine.desired
                                  else None})
            last_state = state
        now += step

    # A decision counts when the engine either sent the command or – because
    # reality had already switched – simply wanted the same state.
    switch_commands = [
        (datetime.fromisoformat(c["at"]), c["kind"] == CommandKind.ENABLE_CHARGER)
        for c in result.commands
        if c["kind"] in (CommandKind.ENABLE_CHARGER, CommandKind.DISABLE_CHARGER)
    ] + [(datetime.fromisoformat(d["at"]), d["on"]) for d in result.desired_changes]
    switch_commands.sort()
    for change in _switch_changes(dataset.inputs.get(Inp.CHARGER_ENABLE, [])):
        if not dataset.start <= change["at"] <= dataset.end:
            continue
        entry = {"at": change["at"].isoformat(), "on": change["on"]}
        result.actual_switches.append(entry)
        hit = next((at for at, on in switch_commands
                    if on == change["on"] and abs(at - change["at"]) <= tolerance), None)
        if hit is not None:
            result.matches.append({**entry, "engine_at": hit.isoformat(),
                                   "delta_s": round((hit - change["at"]).total_seconds())})
        else:
            result.mismatches.append(entry)
    return result
