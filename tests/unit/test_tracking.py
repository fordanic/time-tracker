from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from time_tracker.application.tracking import (
    AlreadyTrackingError,
    ArchivedActivity,
    QuickSwitchAction,
    RecentActivity,
    StartAction,
    TimerRepository,
    TrackingService,
    UnchangedActiveEntryError,
    classify_quick_switch,
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
        self.edits: list[tuple[str, str, str | None, datetime]] = []

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

    def edit_active(
        self,
        project: str,
        activity: str,
        note: str | None,
        updated_at: datetime,
    ) -> ActiveTimer:
        if self.active is None:
            raise ValueError("no active timer")
        self.edits.append((project, activity, note, updated_at))
        self.active = ActiveTimer(
            self.active.entry_id,
            project,
            activity,
            self.active.started_at,
            note,
        )
        return self.active


class CorrectionRepository:
    def __init__(self) -> None:
        self.corrections: list[
            tuple[int, str, str, datetime, datetime, str | None]
        ] = []

    def correct_completed(
        self,
        entry_id: int,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None,
    ) -> CompletedTimer:
        self.corrections.append(
            (entry_id, project, activity, started_at, stopped_at, note)
        )
        return CompletedTimer(
            entry_id,
            project,
            activity,
            started_at,
            stopped_at,
            note,
        )


class ManualEntryRepository:
    def __init__(self) -> None:
        self.created: list[
            tuple[str, str, datetime, datetime, str | None, datetime]
        ] = []

    def create_completed(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None,
        created_at: datetime,
    ) -> CompletedTimer:
        self.created.append(
            (project, activity, started_at, stopped_at, note, created_at)
        )
        return CompletedTimer(
            9,
            project,
            activity,
            started_at,
            stopped_at,
            note,
        )


class RecordingClock:
    def __init__(self, now: datetime) -> None:
        self.instant = now
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return self.instant


class ArchiveRepository:
    def __init__(self) -> None:
        self.archived_projects = ["Archived"]
        self.archived_activities = [
            ArchivedActivity("Archived", "Hidden", project_archived=True)
        ]
        self.project_resolutions: list[str] = []
        self.activity_resolutions: list[tuple[str, str]] = []
        self.project_archives: list[tuple[str, datetime]] = []

    def resolve_project_to_archive(self, project: str) -> str:
        self.project_resolutions.append(project)
        return "Website"

    def resolve_activity_to_archive(
        self,
        project: str,
        activity: str,
    ) -> tuple[str, str]:
        self.activity_resolutions.append((project, activity))
        return "Website", "Planning"

    def list_archived_projects(self) -> list[str]:
        return self.archived_projects

    def list_archived_activities(self) -> list[ArchivedActivity]:
        return self.archived_activities

    def archive_project(self, project: str, archived_at: datetime) -> str:
        self.project_archives.append((project, archived_at))
        return "Website"

    def unarchive_project(self, project: str) -> str:
        return project

    def unarchive_activity(self, project: str, activity: str) -> tuple[str, str]:
        return project, activity


class CreateRepository:
    def __init__(self) -> None:
        self.existing_projects: set[str] = set()
        self.existing_activities: dict[str, set[str]] = {}
        self.created_projects: list[tuple[str, datetime]] = []
        self.created_activities: list[tuple[str, str, datetime]] = []

    def create_project(self, project: str, created_at: datetime) -> str:
        if project.casefold() in {name.casefold() for name in self.existing_projects}:
            raise ValueError(f"project already exists: {project}")
        self.existing_projects.add(project)
        self.created_projects.append((project, created_at))
        return project

    def create_activity(
        self,
        project: str,
        activity: str,
        created_at: datetime,
    ) -> tuple[str, str]:
        if project.casefold() not in {
            name.casefold() for name in self.existing_projects
        }:
            raise ValueError(f"project not found: {project}")
        existing = self.existing_activities.setdefault(project.casefold(), set())
        if activity.casefold() in {name.casefold() for name in existing}:
            raise ValueError(f"activity already exists: {project}/{activity}")
        existing.add(activity)
        self.created_activities.append((project, activity, created_at))
        return project, activity


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


def test_archive_target_preview_and_listing_do_not_capture_a_write_time() -> None:
    instant = datetime(2026, 7, 20, 8, tzinfo=UTC)
    repository = ArchiveRepository()
    clock = RecordingClock(instant)
    service = TrackingService(cast(TimerRepository, repository), clock)

    assert service.get_archive_project_target(" website ") == "Website"
    assert service.get_archive_activity_target(" website ", " planning ") == (
        "Website",
        "Planning",
    )
    assert service.list_archived_projects() == ["Archived"]
    assert service.list_archived_activities() == [
        ArchivedActivity("Archived", "Hidden", project_archived=True)
    ]
    assert repository.project_resolutions == ["website"]
    assert repository.activity_resolutions == [("website", "planning")]
    assert repository.project_archives == []
    assert clock.calls == 0

    assert service.archive_project(" website ") == "Website"
    assert repository.project_archives == [("website", instant)]
    assert clock.calls == 1


def test_create_project_captures_write_time_and_returns_canonical_name() -> None:
    instant = datetime(2026, 7, 20, 8, tzinfo=UTC)
    repository = CreateRepository()
    clock = RecordingClock(instant)
    service = TrackingService(cast(TimerRepository, repository), clock)

    assert service.create_project(" Website ") == "Website"
    assert repository.created_projects == [("Website", instant)]
    assert clock.calls == 1


def test_create_project_requires_a_name() -> None:
    service = TrackingService(cast(TimerRepository, CreateRepository()))

    with pytest.raises(ValueError, match="project name is required"):
        service.create_project("   ")


def test_create_project_rejects_an_existing_name() -> None:
    repository = CreateRepository()
    service = TrackingService(cast(TimerRepository, repository))
    service.create_project("Website")

    with pytest.raises(ValueError, match="project already exists"):
        service.create_project("website")


def test_create_activity_captures_write_time_and_returns_canonical_names() -> None:
    instant = datetime(2026, 7, 20, 8, tzinfo=UTC)
    repository = CreateRepository()
    repository.existing_projects.add("Website")
    clock = RecordingClock(instant)
    service = TrackingService(cast(TimerRepository, repository), clock)

    assert service.create_activity(" Website ", " Planning ") == (
        "Website",
        "Planning",
    )
    assert repository.created_activities == [("Website", "Planning", instant)]
    assert clock.calls == 1


def test_create_activity_requires_project_and_activity_names() -> None:
    service = TrackingService(cast(TimerRepository, CreateRepository()))

    with pytest.raises(ValueError, match="project name is required"):
        service.create_activity("   ", "Planning")
    with pytest.raises(ValueError, match="activity name is required"):
        service.create_activity("Website", "   ")


def test_create_activity_rejects_missing_project() -> None:
    service = TrackingService(cast(TimerRepository, CreateRepository()))

    with pytest.raises(ValueError, match="project not found"):
        service.create_activity("Website", "Planning")


def test_create_activity_rejects_an_existing_name() -> None:
    repository = CreateRepository()
    repository.existing_projects.add("Website")
    service = TrackingService(cast(TimerRepository, repository))
    service.create_activity("Website", "Planning")

    with pytest.raises(ValueError, match="activity already exists"):
        service.create_activity("website", "planning")


def test_recent_activity_limit_is_validated() -> None:
    repository = RecentRepository([], {})
    service = TrackingService(cast(TimerRepository, repository))

    assert service.list_recent_activities(limit=0) == []
    with pytest.raises(ValueError, match="limit cannot be negative"):
        service.list_recent_activities(limit=-1)


def test_quick_switch_action_ignores_capture_note_restart_rules() -> None:
    pair = RecentActivity("Website", "Planning")
    active = ActiveTimer(
        entry_id=7,
        project="Website",
        activity="Planning",
        started_at=datetime(2026, 7, 20, 8, tzinfo=UTC),
        note="Current note",
    )

    assert classify_quick_switch(None, pair) is QuickSwitchAction.START
    assert classify_quick_switch(active, pair) is QuickSwitchAction.CURRENT
    assert (
        classify_quick_switch(active, RecentActivity("Website", "Review"))
        is QuickSwitchAction.SWITCH
    )


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


def test_completed_correction_normalizes_values_and_requires_positive_interval() -> (
    None
):
    repository = CorrectionRepository()
    service = TrackingService(cast(TimerRepository, repository))
    started_at = datetime(2026, 7, 20, 10, tzinfo=UTC)
    stopped_at = started_at + timedelta(hours=1)

    corrected = service.correct_completed(
        7,
        " Website ",
        " Review ",
        started_at,
        stopped_at,
        "  Revised note  ",
    )

    assert corrected.note == "Revised note"
    assert repository.corrections == [
        (7, "Website", "Review", started_at, stopped_at, "Revised note")
    ]

    with pytest.raises(ValueError, match="stop must be after start"):
        service.correct_completed(
            7,
            "Website",
            "Review",
            stopped_at,
            stopped_at,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        service.correct_completed(
            7,
            "Website",
            "Review",
            started_at.replace(tzinfo=None),
            stopped_at,
        )
    assert len(repository.corrections) == 1


def test_manual_entry_normalizes_values_and_captures_creation_time() -> None:
    repository = ManualEntryRepository()
    created_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    clock = RecordingClock(created_at)
    service = TrackingService(cast(TimerRepository, repository), clock)
    started_at = datetime(2026, 7, 19, 10, tzinfo=UTC)
    stopped_at = started_at + timedelta(hours=1)

    entry = service.create_manual_entry(
        " Website ",
        " Review ",
        started_at,
        stopped_at,
        "  Missed work  ",
    )

    assert entry.note == "Missed work"
    assert repository.created == [
        (
            "Website",
            "Review",
            started_at,
            stopped_at,
            "Missed work",
            created_at,
        )
    ]
    assert clock.calls == 1

    with pytest.raises(ValueError, match="stop must be after start"):
        service.create_manual_entry(
            "Website",
            "Review",
            stopped_at,
            stopped_at,
        )
    assert clock.calls == 1
    assert len(repository.created) == 1


def test_active_edit_preserves_start_and_rejects_unchanged_values_before_clock() -> (
    None
):
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    updated_at = started_at + timedelta(hours=1)
    original = ActiveTimer(
        4,
        "Website",
        "Planning",
        started_at,
        "Original",
    )
    repository = ActionRepository(original)
    clock = RecordingClock(updated_at)
    service = TrackingService(cast(TimerRepository, repository), clock)

    with pytest.raises(UnchangedActiveEntryError, match="unchanged"):
        service.edit_active(" website ", "PLANNING", " Original ")
    assert repository.edits == []
    assert clock.calls == 0

    edited = service.edit_active(
        " Client ",
        " Review ",
        " Revised ",
    )

    assert edited.entry_id == original.entry_id
    assert edited.started_at == original.started_at
    assert edited.note == "Revised"
    assert repository.edits == [("Client", "Review", "Revised", updated_at)]
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
