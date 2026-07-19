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
