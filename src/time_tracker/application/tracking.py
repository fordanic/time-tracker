"""Timer use cases and their infrastructure ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from time_tracker.domain.models import ActiveTimer, CompletedTimer, require_utc


@dataclass(frozen=True, slots=True)
class RecentActivity:
    """A selectable project/activity pair ordered by recent completed use."""

    project: str
    activity: str


class StartAction(StrEnum):
    """The effect of applying the current capture selection."""

    START = "start"
    SWITCH = "switch"
    ALREADY_TRACKING = "already_tracking"
    RESTART = "restart"


class AlreadyTrackingError(ValueError):
    """Raised when a requested start would not change the active timer."""


class UnchangedActiveEntryError(ValueError):
    """Raised when an active-entry edit contains no normalized change."""


class Clock(Protocol):
    """Source of persisted wall-clock instants."""

    def now(self) -> datetime:
        """Return the current aware UTC instant."""
        ...


class TimerRepository(Protocol):
    """Persistence operations that must complete atomically."""

    def get_active(self) -> ActiveTimer | None:
        """Return the current active timer, if one exists."""
        ...

    def list_projects(self) -> list[str]:
        """Return selectable project names in display order."""
        ...

    def list_activities(self, project: str) -> list[str]:
        """Return selectable activity names for one project."""
        ...

    def list_completed(self) -> list[CompletedTimer]:
        """Return completed entries in chronological order."""
        ...

    def archive_project(self, project: str, archived_at: datetime) -> str:
        """Archive a project and return its canonical stored name."""
        ...

    def archive_activity(
        self,
        project: str,
        activity: str,
        archived_at: datetime,
    ) -> tuple[str, str]:
        """Archive an activity and return its canonical project and activity."""
        ...

    def start(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        note: str | None,
    ) -> ActiveTimer:
        """Atomically stop the current timer and start a new one."""
        ...

    def stop(self, stopped_at: datetime) -> CompletedTimer | None:
        """Atomically stop the active timer, if one exists."""
        ...

    def correct_completed(
        self,
        entry_id: int,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None,
    ) -> CompletedTimer:
        """Atomically validate and update one completed entry."""
        ...

    def create_completed(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None,
        created_at: datetime,
    ) -> CompletedTimer:
        """Atomically validate and insert one manual completed entry."""
        ...

    def edit_active(
        self,
        project: str,
        activity: str,
        note: str | None,
        updated_at: datetime,
    ) -> ActiveTimer:
        """Atomically update the active entry's target and note."""
        ...


class SystemClock:
    """Production UTC clock."""

    def now(self) -> datetime:
        """Return the current UTC instant."""
        return datetime.now(UTC)


class TrackingService:
    """Application-facing start, stop, and recovery use cases."""

    def __init__(self, repository: TimerRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or SystemClock()

    def get_active(self) -> ActiveTimer | None:
        """Recover the current active timer from authoritative storage."""
        return self._repository.get_active()

    def list_projects(self) -> list[str]:
        """List projects available for a new timer."""
        return self._repository.list_projects()

    def list_activities(self, project: str) -> list[str]:
        """List activities belonging to the selected project."""
        project = project.strip()
        return self._repository.list_activities(project) if project else []

    def list_completed(self) -> list[CompletedTimer]:
        """List completed entries in chronological order."""
        return self._repository.list_completed()

    def list_recent_activities(self, *, limit: int = 5) -> list[RecentActivity]:
        """List unique selectable pairs by most recent completed use."""
        if limit < 0:
            raise ValueError("recent activity limit cannot be negative")
        if limit == 0:
            return []

        selectable_pairs = {
            (project.casefold(), activity.casefold())
            for project in self._repository.list_projects()
            for activity in self._repository.list_activities(project)
        }
        recent: list[RecentActivity] = []
        seen: set[tuple[str, str]] = set()
        completed = sorted(
            self._repository.list_completed(),
            key=lambda entry: (entry.stopped_at, entry.entry_id),
            reverse=True,
        )
        for entry in completed:
            pair = (entry.project.casefold(), entry.activity.casefold())
            if pair in seen or pair not in selectable_pairs:
                continue
            seen.add(pair)
            recent.append(RecentActivity(entry.project, entry.activity))
            if len(recent) == limit:
                break
        return recent

    def get_start_action(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> StartAction:
        """Classify a capture selection against authoritative active state."""
        normalized_project, normalized_activity, normalized_note = _normalize_selection(
            project,
            activity,
            note,
        )
        return _classify_start_action(
            self._repository.get_active(),
            normalized_project,
            normalized_activity,
            normalized_note,
        )

    def archive_project(self, project: str) -> str:
        """Archive a project so it cannot be used for future timers."""
        project = project.strip()
        if not project:
            raise ValueError("project name is required")
        return self._repository.archive_project(project, self._clock.now())

    def archive_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Archive one activity so it cannot be used for future timers."""
        project = project.strip()
        activity = activity.strip()
        if not project:
            raise ValueError("project name is required")
        if not activity:
            raise ValueError("activity name is required")
        return self._repository.archive_activity(
            project,
            activity,
            self._clock.now(),
        )

    def start(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> ActiveTimer:
        """Start an activity after validating user-facing names."""
        project, activity, normalized_note = _normalize_selection(
            project,
            activity,
            note,
        )
        if not project:
            raise ValueError("project name is required")
        if not activity:
            raise ValueError("activity name is required")
        action = _classify_start_action(
            self._repository.get_active(),
            project,
            activity,
            normalized_note,
        )
        if action is StartAction.ALREADY_TRACKING:
            raise AlreadyTrackingError(
                "already tracking the selected project, activity, and note"
            )
        return self._repository.start(
            project,
            activity,
            self._clock.now(),
            normalized_note,
        )

    def stop(self) -> CompletedTimer | None:
        """Stop the current timer using one captured transition instant."""
        return self._repository.stop(self._clock.now())

    def correct_completed(
        self,
        entry_id: int,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer:
        """Correct one completed entry after validating editable values."""
        project, activity, normalized_note = _normalize_selection(
            project,
            activity,
            note,
        )
        if not project:
            raise ValueError("project name is required")
        if not activity:
            raise ValueError("activity name is required")
        started_at = require_utc(started_at)
        stopped_at = require_utc(stopped_at)
        if stopped_at <= started_at:
            raise ValueError("corrected stop must be after start")
        return self._repository.correct_completed(
            entry_id,
            project,
            activity,
            started_at,
            stopped_at,
            normalized_note,
        )

    def create_manual_entry(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer:
        """Create one closed entry for missed time after validating its values."""
        project, activity, normalized_note = _normalize_selection(
            project,
            activity,
            note,
        )
        if not project:
            raise ValueError("project name is required")
        if not activity:
            raise ValueError("activity name is required")
        started_at = require_utc(started_at)
        stopped_at = require_utc(stopped_at)
        if stopped_at <= started_at:
            raise ValueError("manual entry stop must be after start")
        return self._repository.create_completed(
            project,
            activity,
            started_at,
            stopped_at,
            normalized_note,
            self._clock.now(),
        )

    def edit_active(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> ActiveTimer:
        """Edit active details without replacing or restarting the timer."""
        project, activity, normalized_note = _normalize_selection(
            project,
            activity,
            note,
        )
        if not project:
            raise ValueError("project name is required")
        if not activity:
            raise ValueError("activity name is required")
        active = self._repository.get_active()
        if active is None:
            raise ValueError("no active timer to edit")
        if (
            _classify_start_action(
                active,
                project,
                activity,
                normalized_note,
            )
            is StartAction.ALREADY_TRACKING
        ):
            raise UnchangedActiveEntryError("active entry details are unchanged")
        return self._repository.edit_active(
            project,
            activity,
            normalized_note,
            self._clock.now(),
        )


def _normalize_selection(
    project: str,
    activity: str,
    note: str | None,
) -> tuple[str, str, str | None]:
    normalized_note = note.strip() if note and note.strip() else None
    return project.strip(), activity.strip(), normalized_note


def _classify_start_action(
    active: ActiveTimer | None,
    project: str,
    activity: str,
    note: str | None,
) -> StartAction:
    if active is None:
        return StartAction.START
    same_pair = (
        project.casefold() == active.project.casefold()
        and activity.casefold() == active.activity.casefold()
    )
    if not same_pair:
        return StartAction.SWITCH
    if note == active.note:
        return StartAction.ALREADY_TRACKING
    return StartAction.RESTART
