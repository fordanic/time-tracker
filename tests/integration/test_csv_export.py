from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from time_tracker.application.exporting import (
    ExportDestinationExistsError,
    ExportService,
)
from time_tracker.infrastructure.csv_export import CSV_COLUMNS, CsvCompletedEntryWriter
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository


def test_csv_export_preserves_values_and_excludes_active_entry(tmp_path: Path) -> None:
    repository = SQLiteTimerRepository(tmp_path / "tracker.sqlite3")
    service = ExportService(repository, CsvCompletedEntryWriter())
    started_at = datetime(2026, 7, 19, 8, 30, 0, 125_000, tzinfo=UTC)
    transition = started_at + timedelta(seconds=90, microseconds=250_000)
    note = 'Review, "quote"\nand newline Ω'
    repository.start("Client Ω", "Research", started_at, note)
    repository.start("Internal", "Active work", transition, "not exported")
    destination = tmp_path / "entries.csv"

    entry_count = service.export_completed(destination)

    assert entry_count == 1
    with destination.open(encoding="utf-8", newline="") as exported:
        rows = list(csv.reader(exported))
    assert rows[0] == list(CSV_COLUMNS)
    assert rows[1][0:2] == ["Client Ω", "Research"]
    assert datetime.fromisoformat(rows[1][2]).astimezone(UTC) == started_at
    assert datetime.fromisoformat(rows[1][3]).astimezone(UTC) == transition
    assert rows[1][4] == "90.25"
    assert rows[1][5] == note
    assert len(rows) == 2


def test_csv_export_requires_confirmation_before_overwrite(tmp_path: Path) -> None:
    repository = SQLiteTimerRepository(tmp_path / "tracker.sqlite3")
    service = ExportService(repository, CsvCompletedEntryWriter())
    destination = tmp_path / "existing.csv"
    destination.write_text("keep me", encoding="utf-8")

    with pytest.raises(ExportDestinationExistsError):
        service.export_completed(destination)

    assert destination.read_text(encoding="utf-8") == "keep me"
    assert service.export_completed(destination, overwrite=True) == 0
    with destination.open(encoding="utf-8", newline="") as exported:
        assert list(csv.reader(exported)) == [list(CSV_COLUMNS)]
