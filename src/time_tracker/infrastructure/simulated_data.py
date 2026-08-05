"""Create deterministic weekday-only data for local manual testing."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from pathlib import Path

from time_tracker.application.tracking import Clock, TrackingService
from time_tracker.infrastructure.local_files import stop_agent
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository


@dataclass(frozen=True, slots=True)
class SimulatedEntry:
    """One generated completed entry expressed as authoritative UTC instants."""

    project: str
    activity: str
    started_at: datetime
    stopped_at: datetime
    note: str | None


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """Describe the records created by one successful seed operation."""

    start_date: date
    end_date: date
    project_count: int
    activity_count: int
    entry_count: int


@dataclass(frozen=True, slots=True)
class _EntryPattern:
    project: str
    activity: str
    start: time
    duration_minutes: int
    note: str | None = None


_WEEKDAY_PATTERNS: tuple[tuple[_EntryPattern, ...], ...] = (
    (
        _EntryPattern(
            "Product Launch",
            "Planning",
            time(9),
            75,
            "Weekly priorities and delivery plan",
        ),
        _EntryPattern("Client Portal", "Development", time(10, 30), 90),
        _EntryPattern(
            "Product Launch",
            "Implementation",
            time(13),
            210,
            "Feature implementation and tests",
        ),
    ),
    (
        _EntryPattern(
            "Client Portal",
            "Research",
            time(9),
            90,
            "Reviewed user feedback and support themes",
        ),
        _EntryPattern("Product Launch", "Implementation", time(10, 45), 90),
        _EntryPattern(
            "Internal Operations",
            "Learning",
            time(13),
            120,
            "Read documentation and captured follow-up ideas",
        ),
        _EntryPattern("Client Portal", "Development", time(15, 15), 90),
    ),
    (
        _EntryPattern(
            "Client Portal",
            "Meetings",
            time(9),
            60,
            "Weekly client sync",
        ),
        _EntryPattern("Product Launch", "Implementation", time(10, 15), 105),
        _EntryPattern(
            "Client Portal",
            "Development",
            time(13),
            180,
            "API integration and error handling",
        ),
    ),
    (
        _EntryPattern(
            "Product Launch",
            "Review",
            time(9),
            75,
            "Reviewed the current release candidate",
        ),
        _EntryPattern("Internal Operations", "Administration", time(10, 30), 60),
        _EntryPattern(
            "Product Launch",
            "Implementation",
            time(12, 30),
            210,
            "Accessibility and keyboard workflow pass",
        ),
    ),
    (
        _EntryPattern(
            "Client Portal",
            "Development",
            time(9),
            120,
            "Finished the weekly development slice",
        ),
        _EntryPattern(
            "Product Launch",
            "Review",
            time(11, 15),
            45,
            "Demo preparation",
        ),
        _EntryPattern("Internal Operations", "Learning", time(13), 90),
        _EntryPattern(
            "Product Launch",
            "Planning",
            time(14, 45),
            45,
            "Outlined next week's priorities",
        ),
    ),
)


def simulated_entries(
    end_date: date,
    *,
    local_timezone: tzinfo | None = None,
) -> list[SimulatedEntry]:
    """Build entries for an inclusive 45-day window ending on ``end_date``."""
    start_date = end_date - timedelta(days=44)
    entries: list[SimulatedEntry] = []
    for offset in range(45):
        entry_date = start_date + timedelta(days=offset)
        if entry_date.weekday() >= 5:
            continue
        for pattern in _WEEKDAY_PATTERNS[entry_date.weekday()]:
            started_at = _local_instant(entry_date, pattern.start, local_timezone)
            entries.append(
                SimulatedEntry(
                    project=pattern.project,
                    activity=pattern.activity,
                    started_at=started_at,
                    stopped_at=started_at + timedelta(minutes=pattern.duration_minutes),
                    note=pattern.note,
                )
            )
    return entries


def seed_simulated_data(
    database: Path,
    *,
    end_date: date,
    local_timezone: tzinfo | None = None,
    clock: Clock | None = None,
) -> SeedSummary:
    """Populate one empty database through the normal application boundary."""
    repository = SQLiteTimerRepository(database)
    if _has_stored_data(repository):
        raise RuntimeError(
            "database is not empty; run make clear-database CONFIRM=1 before "
            "seeding test data"
        )

    entries = simulated_entries(end_date, local_timezone=local_timezone)
    service = TrackingService(repository, clock)
    for entry in entries:
        service.create_manual_entry(
            entry.project,
            entry.activity,
            entry.started_at,
            entry.stopped_at,
            entry.note,
        )

    projects = {entry.project for entry in entries}
    activities = {(entry.project, entry.activity) for entry in entries}
    return SeedSummary(
        start_date=end_date - timedelta(days=44),
        end_date=end_date,
        project_count=len(projects),
        activity_count=len(activities),
        entry_count=len(entries),
    )


def _has_stored_data(repository: SQLiteTimerRepository) -> bool:
    return bool(
        repository.get_active()
        or repository.list_completed()
        or repository.list_projects()
        or repository.list_archived_projects()
    )


def _local_instant(
    entry_date: date,
    wall_time: time,
    local_timezone: tzinfo | None,
) -> datetime:
    local_value = datetime.combine(entry_date, wall_time)
    if local_timezone is not None:
        local_value = local_value.replace(tzinfo=local_timezone)
    return local_value.astimezone(UTC)


def main(argv: Sequence[str] | None = None) -> int:
    """Stop the agent and seed the default empty local database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm writing simulated records to the local database",
    )
    arguments = parser.parse_args(argv)
    if not arguments.yes:
        parser.error("seeding requires confirmation: make seed-test-data CONFIRM=1")

    paths = AgentPaths.defaults()
    stop_agent(paths)
    end_date = date.today() - timedelta(days=1)
    try:
        summary = seed_simulated_data(paths.database, end_date=end_date)
    except RuntimeError as error:
        parser.error(str(error))

    print(
        f"seeded {summary.entry_count} completed entries across "
        f"{summary.project_count} projects and {summary.activity_count} activities "
        f"from {summary.start_date.isoformat()} through "
        f"{summary.end_date.isoformat()} (weekdays only)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
