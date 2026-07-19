"""Framework-independent timer entities and invariants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def require_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime or reject an invalid persisted instant."""
    if value.tzinfo is None:
        raise ValueError("timer timestamps must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ActiveTimer:
    """The single running time entry exposed to application clients."""

    entry_id: int
    project: str
    activity: str
    started_at: datetime
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", require_utc(self.started_at))

    def stop(self, stopped_at: datetime) -> CompletedTimer:
        """Complete this entry while enforcing chronological timestamps."""
        stopped_at = require_utc(stopped_at)
        if stopped_at < self.started_at:
            raise ValueError("a timer cannot stop before it started")
        return CompletedTimer(
            entry_id=self.entry_id,
            project=self.project,
            activity=self.activity,
            started_at=self.started_at,
            stopped_at=stopped_at,
            note=self.note,
        )


@dataclass(frozen=True, slots=True)
class CompletedTimer:
    """A completed time entry whose duration is derived from its instants."""

    entry_id: int
    project: str
    activity: str
    started_at: datetime
    stopped_at: datetime
    note: str | None = None

    def __post_init__(self) -> None:
        started_at = require_utc(self.started_at)
        stopped_at = require_utc(self.stopped_at)
        if stopped_at < started_at:
            raise ValueError("a timer cannot stop before it started")
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "stopped_at", stopped_at)

    @property
    def duration(self) -> timedelta:
        """Return the duration derived from the stored timestamps."""
        return self.stopped_at - self.started_at
