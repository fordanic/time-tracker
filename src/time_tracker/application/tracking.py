"""Timer use cases and their infrastructure ports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from time_tracker.domain.models import ActiveTimer, CompletedTimer


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
        project = project.strip()
        activity = activity.strip()
        if not project:
            raise ValueError("project name is required")
        if not activity:
            raise ValueError("activity name is required")
        normalized_note = note.strip() if note and note.strip() else None
        return self._repository.start(
            project,
            activity,
            self._clock.now(),
            normalized_note,
        )

    def stop(self) -> CompletedTimer | None:
        """Stop the current timer using one captured transition instant."""
        return self._repository.stop(self._clock.now())
