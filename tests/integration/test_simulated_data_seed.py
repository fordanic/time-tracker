from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from time_tracker.infrastructure.simulated_data import (
    seed_simulated_data,
    simulated_entries,
)
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def test_seed_simulated_data_persists_complete_weekday_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "time-tracker.sqlite3"
    end_date = date(2026, 7, 31)
    generated = simulated_entries(end_date, local_timezone=UTC)

    summary = seed_simulated_data(
        database,
        end_date=end_date,
        local_timezone=UTC,
        clock=FixedClock(datetime(2026, 8, 1, tzinfo=UTC)),
    )

    repository = SQLiteTimerRepository(database)
    completed = repository.list_completed()
    assert summary.start_date == end_date - timedelta(days=44)
    assert summary.end_date == end_date
    assert summary.project_count == 3
    assert summary.activity_count == 8
    assert summary.entry_count == len(generated)
    assert repository.get_active() is None
    assert repository.list_projects() == [
        "Client Portal",
        "Internal Operations",
        "Product Launch",
    ]
    assert [
        (
            entry.project,
            entry.activity,
            entry.started_at,
            entry.stopped_at,
            entry.note,
        )
        for entry in completed
    ] == [
        (
            entry.project,
            entry.activity,
            entry.started_at,
            entry.stopped_at,
            entry.note,
        )
        for entry in generated
    ]


def test_seed_simulated_data_refuses_a_nonempty_database(tmp_path: Path) -> None:
    database = tmp_path / "time-tracker.sqlite3"
    repository = SQLiteTimerRepository(database)
    repository.create_project("Existing", datetime(2026, 7, 1, tzinfo=UTC))

    with pytest.raises(RuntimeError, match="database is not empty"):
        seed_simulated_data(
            database,
            end_date=date(2026, 7, 31),
            local_timezone=UTC,
        )

    restarted = SQLiteTimerRepository(database)
    assert restarted.list_projects() == ["Existing"]
    assert restarted.list_completed() == []
