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


def test_completed_correction_is_atomic_canonical_and_non_overlapping(
    tmp_path: Path,
) -> None:
    repository = SQLiteTimerRepository(tmp_path / "tracker.sqlite3")
    first_start = datetime(2026, 7, 20, 8, tzinfo=UTC)
    first = repository.start("Website", "Planning", first_start, "Original")
    repository.stop(first_start + timedelta(hours=1))
    second_start = first_start + timedelta(hours=2)
    second = repository.start("Website", "Review", second_start, None)
    repository.stop(second_start + timedelta(hours=1))
    active = repository.start(
        "Website",
        "Implementation",
        first_start + timedelta(hours=4),
        None,
    )

    corrected = repository.correct_completed(
        first.entry_id,
        "Client",
        "Planning",
        first_start + timedelta(hours=1),
        second_start,
        "Revised",
    )

    assert corrected.project == "Client"
    assert corrected.activity == "Planning"
    assert corrected.stopped_at == second.started_at
    assert corrected.entry_id == first.entry_id
    assert repository.get_active() == active
    assert repository.list_projects() == ["Client", "Website"]

    before_rejection = repository.list_completed()
    with pytest.raises(ValueError, match=f"overlaps entry {second.entry_id}"):
        repository.correct_completed(
            first.entry_id,
            "Other",
            "Work",
            second_start - timedelta(minutes=1),
            second_start + timedelta(minutes=1),
            None,
        )
    assert repository.list_completed() == before_rejection
    assert "Other" not in repository.list_projects()

    with pytest.raises(ValueError, match=f"overlaps entry {active.entry_id}"):
        repository.correct_completed(
            first.entry_id,
            "Client",
            "Planning",
            active.started_at,
            active.started_at + timedelta(minutes=1),
            "Revised",
        )


def test_time_only_correction_retains_archived_historical_target(
    tmp_path: Path,
) -> None:
    repository = SQLiteTimerRepository(tmp_path / "tracker.sqlite3")
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    entry = repository.start("Website", "Planning", started_at, None)
    repository.stop(started_at + timedelta(hours=1))
    repository.archive_activity(
        "Website",
        "Planning",
        started_at + timedelta(hours=2),
    )

    corrected = repository.correct_completed(
        entry.entry_id,
        "website",
        "PLANNING",
        started_at + timedelta(minutes=5),
        started_at + timedelta(minutes=55),
        "Allowed on archived assignment",
    )

    assert corrected.project == "Website"
    assert corrected.activity == "Planning"
    other = repository.start(
        "Website",
        "Other",
        started_at + timedelta(hours=2),
        None,
    )
    repository.stop(started_at + timedelta(hours=3))
    repository.archive_activity(
        "Website",
        "Other",
        started_at + timedelta(hours=4),
    )
    with pytest.raises(ValueError, match="activity is archived: Planning"):
        repository.correct_completed(
            other.entry_id,
            "Website",
            "Planning",
            other.started_at,
            other.started_at + timedelta(minutes=30),
            None,
        )


def test_manual_entry_is_atomic_non_overlapping_and_preserves_active_timer(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tracker.sqlite3"
    repository = SQLiteTimerRepository(database)
    first_start = datetime(2026, 7, 20, 8, tzinfo=UTC)
    repository.start("Website", "Planning", first_start, None)
    repository.stop(first_start + timedelta(hours=1))
    active = repository.start(
        "Website",
        "Implementation",
        first_start + timedelta(hours=4),
        None,
    )
    created_at = first_start + timedelta(hours=5)

    manual = repository.create_completed(
        "website",
        "Review",
        first_start + timedelta(hours=1),
        first_start + timedelta(hours=2),
        "Missed interval",
        created_at,
    )

    assert manual.project == "Website"
    assert manual.activity == "Review"
    assert manual.started_at == first_start + timedelta(hours=1)
    assert repository.get_active() == active
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT created_at_utc FROM time_entries WHERE id = ?",
            (manual.entry_id,),
        ).fetchone()
    assert row == (datetime_to_micros(created_at),)

    before_rejection = repository.list_completed()
    with pytest.raises(ValueError, match=f"overlaps entry {active.entry_id}"):
        repository.create_completed(
            "New project",
            "New activity",
            active.started_at,
            active.started_at + timedelta(minutes=30),
            None,
            created_at,
        )
    assert repository.list_completed() == before_rejection
    assert "New project" not in repository.list_projects()

    repository.archive_activity("Website", "Review", created_at)
    with pytest.raises(ValueError, match="activity is archived: Review"):
        repository.create_completed(
            "Website",
            "Review",
            first_start + timedelta(hours=2),
            first_start + timedelta(hours=3),
            None,
            created_at,
        )
    assert repository.list_completed() == before_rejection


def test_active_detail_edit_preserves_identity_start_and_archived_assignment(
    tmp_path: Path,
) -> None:
    database = tmp_path / "tracker.sqlite3"
    repository = SQLiteTimerRepository(database)
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    original = repository.start("Website", "Planning", started_at, "Original")
    repository.archive_activity(
        "Website",
        "Planning",
        started_at + timedelta(minutes=30),
    )

    note_only = repository.edit_active(
        "website",
        "PLANNING",
        "Revised",
        started_at + timedelta(hours=1),
    )

    assert note_only.entry_id == original.entry_id
    assert note_only.started_at == original.started_at
    assert note_only.project == "Website"
    assert note_only.activity == "Planning"
    assert repository.list_completed() == []

    reassigned = repository.edit_active(
        "Client",
        "Review",
        None,
        started_at + timedelta(hours=2),
    )
    assert reassigned.entry_id == original.entry_id
    assert reassigned.started_at == original.started_at
    assert repository.list_projects() == ["Client", "Website"]

    repository.archive_project("Client", started_at + timedelta(hours=3))
    with pytest.raises(ValueError, match="project is archived: Client"):
        repository.edit_active(
            "Client",
            "Other",
            None,
            started_at + timedelta(hours=4),
        )
    assert repository.get_active() == reassigned
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT started_at_utc, stopped_at_utc, created_at_utc FROM time_entries"
        ).fetchone()
    original_micros = datetime_to_micros(started_at)
    assert row == (original_micros, None, original_micros)
