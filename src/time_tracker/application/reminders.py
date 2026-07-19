"""Reminder policy independent of scheduling and desktop APIs."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
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


class ReminderSchedule:
    """Deterministic monotonic schedule reset by persisted timer transitions."""

    def __init__(
        self,
        intervals: ReminderIntervals | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._intervals = intervals or ReminderIntervals()
        self._monotonic = monotonic
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

    def seconds_until_due(self) -> float | None:
        """Return the non-negative wait until the next enabled reminder."""
        if self._due_at is None:
            return None
        return max(0.0, self._due_at - self._monotonic())

    def take_due(self) -> Reminder | None:
        """Return a due reminder and schedule the next repetition."""
        if self._due_at is None or self._monotonic() < self._due_at:
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
