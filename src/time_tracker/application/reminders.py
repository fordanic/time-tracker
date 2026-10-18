"""Reminder policy independent of scheduling and desktop APIs."""

from __future__ import annotations

import math
import secrets
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


class ReminderReason(Enum):
    """Why an active reminder was requested."""

    SCHEDULED = "scheduled"
    IDLE = "idle"
    LUNCH = "lunch"
    END_OF_DAY = "end_of_day"


class CheckpointAction(Enum):
    """Actions accepted for one pending active checkpoint."""

    CONTINUE = "continue"
    SNOOZE = "snooze"
    STOP = "stop"
    SWITCH = "switch"


@dataclass(frozen=True, slots=True)
class Reminder:
    """A reminder ready for presentation by an infrastructure adapter."""

    kind: ReminderKind
    project: str | None = None
    activity: str | None = None
    reason: ReminderReason = ReminderReason.SCHEDULED
    idle_threshold_minutes: float | None = None
    checkpoint_id: str | None = None
    active_entry_id: int | None = None
    switch_requested: bool = False

    def __post_init__(self) -> None:
        if self.reason is ReminderReason.IDLE:
            threshold = self.idle_threshold_minutes
            if (
                self.kind is not ReminderKind.ACTIVE
                or threshold is None
                or not math.isfinite(threshold)
                or threshold <= 0
            ):
                raise ValueError(
                    "idle-triggered reminders require an active timer and a "
                    "positive finite threshold"
                )
        elif self.idle_threshold_minutes is not None:
            raise ValueError("scheduled reminders cannot include an idle threshold")
        if (self.checkpoint_id is None) != (self.active_entry_id is None):
            raise ValueError(
                "checkpoint identifier and active entry identity must appear together"
            )
        if self.checkpoint_id is not None:
            if self.kind is not ReminderKind.ACTIVE or not self.checkpoint_id:
                raise ValueError("checkpoint identifiers require an active reminder")
            if (
                isinstance(self.active_entry_id, bool)
                or not isinstance(self.active_entry_id, int)
                or self.active_entry_id <= 0
            ):
                raise ValueError("checkpoint active entry identity must be positive")
        if self.switch_requested and self.checkpoint_id is None:
            raise ValueError("a switch request requires an active checkpoint")


@dataclass(frozen=True, slots=True)
class AutoStoppedNotification:
    """Follow-up notification emitted after a checkpoint stops a timer."""

    project: str
    activity: str
    stopped_at: datetime


@dataclass(frozen=True, slots=True)
class ScheduledCheckpoint:
    """One enabled named checkpoint at a local wall-clock time."""

    reason: ReminderReason
    at: wall_time

    def __post_init__(self) -> None:
        if self.reason not in {ReminderReason.LUNCH, ReminderReason.END_OF_DAY}:
            raise ValueError("scheduled safeguards require a named checkpoint reason")


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
        self._reason = ReminderReason.SCHEDULED
        self._idle_threshold_minutes: float | None = None

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
        self._reason = ReminderReason.SCHEDULED
        self._idle_threshold_minutes = None
        interval = self._interval(kind)
        self._due_at = None if interval is None else self._monotonic() + interval

    def replace_intervals(self, intervals: ReminderIntervals) -> None:
        """Replace policy before the owner resets the current state."""
        self._intervals = intervals

    def replace_window(self, window: ReminderWindow | None) -> None:
        """Replace the local presentation window before the owner resets state."""
        self._window = window

    def snooze(
        self,
        seconds: float,
        *,
        reason: ReminderReason = ReminderReason.SCHEDULED,
        idle_threshold_minutes: float | None = None,
    ) -> None:
        """Replace the current deadline with an in-memory monotonic snooze."""
        if seconds <= 0:
            raise ValueError("snooze duration must be positive")
        self._reason = reason
        self._idle_threshold_minutes = idle_threshold_minutes
        self._due_at = self._monotonic() + seconds

    def request_idle(self, threshold_minutes: float) -> None:
        """Request the current active reminder immediately for detected idleness."""
        if self._kind is not ReminderKind.ACTIVE:
            raise ValueError("idle reminders require an active timer")
        if not math.isfinite(threshold_minutes) or threshold_minutes <= 0:
            raise ValueError("idle threshold must be positive")
        self._reason = ReminderReason.IDLE
        self._idle_threshold_minutes = threshold_minutes
        self._due_at = self._monotonic()

    def seconds_until_due(self) -> float | None:
        """Return the non-negative wait until the next enabled reminder."""
        if self._due_at is None:
            return None
        return max(0.0, self._due_at - self._monotonic())

    @property
    def reason(self) -> ReminderReason:
        """Return the reason attached to the current deadline."""
        return self._reason

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
        reminder = Reminder(
            kind=self._kind,
            project=self._project,
            activity=self._activity,
            reason=self._reason,
            idle_threshold_minutes=self._idle_threshold_minutes,
        )
        interval = self._interval(self._kind)
        self._due_at = None if interval is None else self._monotonic() + interval
        self._reason = ReminderReason.SCHEDULED
        self._idle_threshold_minutes = None
        return reminder

    def _interval(self, kind: ReminderKind) -> float | None:
        if kind is ReminderKind.ACTIVE:
            return self._intervals.active
        return self._intervals.inactive


class ScheduledCheckpointSchedule:
    """Local wall-clock safeguards represented by one monotonic deadline."""

    def __init__(
        self,
        weekdays: tuple[int, ...],
        checkpoints: tuple[ScheduledCheckpoint, ...],
        monotonic: Callable[[], float] = time.monotonic,
        *,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not weekdays or len(set(weekdays)) != len(weekdays):
            raise ValueError("checkpoint weekdays must be non-empty and unique")
        if any(day < 0 or day > 6 for day in weekdays):
            raise ValueError("checkpoint weekdays must be between 0 and 6")
        if len({checkpoint.reason for checkpoint in checkpoints}) != len(checkpoints):
            raise ValueError("checkpoint reasons must be unique")
        self._weekdays = weekdays
        self._checkpoints = checkpoints
        self._monotonic = monotonic
        self._wall_clock = wall_clock or (lambda: datetime.now().astimezone())
        self._due_at: float | None = None
        self._due_reason: ReminderReason | None = None
        self.reset()

    def reset(self) -> None:
        """Skip past occurrences and schedule the next local checkpoint."""
        self._schedule_next(_aware_local(self._wall_clock()))

    def seconds_until_due(self) -> float | None:
        """Return the wait until the next configured safeguard."""
        if self._due_at is None:
            return None
        return max(0.0, self._due_at - self._monotonic())

    def take_due(self, *, active: bool) -> ReminderReason | None:
        """Consume one occurrence, returning it only when a timer is active."""
        if self._due_at is None or self._monotonic() < self._due_at:
            return None
        reason = self._due_reason
        self._schedule_next(_aware_local(self._wall_clock()))
        return reason if active else None

    def _schedule_next(self, now: datetime) -> None:
        candidates: list[tuple[datetime, ReminderReason]] = []
        selected = set(self._weekdays)
        for offset in range(8):
            candidate_date = now.date() + timedelta(days=offset)
            if candidate_date.weekday() not in selected:
                continue
            for checkpoint in self._checkpoints:
                candidate = datetime.combine(candidate_date, checkpoint.at, now.tzinfo)
                if candidate > now:
                    candidates.append((candidate, checkpoint.reason))
        if not candidates:
            self._due_at = None
            self._due_reason = None
            return
        candidate, reason = min(candidates, key=lambda value: value[0])
        self._due_at = self._monotonic() + max(
            0.0, candidate.timestamp() - now.timestamp()
        )
        self._due_reason = reason


def new_checkpoint_id() -> str:
    """Return an unguessable URL-safe identifier for one active checkpoint."""
    return secrets.token_urlsafe(24)


def _aware_local(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reminder window clock must return an aware datetime")
    return value
