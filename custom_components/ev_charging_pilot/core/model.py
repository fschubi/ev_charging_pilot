"""Value objects shared by every layer of the core (masterplan §4.2, §7.1, §8.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class Clock(Protocol):
    """Injected time source. Must return timezone-aware datetimes."""

    def now(self) -> datetime: ...


class SystemClock:
    """Wall clock in UTC – the default outside of tests."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class Quality(StrEnum):
    """Quality levels of a measured value (§7.2)."""

    GOOD = "GOOD"
    LAST_KNOWN_VALID = "LAST_KNOWN_VALID"
    STALE = "STALE"
    ESTIMATED = "ESTIMATED"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"

    @property
    def usable_for_control(self) -> bool:
        """May a switching decision (e.g. a shutdown) rely on this value?"""
        return self is Quality.GOOD

    @property
    def usable_for_planning(self) -> bool:
        """May a plan or estimate rely on this value?"""
        return self in (Quality.GOOD, Quality.LAST_KNOWN_VALID, Quality.ESTIMATED)


@dataclass(frozen=True, slots=True)
class Value:
    """A measured value with source, timestamp and quality (§7.1)."""

    raw: Any
    normalized: Any
    source: str
    updated_at: datetime | None
    quality: Quality = Quality.GOOD
    unit: str | None = None

    def age_s(self, now: datetime) -> float | None:
        if self.updated_at is None:
            return None
        return (now - self.updated_at).total_seconds()

    @property
    def available(self) -> bool:
        return self.quality not in (Quality.UNAVAILABLE, Quality.INVALID)

    def with_quality(self, quality: Quality) -> Value:
        return Value(
            raw=self.raw,
            normalized=self.normalized,
            source=self.source,
            updated_at=self.updated_at,
            quality=quality,
            unit=self.unit,
        )

    @classmethod
    def unavailable(cls, source: str) -> Value:
        return cls(raw=None, normalized=None, source=source, updated_at=None,
                   quality=Quality.UNAVAILABLE)


class Reason(StrEnum):
    """Why the desired state is what it is (§4.2, §10.4)."""

    SAFETY_LOCK = "safety_lock"
    OVERRIDE = "override"
    RFID = "rfid"
    ONE_SHOT = "one_shot"
    TARGET_SOC_REACHED = "target_soc_reached"
    CLIMATE = "climate"
    SCHEDULE = "schedule"
    DEFAULT_OFF = "default_off"
    AUTOMATION_OFF = "automation_off"


@dataclass(frozen=True, slots=True)
class ClimateRequest:
    """Run the OVMS climate for ``duration_min`` starting at ``start_at`` (§9)."""

    duration_min: int
    start_at: datetime
    until: datetime

    @property
    def key(self) -> str:
        return f"{self.start_at.isoformat()}/{self.duration_min}"


@dataclass(frozen=True, slots=True)
class Desired:
    """The target state the executor reconciles against (§4.2).

    ``charger_enabled is None`` means "do not touch the Halo".
    """

    charger_enabled: bool | None
    reason: Reason
    source_id: str | None = None
    valid_until: datetime | None = None
    climate: ClimateRequest | None = None
    # False: topping up after the target was reached – never wake the car for that.
    wake_allowed: bool = True
    # Charging current to set at the wallbox (None = leave it as it is).
    current_a: int | None = None

    @property
    def window_key(self) -> str:
        """Identifies one charging window – wakeup attempts are counted per key."""
        until = self.valid_until.isoformat() if self.valid_until else "-"
        return f"{self.reason}|{self.source_id or '-'}|{until}"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Category(StrEnum):
    CHARGING = "charging"
    WAKEUP = "wakeup"
    CP = "cp"
    CLIMATE = "climate"
    HEALTH = "health"
    CONFIG = "config"
    USER = "user"


@dataclass(frozen=True, slots=True)
class Event:
    """One entry of the event log (§8.5)."""

    timestamp: datetime
    category: Category
    severity: Severity
    code: str
    message: str
    session_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "category": str(self.category),
            "severity": str(self.severity),
            "code": self.code,
            "message": self.message,
            "session_id": self.session_id,
            "data": dict(self.data),
        }
