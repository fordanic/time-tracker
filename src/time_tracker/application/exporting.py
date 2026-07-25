"""Filtered completed-time export use cases and output ports."""

from __future__ import annotations

from collections.abc import Callable
from datetime import tzinfo
from pathlib import Path
from typing import Protocol

from time_tracker.application.reporting import (
    DailySummary,
    RangeSummary,
    ReviewFilter,
    build_daily_summaries,
    build_range_summaries,
    filter_completed_entries,
)
from time_tracker.domain.models import CompletedTimer


class ExportDestinationExistsError(ValueError):
    """Raised when an export would overwrite a file without confirmation."""


class CompletedEntrySource(Protocol):
    """Read access required by completed-entry export."""

    def list_completed(self) -> list[CompletedTimer]:
        """Return completed entries in chronological order."""
        ...


class CompletedEntryWriter(Protocol):
    """Output boundary for completed entries."""

    def write(
        self,
        destination: Path,
        entries: list[CompletedTimer],
        *,
        overwrite: bool,
        delimiter: str,
    ) -> None:
        """Write entries to a destination or reject an unconfirmed overwrite."""
        ...


class DailySummaryWriter(Protocol):
    """Output boundary for daily project/activity summaries."""

    def write(
        self,
        destination: Path,
        summaries: list[DailySummary],
        *,
        overwrite: bool,
        delimiter: str,
    ) -> None:
        """Write summaries or reject an unconfirmed overwrite."""
        ...


class RangeSummaryWriter(Protocol):
    """Output boundary for selected-range project/activity totals."""

    def write(
        self,
        destination: Path,
        summaries: list[RangeSummary],
        *,
        overwrite: bool,
        delimiter: str,
    ) -> None:
        """Write range totals or reject an unconfirmed overwrite."""
        ...


class ExportService:
    """Export selected completed entries or project/activity summaries."""

    def __init__(
        self,
        source: CompletedEntrySource,
        completed_writer: CompletedEntryWriter,
        summary_writer: DailySummaryWriter,
        local_timezone: tzinfo | None = None,
        range_writer: RangeSummaryWriter | None = None,
        delimiter: Callable[[], str] | None = None,
    ) -> None:
        self._source = source
        self._completed_writer = completed_writer
        self._summary_writer = summary_writer
        self._local_timezone = local_timezone
        self._range_writer = range_writer
        self._delimiter = delimiter or (lambda: ",")

    def export_completed(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export completed entries and return the number written."""
        entries = filter_completed_entries(
            self._source.list_completed(),
            self._local_timezone,
            review_filter,
        )
        self._completed_writer.write(
            destination,
            entries,
            overwrite=overwrite,
            delimiter=self._delimiter(),
        )
        return len(entries)

    def export_daily_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export local-day summaries and return the number written."""
        summaries = build_daily_summaries(
            self._source.list_completed(),
            self._local_timezone,
            review_filter,
        )
        self._summary_writer.write(
            destination,
            summaries,
            overwrite=overwrite,
            delimiter=self._delimiter(),
        )
        return len(summaries)

    def export_range_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export selected-range totals and return the number written."""
        if self._range_writer is None:
            raise RuntimeError("range summary export is unavailable")
        summaries = build_range_summaries(
            self._source.list_completed(),
            self._local_timezone,
            review_filter,
        )
        self._range_writer.write(
            destination,
            summaries,
            overwrite=overwrite,
            delimiter=self._delimiter(),
        )
        return len(summaries)
