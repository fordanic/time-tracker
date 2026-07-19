"""Textual interface for the first persistent timer workflow."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.domain.models import ActiveTimer, CompletedTimer


class TrackerGateway(Protocol):
    """Operations available to the TUI across the application boundary."""

    def get_active(self) -> ActiveTimer | None:
        """Return the recovered active timer."""
        ...

    def list_projects(self) -> list[str]:
        """Return project names available for autocomplete."""
        ...

    def list_activities(self, project: str) -> list[str]:
        """Return activity names available for the selected project."""
        ...

    def list_completed(self) -> list[CompletedTimer]:
        """Return completed entries in chronological order."""
        ...

    def archive_project(self, project: str) -> str:
        """Archive a project and return its canonical stored name."""
        ...

    def archive_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Archive an activity and return its canonical stored names."""
        ...

    def export_completed(self, destination: Path, *, overwrite: bool = False) -> int:
        """Export completed entries to a confirmed destination."""
        ...

    def start(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> ActiveTimer:
        """Persist and return a new active timer."""
        ...

    def stop(self) -> CompletedTimer | None:
        """Persist and return the stopped timer."""
        ...


class TimeTrackerApp(App[None]):
    """Keyboard-first start/stop screen backed by the local agent."""

    TITLE = "Time Tracker"
    SUB_TITLE = "Persistent walking skeleton"
    BINDINGS = [
        Binding("f5", "start_timer", "Start / switch"),
        Binding("f6", "stop_timer", "Stop"),
        Binding("f7", "export_completed", "Export CSV"),
        Binding("f8", "archive_project", "Archive project"),
        Binding("f9", "archive_activity", "Archive activity"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    CSS = """
    Screen {
        align: center middle;
    }

    #tracker {
        width: 100%;
        max-width: 120;
        height: 1fr;
        padding: 0 2;
        border: round $accent;
    }

    #active-timer {
        height: 4;
        padding: 0 1;
        text-align: center;
        background: $panel;
        content-align: center middle;
    }

    Input {
        margin-bottom: 0;
    }

    #project-actions, #activity-actions {
        height: auto;
    }

    #project, #activity {
        width: 1fr;
    }

    #archive-project-button, #archive-activity-button {
        width: 26;
        margin-left: 1;
    }

    #actions {
        height: auto;
        margin-top: 0;
    }

    #actions Button {
        width: 1fr;
        margin-right: 1;
    }

    #export-actions {
        height: auto;
        margin-top: 1;
    }

    #export-path {
        width: 1fr;
    }

    #export-button {
        width: 24;
        margin-left: 1;
    }

    #message {
        height: 2;
        margin-top: 1;
        color: $text-muted;
    }

    #history-title {
        margin-top: 1;
        text-style: bold;
    }

    #history {
        height: 1fr;
        min-height: 8;
    }
    """

    def __init__(self, client: TrackerGateway) -> None:
        super().__init__()
        self.client = client
        self.active_timer: ActiveTimer | None = None
        self._pending_export_path: Path | None = None

    def compose(self) -> ComposeResult:
        """Compose the single-screen timer workflow."""
        yield Header()
        with Vertical(id="tracker"):
            yield Static("No timer running", id="active-timer")
            with Horizontal(id="project-actions"):
                yield Input(
                    placeholder="Project (type to reuse existing)",
                    id="project",
                )
                yield Button("Archive project  F8", id="archive-project-button")
            with Horizontal(id="activity-actions"):
                yield Input(
                    placeholder="Activity (type to reuse existing)",
                    id="activity",
                )
                yield Button("Archive activity  F9", id="archive-activity-button")
            yield Input(placeholder="Optional note", id="note")
            with Horizontal(id="actions"):
                yield Button("Start / switch  F5", id="start-button", variant="success")
                yield Button("Stop  F6", id="stop-button", variant="warning")
            with Horizontal(id="export-actions"):
                yield Input(
                    placeholder="CSV export path (for example ~/times.csv)",
                    id="export-path",
                )
                yield Button("Export CSV  F7", id="export-button")
            yield Static("", id="message")
            yield Static("Completed entries", id="history-title")
            yield DataTable(id="history", cursor_type="row", zebra_stripes=True)
        yield Footer()

    async def on_mount(self) -> None:
        """Recover any persisted active timer when the TUI reconnects."""
        self.set_interval(1.0, self._render_active)
        history = self.query_one("#history", DataTable)
        history.add_columns("Project", "Activity", "Start", "Stop", "Duration", "Note")
        try:
            self.active_timer = await asyncio.to_thread(self.client.get_active)
            projects = await asyncio.to_thread(self.client.list_projects)
            completed = await asyncio.to_thread(self.client.list_completed)
        except Exception as error:
            self._show_message(str(error), error=True)
        else:
            self.query_one("#project", Input).suggester = SuggestFromList(
                projects,
                case_sensitive=False,
            )
            self._render_history(completed)
        self._render_active()

    @on(Input.Changed, "#project")
    async def handle_project_changed(self, event: Input.Changed) -> None:
        """Refresh activity completions when the selected project changes."""
        project = event.value.strip()
        try:
            activities = await asyncio.to_thread(
                self.client.list_activities,
                project,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        if self.query_one("#project", Input).value.strip() != project:
            return
        self.query_one("#activity", Input).suggester = SuggestFromList(
            activities,
            case_sensitive=False,
        )

    @on(Button.Pressed, "#start-button")
    async def handle_start_button(self) -> None:
        """Handle pointer activation of the start action."""
        await self._start_timer()

    @on(Button.Pressed, "#stop-button")
    async def handle_stop_button(self) -> None:
        """Handle pointer activation of the stop action."""
        await self._stop_timer()

    @on(Button.Pressed, "#export-button")
    async def handle_export_button(self) -> None:
        """Handle pointer activation of the export action."""
        await self._export_completed()

    @on(Button.Pressed, "#archive-project-button")
    async def handle_archive_project_button(self) -> None:
        """Handle pointer activation of project archiving."""
        await self._archive_project()

    @on(Button.Pressed, "#archive-activity-button")
    async def handle_archive_activity_button(self) -> None:
        """Handle pointer activation of activity archiving."""
        await self._archive_activity()

    @on(Input.Changed, "#export-path")
    def handle_export_path_changed(self) -> None:
        """Cancel overwrite confirmation when the destination is edited."""
        if self._pending_export_path is not None:
            self._clear_export_confirmation()

    async def action_start_timer(self) -> None:
        """Start or switch the timer from the F5 binding."""
        await self._start_timer()

    async def action_stop_timer(self) -> None:
        """Stop the timer from the F6 binding."""
        await self._stop_timer()

    async def action_export_completed(self) -> None:
        """Export completed entries from the F7 binding."""
        await self._export_completed()

    async def action_archive_project(self) -> None:
        """Archive the entered project from the F8 binding."""
        await self._archive_project()

    async def action_archive_activity(self) -> None:
        """Archive the entered activity from the F9 binding."""
        await self._archive_activity()

    async def _start_timer(self) -> None:
        project = self.query_one("#project", Input).value
        activity = self.query_one("#activity", Input).value
        note = self.query_one("#note", Input).value
        try:
            self.active_timer = await asyncio.to_thread(
                self.client.start,
                project,
                activity,
                note,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._show_message("Timer persisted and running.")
        self.query_one("#project", Input).value = self.active_timer.project
        self.query_one("#activity", Input).value = self.active_timer.activity
        await self._refresh_project_suggestions()
        await self._refresh_history()
        self._render_active()

    async def _refresh_project_suggestions(self) -> None:
        projects = await asyncio.to_thread(self.client.list_projects)
        self.query_one("#project", Input).suggester = SuggestFromList(
            projects,
            case_sensitive=False,
        )

    async def _refresh_activity_suggestions(self, project: str) -> None:
        activities = await asyncio.to_thread(self.client.list_activities, project)
        self.query_one("#activity", Input).suggester = SuggestFromList(
            activities,
            case_sensitive=False,
        )

    async def _archive_project(self) -> None:
        project_input = self.query_one("#project", Input)
        project = project_input.value
        try:
            archived_project = await asyncio.to_thread(
                self.client.archive_project,
                project,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        project_input.value = ""
        self.query_one("#activity", Input).value = ""
        await self._refresh_project_suggestions()
        await self._refresh_activity_suggestions("")
        self._show_message(f"Archived project {archived_project}.")

    async def _archive_activity(self) -> None:
        project = self.query_one("#project", Input).value
        activity_input = self.query_one("#activity", Input)
        activity = activity_input.value
        try:
            archived_project, archived_activity = await asyncio.to_thread(
                self.client.archive_activity,
                project,
                activity,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        activity_input.value = ""
        await self._refresh_activity_suggestions(archived_project)
        self._show_message(
            f"Archived activity {archived_project} / {archived_activity}."
        )

    async def _stop_timer(self) -> None:
        try:
            completed = await asyncio.to_thread(self.client.stop)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self.active_timer = None
        if completed is None:
            self._show_message("No active timer to stop.")
        else:
            self._show_message(
                f"Stopped {completed.project} / {completed.activity} "
                f"after {_format_duration(completed.duration)}."
            )
            await self._refresh_history()
        self._render_active()

    async def _refresh_history(self) -> None:
        try:
            completed = await asyncio.to_thread(self.client.list_completed)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_history(completed)

    async def _export_completed(self) -> None:
        raw_destination = self.query_one("#export-path", Input).value.strip()
        if not raw_destination:
            self._show_message("CSV export path is required.", error=True)
            return
        destination = Path(raw_destination).expanduser().resolve()
        overwrite = self._pending_export_path == destination
        try:
            entry_count = await asyncio.to_thread(
                self.client.export_completed,
                destination,
                overwrite=overwrite,
            )
        except ExportDestinationExistsError:
            self._pending_export_path = destination
            button = self.query_one("#export-button", Button)
            button.label = "Overwrite CSV  F7"
            button.variant = "warning"
            self._show_message(
                f"{destination} exists. Press Overwrite CSV again to confirm.",
                error=True,
            )
            return
        except Exception as error:
            self._clear_export_confirmation()
            self._show_message(str(error), error=True)
            return

        self._clear_export_confirmation()
        noun = "entry" if entry_count == 1 else "entries"
        self._show_message(f"Exported {entry_count} {noun} to {destination}.")

    def _clear_export_confirmation(self) -> None:
        self._pending_export_path = None
        button = self.query_one("#export-button", Button)
        button.label = "Export CSV  F7"
        button.variant = "default"

    def _render_history(self, entries: list[CompletedTimer]) -> None:
        table = self.query_one("#history", DataTable)
        table.clear()
        for entry in entries:
            table.add_row(
                entry.project,
                entry.activity,
                entry.started_at.astimezone().isoformat(timespec="seconds"),
                entry.stopped_at.astimezone().isoformat(timespec="seconds"),
                _format_duration(entry.duration),
                entry.note or "",
                key=str(entry.entry_id),
            )

    def _render_active(self) -> None:
        active_widget = self.query_one("#active-timer", Static)
        stop_button = self.query_one("#stop-button", Button)
        if self.active_timer is None:
            active_widget.update("No timer running")
            stop_button.disabled = True
            return

        timer = self.active_timer
        now = datetime.now(UTC)
        elapsed = max(now - timer.started_at, timedelta())
        local_start = timer.started_at.astimezone().isoformat(timespec="seconds")
        note = f"\n{timer.note}" if timer.note else ""
        active_widget.update(
            f"{timer.project} / {timer.activity}\n"
            f"Started {local_start} · {_format_duration(elapsed)}{note}"
        )
        stop_button.disabled = False

    def _show_message(self, message: str, *, error: bool = False) -> None:
        widget = self.query_one("#message", Static)
        widget.update(message)
        widget.styles.color = self.theme_variables["error" if error else "success"]


def _format_duration(duration: timedelta) -> str:
    total_seconds = max(0, int(duration.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
