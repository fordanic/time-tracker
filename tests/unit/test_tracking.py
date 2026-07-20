from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from time_tracker.application.tracking import (
    RecentActivity,
    TimerRepository,
    TrackingService,
)
from time_tracker.domain.models import CompletedTimer


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
