"""Completed-entry export use case and its output port."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

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
    ) -> None:
        """Write entries to a destination or reject an unconfirmed overwrite."""
        ...


class ExportService:
    """Export only completed entries from authoritative storage."""

    def __init__(
        self,
        source: CompletedEntrySource,
        writer: CompletedEntryWriter,
    ) -> None:
        self._source = source
        self._writer = writer

    def export_completed(self, destination: Path, *, overwrite: bool = False) -> int:
        """Export completed entries and return the number written."""
        entries = self._source.list_completed()
        self._writer.write(destination, entries, overwrite=overwrite)
        return len(entries)
