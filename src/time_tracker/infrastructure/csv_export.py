"""UTF-8 CSV output for completed time entries."""

from __future__ import annotations

import csv
from pathlib import Path

from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.domain.models import CompletedTimer

CSV_COLUMNS = (
    "project",
    "activity",
    "start_time",
    "stop_time",
    "duration_seconds",
    "note",
)


class CsvCompletedEntryWriter:
    """Write the MVP export format using standard CSV quoting."""

    def write(
        self,
        destination: Path,
        entries: list[CompletedTimer],
        *,
        overwrite: bool,
    ) -> None:
        """Write entries without overwriting unless explicitly confirmed."""
        mode = "w" if overwrite else "x"
        try:
            with destination.open(mode, encoding="utf-8", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(CSV_COLUMNS)
                for entry in entries:
                    writer.writerow(
                        (
                            entry.project,
                            entry.activity,
                            entry.started_at.astimezone().isoformat(),
                            entry.stopped_at.astimezone().isoformat(),
                            _duration_seconds(entry),
                            entry.note or "",
                        )
                    )
        except FileExistsError as error:
            raise ExportDestinationExistsError(
                f"export destination already exists: {destination}"
            ) from error


def _duration_seconds(entry: CompletedTimer) -> str:
    """Preserve microsecond precision while keeping whole seconds concise."""
    microseconds = (
        entry.duration.days * 86_400_000_000
        + entry.duration.seconds * 1_000_000
        + entry.duration.microseconds
    )
    seconds, remainder = divmod(microseconds, 1_000_000)
    if remainder == 0:
        return str(seconds)
    return f"{seconds}.{remainder:06d}".rstrip("0")
