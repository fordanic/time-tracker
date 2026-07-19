from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from time_tracker.infrastructure.sqlite_repository import (
    SQLiteTimerRepository,
    datetime_to_micros,
)


def test_active_timer_survives_repository_restart_and_can_be_stopped(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tracker.sqlite3"
    started_at = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)
    first_repository = SQLiteTimerRepository(database)
    started = first_repository.start(
        "Website",
        "Implementation",
        started_at,
        "Persistent slice",
    )

    restarted_repository = SQLiteTimerRepository(database)

    assert restarted_repository.get_active() == started
    completed = restarted_repository.stop(started_at + timedelta(minutes=45))
    assert completed is not None
    assert completed.duration == timedelta(minutes=45)
    assert restarted_repository.get_active() is None


def test_switching_timers_uses_one_adjacent_transition_timestamp(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tracker.sqlite3"
    repository = SQLiteTimerRepository(database)
    first_start = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    transition = first_start + timedelta(minutes=10)

    repository.start("Website", "Planning", first_start, None)
    current = repository.start("Website", "Implementation", transition, None)

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT started_at_utc, stopped_at_utc
            FROM time_entries
            ORDER BY id
            """
        ).fetchall()
    assert rows == [
        (datetime_to_micros(first_start), datetime_to_micros(transition)),
        (datetime_to_micros(transition), None),
    ]
    assert repository.get_active() == current


def test_database_boundary_rejects_a_second_active_entry(tmp_path: Path) -> None:
    database = tmp_path / "tracker.sqlite3"
    repository = SQLiteTimerRepository(database)
    started_at = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    repository.start("Website", "Implementation", started_at, None)

    with sqlite3.connect(database) as connection:
        activity_id = connection.execute("SELECT id FROM activities").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO time_entries(
                    activity_id, started_at_utc, created_at_utc
                ) VALUES (?, ?, ?)
                """,
                (
                    activity_id,
                    datetime_to_micros(started_at),
                    datetime_to_micros(started_at),
                ),
            )


def test_existing_names_are_listed_and_reused_case_insensitively(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tracker.sqlite3"
    repository = SQLiteTimerRepository(database)
    started_at = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    repository.start("Website", "Implementation", started_at, None)

    restarted = repository.start(
        "website",
        "implementation",
        started_at + timedelta(minutes=5),
        None,
    )

    assert restarted.project == "Website"
    assert restarted.activity == "Implementation"
    assert repository.list_projects() == ["Website"]
    assert repository.list_activities("WEBSITE") == ["Implementation"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM projects").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM activities").fetchone()[0] == 1


def test_completed_entries_are_listed_chronologically_without_active_entry(
    tmp_path: Path,
) -> None:
    repository = SQLiteTimerRepository(tmp_path / "tracker.sqlite3")
    first_start = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    transition = first_start + timedelta(minutes=20)
    stopped_at = transition + timedelta(minutes=40)

    first = repository.start("Website", "Planning", first_start, "Outline, review")
    second = repository.start("Client Ω", "Implementation", transition, None)

    assert repository.list_completed() == [first.stop(transition)]

    repository.stop(stopped_at)

    assert repository.list_completed() == [
        first.stop(transition),
        second.stop(stopped_at),
    ]


def test_archived_activity_remains_in_history_and_cannot_be_reused(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tracker.sqlite3"
    repository = SQLiteTimerRepository(database)
    started_at = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    stopped_at = started_at + timedelta(minutes=30)
    archived_at = stopped_at + timedelta(minutes=1)
    active = repository.start("Website", "Implementation", started_at, None)
    completed = repository.stop(stopped_at)

    archived = repository.archive_activity("website", "implementation", archived_at)

    assert archived == ("Website", "Implementation")
    assert repository.list_projects() == ["Website"]
    assert repository.list_activities("Website") == []
    assert repository.list_completed() == [completed]
    with pytest.raises(ValueError, match="activity is archived: Implementation"):
        repository.start(
            "WEBSITE",
            "IMPLEMENTATION",
            archived_at + timedelta(minutes=1),
            None,
        )
    assert repository.get_active() is None
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT archived_at_utc FROM activities").fetchone()
        assert row == (datetime_to_micros(archived_at),)
        assert connection.execute("SELECT count(*) FROM activities").fetchone()[0] == 1
    assert completed == active.stop(stopped_at)


def test_archived_project_is_not_selectable_and_rejected_start_is_atomic(
    tmp_path: Path,
) -> None:
    repository = SQLiteTimerRepository(tmp_path / "tracker.sqlite3")
    started_at = datetime(2026, 7, 19, 9, 0, tzinfo=UTC)
    archived_at = started_at + timedelta(minutes=5)
    active = repository.start("Website", "Planning", started_at, None)

    assert repository.archive_project("website", archived_at) == "Website"
    assert repository.list_projects() == []
    assert repository.list_activities("Website") == []
    assert repository.get_active() == active

    with pytest.raises(ValueError, match="project is archived: Website"):
        repository.start(
            "WEBSITE",
            "Other",
            archived_at + timedelta(minutes=1),
            None,
        )

    assert repository.get_active() == active
    assert repository.list_completed() == []
