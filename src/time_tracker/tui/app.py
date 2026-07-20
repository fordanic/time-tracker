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
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Footer,
    Header,
    Input,
    OptionList,
    Static,
    Switch,
    Tab,
    Tabs,
)
from textual.widgets.option_list import Option

from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.application.reminders import Reminder, ReminderKind
from time_tracker.application.reporting import build_daily_summaries
from time_tracker.application.tracking import RecentActivity, StartAction
from time_tracker.domain.models import ActiveTimer, CompletedTimer


class TrackerGateway(Protocol):
    """Operations available to the TUI across the application boundary."""

    def get_active(self) -> ActiveTimer | None:
        """Return the recovered active timer."""
        ...

    def get_reminder(self) -> Reminder | None:
        """Return the latest reminder due in the background process."""
        ...

    def confirm_active_reminder(self) -> bool:
        """Confirm the active timer and restart its reminder interval."""
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

    def list_recent_activities(self) -> list[RecentActivity]:
        """Return recent selectable project/activity pairs."""
        ...

    def get_start_action(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> StartAction:
        """Return the application-classified effect of a capture selection."""
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

    def export_daily_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> int:
        """Export daily project/activity summaries to a confirmed destination."""
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


class PointerOnlyButton(Button):
    """A clickable button intentionally omitted from keyboard tab order."""

    can_focus = False


class TimeTrackerApp(App[None]):
    """Keyboard-first focused workflows backed by the local agent."""

    TITLE = "Time Tracker"
    SUB_TITLE = "Local, persistent time tracking"
    BINDINGS = [
        Binding("f1", "show_track", "Track"),
        Binding("f2", "show_review", "Review"),
        Binding("f3", "show_manage", "Manage"),
        Binding("f4", "show_settings", "Settings"),
        Binding("f5", "start_timer", "Timer action"),
        Binding("f6", "stop_timer", "Stop"),
        Binding("f7", "export_csv", "Export CSV"),
        Binding("f8", "archive_project", "Archive project"),
        Binding("f9", "archive_activity", "Archive activity"),
        Binding("f10", "confirm_active_reminder", "Still active"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    _VIEW_CONTENT = {
        "track-tab": "track-view",
        "review-tab": "review-view",
        "manage-tab": "manage-view",
        "settings-tab": "settings-view",
    }
    _VIEW_FOCUS = {
        "track-tab": "#project",
        "review-tab": "#history",
        "manage-tab": "#manage-project",
    }
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
        height: 3;
        padding: 0 1;
        text-align: center;
        background: $panel;
        content-align: center middle;
    }

    #view-tabs {
        height: 2;
    }

    #view-switcher, .view {
        height: 1fr;
    }

    .view {
        padding-top: 1;
    }

    #reminder {
        display: none;
        height: auto;
        margin-bottom: 1;
        padding: 0 1;
        background: $warning-muted;
    }

    #reminder-message {
        width: 1fr;
        height: auto;
        content-align: left middle;
    }

    #confirm-active-reminder-button {
        display: none;
        width: 24;
        margin-left: 1;
    }

    Input {
        margin-bottom: 0;
    }

    #manage-project-actions, #manage-activity-actions {
        height: auto;
    }

    #manage-project, #manage-activity {
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

    #recent-activities {
        height: 1;
    }

    #recent-empty {
        height: 1;
        color: $text-muted;
    }

    #export-actions {
        height: auto;
        margin-top: 0;
    }

    #export-path {
        width: 1fr;
    }

    #summary-mode-label {
        width: auto;
        height: 1;
        padding-right: 1;
    }

    #summary-mode, #summary-mode:focus {
        width: auto;
        height: 1;
        padding: 0;
        border: none;
    }

    #history-options {
        height: 1;
        align-horizontal: right;
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

    #manage-help, #settings-info {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }

    #history-title {
        margin-top: 1;
        text-style: bold;
    }

    #history {
        height: 1fr;
        min-height: 6;
    }
    """

    def __init__(self, client: TrackerGateway) -> None:
        super().__init__()
        self.client = client
        self.active_timer: ActiveTimer | None = None
        self.pending_reminder: Reminder | None = None
        self._pending_export_path: Path | None = None
        self._completed_entries: list[CompletedTimer] = []
        self._recent_activities: list[RecentActivity] = []
        self._start_action: StartAction | None = None

    def compose(self) -> ComposeResult:
        """Compose focused workflows around one persistent active-timer strip."""
        yield Header()
        with Vertical(id="tracker"):
            yield Static("No timer running", id="active-timer")
            with Horizontal(id="reminder"):
                yield Static("", id="reminder-message")
                yield Button(
                    "Still active  F10",
                    id="confirm-active-reminder-button",
                    variant="primary",
                )
            yield Tabs(
                Tab("Track  F1", id="track-tab"),
                Tab("Review  F2", id="review-tab"),
                Tab("Manage  F3", id="manage-tab"),
                Tab("Settings  F4", id="settings-tab"),
                active="track-tab",
                id="view-tabs",
            )
            with ContentSwitcher(initial="track-view", id="view-switcher"):
                with Vertical(id="track-view", classes="view"):
                    yield Input(
                        placeholder="Project (type to reuse existing)",
                        id="project",
                    )
                    yield Input(
                        placeholder="Activity (type to reuse existing)",
                        id="activity",
                    )
                    yield Input(placeholder="Optional note", id="note")
                    yield OptionList(id="recent-activities", compact=True)
                    yield Static("No recent activities yet.", id="recent-empty")
                    with Horizontal(id="actions"):
                        yield Button(
                            "Start  F5",
                            id="start-button",
                            variant="success",
                        )
                        yield Button(
                            "Stop  F6",
                            id="stop-button",
                            variant="warning",
                        )
                with Vertical(id="review-view", classes="view"):
                    with Horizontal(id="export-actions"):
                        yield Input(
                            placeholder="CSV export path (for example ~/times.csv)",
                            id="export-path",
                        )
                        yield Button("Export CSV  F7", id="export-button")
                    with Horizontal(id="history-options"):
                        yield Static("Daily summaries", id="summary-mode-label")
                        yield Switch(id="summary-mode")
                    yield Static("Completed entries", id="history-title")
                    yield DataTable(
                        id="history",
                        cursor_type="row",
                        zebra_stripes=True,
                    )
                with Vertical(id="manage-view", classes="view"):
                    yield Static(
                        "Archive selectable projects and activities. "
                        "Archived-item restore is planned for the next Manage slice.",
                        id="manage-help",
                    )
                    with Horizontal(id="manage-project-actions"):
                        yield Input(
                            placeholder="Project to archive",
                            id="manage-project",
                        )
                        yield PointerOnlyButton(
                            "Archive project  F8",
                            id="archive-project-button",
                        )
                    with Horizontal(id="manage-activity-actions"):
                        yield Input(
                            placeholder="Activity to archive",
                            id="manage-activity",
                        )
                        yield PointerOnlyButton(
                            "Archive activity  F9",
                            id="archive-activity-button",
                        )
                with Vertical(id="settings-view", classes="view"):
                    yield Static(
                        "Reminder settings are currently managed in the TOML "
                        "configuration file. Run `time-tracker --config-path` to "
                        "locate it, then restart the background process after "
                        "editing. TUI editing and live reload are planned for a "
                        "later Settings slice.",
                        id="settings-info",
                    )
            yield Static("", id="message")
        yield Footer()

    async def on_mount(self) -> None:
        """Recover any persisted active timer when the TUI reconnects."""
        self.set_interval(1.0, self._render_active)
        self.set_interval(1.0, self._refresh_reminder)
        try:
            self.active_timer = await asyncio.to_thread(self.client.get_active)
            projects = await asyncio.to_thread(self.client.list_projects)
            completed = await asyncio.to_thread(self.client.list_completed)
            recent = await asyncio.to_thread(self.client.list_recent_activities)
        except Exception as error:
            self._show_message(str(error), error=True)
        else:
            self._set_project_suggestions(projects)
            self._render_history(completed)
            self._render_recent_activities(recent)
            if self.active_timer is not None:
                self.query_one("#project", Input).value = self.active_timer.project
                self.query_one("#activity", Input).value = self.active_timer.activity
                self.query_one("#note", Input).value = self.active_timer.note or ""
        self._render_active()
        await self._refresh_start_action()
        await self._refresh_reminder()
        self._select_view("track-tab")

    @on(Tabs.TabActivated, "#view-tabs")
    def handle_view_activated(self, event: Tabs.TabActivated) -> None:
        """Show and focus the content owned by the selected tab."""
        if event.tab.id is not None:
            self._select_view(event.tab.id)

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
            await self._refresh_start_action()
            return
        if self.query_one("#project", Input).value.strip() != project:
            return
        self.query_one("#activity", Input).suggester = SuggestFromList(
            activities,
            case_sensitive=False,
        )
        await self._refresh_start_action()

    @on(Input.Changed, "#activity")
    async def handle_activity_changed(self) -> None:
        """Refresh the primary action when the selected activity changes."""
        await self._refresh_start_action()

    @on(Input.Changed, "#note")
    async def handle_note_changed(self) -> None:
        """Refresh the primary action when the selected note changes."""
        await self._refresh_start_action()

    @on(Input.Changed, "#manage-project")
    async def handle_manage_project_changed(self, event: Input.Changed) -> None:
        """Refresh Manage activity suggestions for its selected project."""
        project = event.value.strip()
        try:
            activities = await asyncio.to_thread(
                self.client.list_activities,
                project,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        if self.query_one("#manage-project", Input).value.strip() != project:
            return
        self.query_one("#manage-activity", Input).suggester = SuggestFromList(
            activities,
            case_sensitive=False,
        )

    @on(Button.Pressed, "#start-button")
    async def handle_start_button(self) -> None:
        """Handle pointer activation of the start action."""
        await self._start_timer()

    @on(OptionList.OptionSelected, "#recent-activities")
    def handle_recent_activity_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        """Populate capture inputs from one application-projected recent pair."""
        if not 0 <= event.option_index < len(self._recent_activities):
            return
        pair = self._recent_activities[event.option_index]
        self.query_one("#project", Input).value = pair.project
        self.query_one("#activity", Input).value = pair.activity
        note_input = self.query_one("#note", Input)
        note_input.value = ""
        note_input.focus()

    @on(Button.Pressed, "#stop-button")
    async def handle_stop_button(self) -> None:
        """Handle pointer activation of the stop action."""
        await self._stop_timer()

    @on(Button.Pressed, "#export-button")
    async def handle_export_button(self) -> None:
        """Handle pointer activation of the export action."""
        await self._export_current_view()

    @on(Button.Pressed, "#archive-project-button")
    async def handle_archive_project_button(self) -> None:
        """Handle pointer activation of project archiving."""
        await self._archive_project()

    @on(Button.Pressed, "#archive-activity-button")
    async def handle_archive_activity_button(self) -> None:
        """Handle pointer activation of activity archiving."""
        await self._archive_activity()

    @on(Button.Pressed, "#confirm-active-reminder-button")
    async def handle_confirm_active_reminder_button(self) -> None:
        """Confirm an active reminder from its visible prompt."""
        await self._confirm_active_reminder()

    @on(Input.Changed, "#export-path")
    def handle_export_path_changed(self) -> None:
        """Cancel overwrite confirmation when the destination is edited."""
        if self._pending_export_path is not None:
            self._clear_export_confirmation()

    @on(Switch.Changed, "#summary-mode")
    def handle_summary_mode_changed(self) -> None:
        """Render and export the representation selected by the user."""
        self._clear_export_confirmation()
        self._render_history(self._completed_entries)

    def action_show_track(self) -> None:
        """Select the Track view from the F1 binding."""
        self._select_view("track-tab")

    def action_show_review(self) -> None:
        """Select the Review view from the F2 binding."""
        self._select_view("review-tab")

    def action_show_manage(self) -> None:
        """Select the Manage view from the F3 binding."""
        self._select_view("manage-tab")

    def action_show_settings(self) -> None:
        """Select the Settings view from the F4 binding."""
        self._select_view("settings-tab")

    async def action_start_timer(self) -> None:
        """Start or switch the timer from the F5 binding."""
        await self._start_timer()

    async def action_stop_timer(self) -> None:
        """Stop the timer from the F6 binding."""
        await self._stop_timer()

    async def action_export_csv(self) -> None:
        """Export the selected representation from the F7 binding."""
        await self._export_current_view()

    async def action_archive_project(self) -> None:
        """Archive the entered project from the F8 binding."""
        await self._archive_project()

    async def action_archive_activity(self) -> None:
        """Archive the entered activity from the F9 binding."""
        await self._archive_activity()

    async def action_confirm_active_reminder(self) -> None:
        """Confirm an active reminder from the F10 binding."""
        await self._confirm_active_reminder()

    async def _start_timer(self) -> None:
        if self.query_one("#start-button", Button).disabled:
            return
        project = self.query_one("#project", Input).value
        activity = self.query_one("#activity", Input).value
        note = self.query_one("#note", Input).value
        requested_action = self._start_action
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
        self.pending_reminder = None
        self._render_reminder()
        if requested_action is StartAction.SWITCH:
            message = (
                f"Switched to {self.active_timer.project} / "
                f"{self.active_timer.activity}."
            )
        elif requested_action is StartAction.RESTART:
            message = (
                f"Restarted {self.active_timer.project} / "
                f"{self.active_timer.activity} with a new note."
            )
        else:
            message = "Timer persisted and running."
        self._show_message(message)
        self.query_one("#project", Input).value = self.active_timer.project
        self.query_one("#activity", Input).value = self.active_timer.activity
        self.query_one("#note", Input).value = self.active_timer.note or ""
        await self._refresh_project_suggestions()
        await self._refresh_history()
        await self._refresh_recent_activities()
        self._render_active()
        await self._refresh_start_action()

    async def _refresh_project_suggestions(self) -> None:
        projects = await asyncio.to_thread(self.client.list_projects)
        self._set_project_suggestions(projects)

    async def _refresh_activity_suggestions(
        self,
        project: str,
        *,
        input_selector: str = "#activity",
    ) -> None:
        activities = await asyncio.to_thread(self.client.list_activities, project)
        self.query_one(input_selector, Input).suggester = SuggestFromList(
            activities,
            case_sensitive=False,
        )

    async def _archive_project(self) -> None:
        project_input = self.query_one("#manage-project", Input)
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
        self.query_one("#manage-activity", Input).value = ""
        await self._refresh_project_suggestions()
        await self._refresh_activity_suggestions(
            "",
            input_selector="#manage-activity",
        )
        self._show_message(f"Archived project {archived_project}.")
        await self._refresh_recent_activities()

    async def _archive_activity(self) -> None:
        project = self.query_one("#manage-project", Input).value
        activity_input = self.query_one("#manage-activity", Input)
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
        await self._refresh_activity_suggestions(
            archived_project,
            input_selector="#manage-activity",
        )
        self._show_message(
            f"Archived activity {archived_project} / {archived_activity}."
        )
        await self._refresh_recent_activities()

    def _select_view(self, tab_id: str) -> None:
        """Select one view without changing any workflow state."""
        content_id = self._VIEW_CONTENT[tab_id]
        tabs = self.query_one("#view-tabs", Tabs)
        switcher = self.query_one("#view-switcher", ContentSwitcher)
        tabs.active = tab_id
        switcher.current = content_id
        focus_selector = self._VIEW_FOCUS.get(tab_id)
        if focus_selector is None:
            tabs.focus()
        else:
            self.query_one(focus_selector).focus()

    def _set_project_suggestions(self, projects: list[str]) -> None:
        """Apply canonical project suggestions to Track and Manage inputs."""
        for selector in ("#project", "#manage-project"):
            self.query_one(selector, Input).suggester = SuggestFromList(
                projects,
                case_sensitive=False,
            )

    async def _stop_timer(self) -> None:
        try:
            completed = await asyncio.to_thread(self.client.stop)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self.active_timer = None
        self.pending_reminder = None
        self._render_reminder()
        if completed is None:
            self._show_message("No active timer to stop.")
        else:
            self._show_message(
                f"Stopped {completed.project} / {completed.activity} "
                f"after {_format_duration(completed.duration)}."
            )
            await self._refresh_history()
            await self._refresh_recent_activities()
        self._render_active()
        await self._refresh_start_action()

    async def _refresh_reminder(self) -> None:
        try:
            reminder = await asyncio.to_thread(self.client.get_reminder)
        except Exception:
            return
        if reminder == self.pending_reminder:
            return
        self.pending_reminder = reminder
        self._render_reminder()

    async def _confirm_active_reminder(self) -> None:
        try:
            confirmed = await asyncio.to_thread(self.client.confirm_active_reminder)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        if not confirmed:
            await self._refresh_reminder()
            self._show_message("No active reminder to confirm.", error=True)
            return
        self.pending_reminder = None
        self._render_reminder()
        self._show_message("Timer confirmed; active reminder interval restarted.")

    async def _refresh_history(self) -> None:
        try:
            completed = await asyncio.to_thread(self.client.list_completed)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_history(completed)

    async def _refresh_recent_activities(self) -> None:
        try:
            recent = await asyncio.to_thread(self.client.list_recent_activities)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_recent_activities(recent)

    async def _refresh_start_action(self) -> None:
        project = self.query_one("#project", Input).value
        activity = self.query_one("#activity", Input).value
        note = self.query_one("#note", Input).value
        selection = (project, activity, note)
        button = self.query_one("#start-button", Button)
        try:
            action = await asyncio.to_thread(
                self.client.get_start_action,
                project,
                activity,
                note,
            )
        except Exception as error:
            self._start_action = None
            button.label = "Timer action unavailable  F5"
            button.disabled = True
            self._show_message(str(error), error=True)
            return
        current_selection = (
            self.query_one("#project", Input).value,
            self.query_one("#activity", Input).value,
            self.query_one("#note", Input).value,
        )
        if current_selection != selection:
            return
        self._start_action = action
        button.disabled = action is StartAction.ALREADY_TRACKING
        if action is StartAction.START:
            button.label = "Start  F5"
        elif action is StartAction.ALREADY_TRACKING:
            button.label = "Already tracking"
        elif action is StartAction.RESTART:
            button.label = "Restart with new note  F5"
        else:
            current = self.active_timer
            current_name = (
                f"{current.project} / {current.activity}"
                if current is not None
                else "current timer"
            )
            selected_name = (
                f"{project.strip() or '(project required)'} / "
                f"{activity.strip() or '(activity required)'}"
            )
            button.label = f"Switch from {current_name} to {selected_name}  F5"

    async def _export_current_view(self) -> None:
        raw_destination = self.query_one("#export-path", Input).value.strip()
        if not raw_destination:
            self._show_message("CSV export path is required.", error=True)
            return
        destination = Path(raw_destination).expanduser().resolve()
        overwrite = self._pending_export_path == destination
        summary_mode = self.query_one("#summary-mode", Switch).value
        export = (
            self.client.export_daily_summaries
            if summary_mode
            else self.client.export_completed
        )
        try:
            row_count = await asyncio.to_thread(
                export,
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
        if summary_mode:
            noun = "daily summary" if row_count == 1 else "daily summaries"
        else:
            noun = "entry" if row_count == 1 else "entries"
        self._show_message(f"Exported {row_count} {noun} to {destination}.")

    def _clear_export_confirmation(self) -> None:
        self._pending_export_path = None
        button = self.query_one("#export-button", Button)
        button.label = "Export CSV  F7"
        button.variant = "default"

    def _render_history(self, entries: list[CompletedTimer]) -> None:
        self._completed_entries = entries
        table = self.query_one("#history", DataTable)
        table.clear(columns=True)
        summary_mode = self.query_one("#summary-mode", Switch).value
        title = self.query_one("#history-title", Static)
        if summary_mode:
            title.update("Daily summaries")
            table.add_columns("Date", "Project", "Activity", "Duration")
            for summary in build_daily_summaries(entries):
                table.add_row(
                    summary.day.isoformat(),
                    summary.project,
                    summary.activity,
                    _format_duration(summary.duration),
                    key=(
                        f"{summary.day.isoformat()}\0{summary.project}\0"
                        f"{summary.activity}"
                    ),
                )
            return

        title.update("Completed entries")
        table.add_columns("Project", "Activity", "Start", "Stop", "Duration", "Note")
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

    def _render_recent_activities(self, recent: list[RecentActivity]) -> None:
        self._recent_activities = recent
        option_list = self.query_one("#recent-activities", OptionList)
        option_list.set_options(
            Option(
                f"Track again: {pair.project} / {pair.activity}",
                id=f"recent-{index}",
            )
            for index, pair in enumerate(recent)
        )
        option_list.highlighted = 0 if recent else None
        option_list.display = bool(recent)
        self.query_one("#recent-empty", Static).display = not recent

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

    def _render_reminder(self) -> None:
        panel = self.query_one("#reminder", Horizontal)
        button = self.query_one("#confirm-active-reminder-button", Button)
        reminder = self.pending_reminder
        panel.display = reminder is not None
        button.display = reminder is not None and reminder.kind is ReminderKind.ACTIVE
        if reminder is None:
            self.query_one("#reminder-message", Static).update("")
            return
        if reminder.kind is ReminderKind.ACTIVE:
            timer_name = " / ".join(
                part for part in (reminder.project, reminder.activity) if part
            )
            message = (
                f"Still tracking {timer_name}? Confirm to restart the reminder "
                "interval, or stop the timer."
            )
        else:
            message = "No timer is running. Start one if you are working."
        self.query_one("#reminder-message", Static).update(message)

    def _show_message(self, message: str, *, error: bool = False) -> None:
        widget = self.query_one("#message", Static)
        widget.update(message)
        widget.styles.color = self.theme_variables["error" if error else "success"]


def _format_duration(duration: timedelta) -> str:
    total_seconds = max(0, int(duration.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
