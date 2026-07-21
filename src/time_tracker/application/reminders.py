"""Reminder policy independent of scheduling and desktop APIs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as wall_time
from enum import Enum


class ReminderKind(Enum):
    """The two reminder states required by the MVP."""

    INACTIVE = "inactive"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class Reminder:
    """A reminder ready for presentation by an infrastructure adapter."""

    kind: ReminderKind
    project: str | None = None
    activity: str | None = None


@dataclass(frozen=True, slots=True)
class ReminderIntervals:
    """Enabled reminder intervals in seconds; ``None`` disables a kind."""

    inactive: float | None = 5 * 60
    active: float | None = 30 * 60

    def __post_init__(self) -> None:
        for interval in (self.inactive, self.active):
            if interval is not None and interval <= 0:
                raise ValueError("reminder intervals must be positive or disabled")


@dataclass(frozen=True, slots=True)
class ReminderWindow:
    """Weekly local-time window in which reminders may be presented."""

    weekdays: tuple[int, ...]
    start: wall_time
    end: wall_time

    def __post_init__(self) -> None:
        if not self.weekdays or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("reminder window weekdays must be non-empty and unique")
        if any(day < 0 or day > 6 for day in self.weekdays):
            raise ValueError("reminder window weekdays must be between 0 and 6")
        if self.start == self.end:
            raise ValueError("reminder window start and end must differ")

    def contains(self, now: datetime) -> bool:
        """Return whether an aware local instant lies within the weekly window."""
        local = _aware_local(now)
        current = local.timetz().replace(tzinfo=None)
        selected = set(self.weekdays)
        if self.start < self.end:
            return local.weekday() in selected and self.start <= current < self.end
        return (local.weekday() in selected and current >= self.start) or (
            (local.weekday() - 1) % 7 in selected and current < self.end
        )

    def seconds_until_open(self, now: datetime) -> float:
        """Return seconds until the next selected opening, or zero when open."""
        local = _aware_local(now)
        if self.contains(local):
            return 0.0
        for offset in range(8):
            candidate_date = local.date() + timedelta(days=offset)
            if candidate_date.weekday() not in self.weekdays:
                continue
            candidate = datetime.combine(candidate_date, self.start, local.tzinfo)
            if candidate > local:
                return candidate.timestamp() - local.timestamp()
        raise RuntimeError("a valid weekly reminder window has no next opening")


class ReminderSchedule:
    """Deterministic monotonic schedule reset by persisted timer transitions."""

    def __init__(
        self,
        intervals: ReminderIntervals | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        *,
        window: ReminderWindow | None = None,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._intervals = intervals or ReminderIntervals()
        self._monotonic = monotonic
        self._window = window
        self._wall_clock = wall_clock or (lambda: datetime.now().astimezone())
        self._kind = ReminderKind.INACTIVE
        self._project: str | None = None
        self._activity: str | None = None
        self._due_at: float | None = None

    def reset(
        self,
        kind: ReminderKind,
        *,
        project: str | None = None,
        activity: str | None = None,
    ) -> None:
        """Restart the selected reminder interval from now."""
        self._kind = kind
        self._project = project
        self._activity = activity
        interval = self._interval(kind)
        self._due_at = None if interval is None else self._monotonic() + interval

    def replace_intervals(self, intervals: ReminderIntervals) -> None:
        """Replace policy before the owner resets the current state."""
        self._intervals = intervals

    def replace_window(self, window: ReminderWindow | None) -> None:
        """Replace the local presentation window before the owner resets state."""
        self._window = window

    def snooze(self, seconds: float) -> None:
        """Replace the current deadline with an in-memory monotonic snooze."""
        if seconds <= 0:
            raise ValueError("snooze duration must be positive")
        self._due_at = self._monotonic() + seconds

    def seconds_until_due(self) -> float | None:
        """Return the non-negative wait until the next enabled reminder."""
        if self._due_at is None:
            return None
        return max(0.0, self._due_at - self._monotonic())

    def update_active_details(self, project: str, activity: str) -> None:
        """Update active reminder text without changing its existing deadline."""
        if self._kind is ReminderKind.ACTIVE:
            self._project = project
            self._activity = activity

    def take_due(self) -> Reminder | None:
        """Return a due reminder and schedule the next repetition."""
        if self._due_at is None or self._monotonic() < self._due_at:
            return None
        if self._window is not None:
            now = self._wall_clock()
            if not self._window.contains(now):
                self._due_at = self._monotonic() + self._window.seconds_until_open(now)
                return None
        interval = self._interval(self._kind)
        self._due_at = None if interval is None else self._monotonic() + interval
        return Reminder(
            kind=self._kind,
            project=self._project,
            activity=self._activity,
        )

    def _interval(self, kind: ReminderKind) -> float | None:
        if kind is ReminderKind.ACTIVE:
            return self._intervals.active
        return self._intervals.inactive


def _aware_local(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reminder window clock must return an aware datetime")
    return value
