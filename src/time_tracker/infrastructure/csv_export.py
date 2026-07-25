"""UTF-8 CSV output for completed entries and Review summaries."""

from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path

from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.application.reporting import DailySummary, RangeSummary
from time_tracker.domain.models import CompletedTimer

CSV_COLUMNS = (
    "project",
    "activity",
    "start_time",
    "stop_time",
    "duration_seconds",
    "note",
)
DAILY_SUMMARY_COLUMNS = ("date", "project", "activity", "duration_seconds")
RANGE_SUMMARY_COLUMNS = ("project", "activity", "duration_seconds")


class CsvCompletedEntryWriter:
    """Write the MVP export format using standard CSV quoting."""

    def write(
        self,
        destination: Path,
        entries: list[CompletedTimer],
        *,
        overwrite: bool,
        delimiter: str,
    ) -> None:
        """Write entries without overwriting unless explicitly confirmed."""
        mode = "w" if overwrite else "x"
        try:
            with destination.open(mode, encoding="utf-8", newline="") as output:
                writer = csv.writer(output, delimiter=delimiter)
                writer.writerow(CSV_COLUMNS)
                for entry in entries:
                    writer.writerow(
                        (
                            entry.project,
                            entry.activity,
                            entry.started_at.astimezone().isoformat(),
                            entry.stopped_at.astimezone().isoformat(),
                            _duration_seconds(entry.duration),
                            entry.note or "",
                        )
                    )
        except FileExistsError as error:
            raise ExportDestinationExistsError(
                f"export destination already exists: {destination}"
            ) from error


class CsvDailySummaryWriter:
    """Write one row per local day, project, and activity."""

    def write(
        self,
        destination: Path,
        summaries: list[DailySummary],
        *,
        overwrite: bool,
        delimiter: str,
    ) -> None:
        """Write summaries without overwriting unless explicitly confirmed."""
        mode = "w" if overwrite else "x"
        try:
            with destination.open(mode, encoding="utf-8", newline="") as output:
                writer = csv.writer(output, delimiter=delimiter)
                writer.writerow(DAILY_SUMMARY_COLUMNS)
                for summary in summaries:
                    writer.writerow(
                        (
                            summary.day.isoformat(),
                            summary.project,
                            summary.activity,
                            _duration_seconds(summary.duration),
                        )
                    )
        except FileExistsError as error:
            raise ExportDestinationExistsError(
                f"export destination already exists: {destination}"
            ) from error


class CsvRangeSummaryWriter:
    """Write one row per selected project and activity."""

    def write(
        self,
        destination: Path,
        summaries: list[RangeSummary],
        *,
        overwrite: bool,
        delimiter: str,
    ) -> None:
        """Write range totals without overwriting unless explicitly confirmed."""
        mode = "w" if overwrite else "x"
        try:
            with destination.open(mode, encoding="utf-8", newline="") as output:
                writer = csv.writer(output, delimiter=delimiter)
                writer.writerow(RANGE_SUMMARY_COLUMNS)
                for summary in summaries:
                    writer.writerow(
                        (
                            summary.project,
                            summary.activity,
                            _duration_seconds(summary.duration),
                        )
                    )
        except FileExistsError as error:
            raise ExportDestinationExistsError(
                f"export destination already exists: {destination}"
            ) from error


def _duration_seconds(duration: timedelta) -> str:
    """Preserve microsecond precision while keeping whole seconds concise."""
    microseconds = (
        duration.days * 86_400_000_000
        + duration.seconds * 1_000_000
        + duration.microseconds
    )
    seconds, remainder = divmod(microseconds, 1_000_000)
    if remainder == 0:
        return str(seconds)
    return f"{seconds}.{remainder:06d}".rstrip("0")
