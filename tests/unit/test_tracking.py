from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from time_tracker.application.tracking import (
    AlreadyTrackingError,
    RecentActivity,
    StartAction,
    TimerRepository,
    TrackingService,
)
from time_tracker.domain.models import ActiveTimer, CompletedTimer


class RecentRepository:
    def __init__(
        self,
        completed: list[CompletedTimer],
        selectable: dict[str, list[str]],
    ) -> None:
        self.completed = completed
        self.selectable = selectable

    def list_projects(self) -> list[str]:
        return list(self.selectable)

    def list_activities(self, project: str) -> list[str]:
        return self.selectable[project]

    def list_completed(self) -> list[CompletedTimer]:
        return self.completed


class ActionRepository:
    def __init__(self, active: ActiveTimer | None) -> None:
        self.active = active
        self.starts: list[tuple[str, str, datetime, str | None]] = []

    def get_active(self) -> ActiveTimer | None:
        return self.active

    def start(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        note: str | None,
    ) -> ActiveTimer:
        self.starts.append((project, activity, started_at, note))
        self.active = ActiveTimer(
            entry_id=(self.active.entry_id + 1 if self.active else 1),
            project=project,
            activity=activity,
            started_at=started_at,
            note=note,
        )
        return self.active


class RecordingClock:
    def __init__(self, now: datetime) -> None:
        self.instant = now
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return self.instant


def test_recent_activities_are_unique_selectable_and_limited() -> None:
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    completed = [
        _completed(1, "Work", "Planning", started_at),
        _completed(2, "Work", "Research", started_at + timedelta(hours=1)),
        _completed(3, "Work", "Review", started_at + timedelta(hours=2)),
        _completed(4, "Archived", "Hidden", started_at + timedelta(hours=3)),
        _completed(5, "Work", "Planning", started_at + timedelta(hours=4)),
        _completed(6, "Work", "Testing", started_at + timedelta(hours=5)),
        _completed(7, "Work", "Implementation", started_at + timedelta(hours=6)),
    ]
    repository = RecentRepository(
        completed,
        {
            "Work": ["Planning", "Research", "Review", "Testing", "Implementation"],
        },
    )
    service = TrackingService(cast(TimerRepository, repository))

    assert service.list_recent_activities() == [
        RecentActivity("Work", "Implementation"),
        RecentActivity("Work", "Testing"),
        RecentActivity("Work", "Planning"),
        RecentActivity("Work", "Review"),
        RecentActivity("Work", "Research"),
    ]


def test_recent_activity_limit_is_validated() -> None:
    repository = RecentRepository([], {})
    service = TrackingService(cast(TimerRepository, repository))

    assert service.list_recent_activities(limit=0) == []
    with pytest.raises(ValueError, match="limit cannot be negative"):
        service.list_recent_activities(limit=-1)


def test_start_action_classifies_normalized_selection() -> None:
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    repository = ActionRepository(
        ActiveTimer(
            entry_id=1,
            project="Website",
            activity="Implementation",
            started_at=started_at,
            note="Original note",
        )
    )
    service = TrackingService(cast(TimerRepository, repository))

    assert (
        service.get_start_action(
            " website ",
            " IMPLEMENTATION ",
            "  Original note  ",
        )
        is StartAction.ALREADY_TRACKING
    )
    assert (
        service.get_start_action("Website", "Implementation", "original note")
        is StartAction.RESTART
    )
    assert (
        service.get_start_action("Website", "Review", "Original note")
        is StartAction.SWITCH
    )

    repository.active = None
    assert (
        service.get_start_action("Website", "Implementation", "Original note")
        is StartAction.START
    )


def test_unchanged_start_is_rejected_before_clock_or_repository() -> None:
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    active = ActiveTimer(
        entry_id=1,
        project="Website",
        activity="Implementation",
        started_at=started_at,
        note="Original note",
    )
    repository = ActionRepository(active)
    clock = RecordingClock(started_at + timedelta(hours=1))
    service = TrackingService(cast(TimerRepository, repository), clock)

    with pytest.raises(AlreadyTrackingError, match="already tracking"):
        service.start(" website ", "implementation", " Original note ")

    assert repository.get_active() == active
    assert repository.starts == []
    assert clock.calls == 0


def test_restart_normalizes_note_and_captures_one_transition_instant() -> None:
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    transition = started_at + timedelta(hours=1)
    repository = ActionRepository(
        ActiveTimer(1, "Website", "Implementation", started_at, "Original note")
    )
    clock = RecordingClock(transition)
    service = TrackingService(cast(TimerRepository, repository), clock)

    restarted = service.start(
        " Website ",
        " Implementation ",
        "  New note  ",
    )

    assert restarted.note == "New note"
    assert repository.starts == [("Website", "Implementation", transition, "New note")]
    assert clock.calls == 1


def _completed(
    entry_id: int,
    project: str,
    activity: str,
    started_at: datetime,
) -> CompletedTimer:
    return CompletedTimer(
        entry_id=entry_id,
        project=project,
        activity=activity,
        started_at=started_at,
        stopped_at=started_at + timedelta(minutes=30),
        note=f"Historical note {entry_id}",
    )
