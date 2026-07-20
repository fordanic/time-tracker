"""Textual interface for the first persistent timer workflow."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
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
from time_tracker.application.tracking import (
    ArchivedActivity,
    RecentActivity,
    StartAction,
)
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

    def correct_completed(
        self,
        entry_id: int,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer:
        """Correct one completed entry and return its canonical values."""
        ...

    def create_manual_entry(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer:
        """Create one completed entry for missed time."""
        ...

    def edit_active(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> ActiveTimer:
        """Update active details without restarting the timer."""
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

    def get_archive_project_target(self, project: str) -> str:
        """Validate and return a canonical project archive target."""
        ...

    def archive_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Archive an activity and return its canonical stored names."""
        ...

    def get_archive_activity_target(
        self,
        project: str,
        activity: str,
    ) -> tuple[str, str]:
        """Validate and return a canonical activity archive target."""
        ...

    def list_archived_projects(self) -> list[str]:
        """Return canonical archived project names."""
        ...

    def list_archived_activities(self) -> list[ArchivedActivity]:
        """Return archived activities with canonical parent state."""
        ...

    def unarchive_project(self, project: str) -> str:
        """Restore one archived project."""
        ...

    def unarchive_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Restore one archived activity."""
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
        Binding("f11", "edit_active", "Update active"),
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

    #archived-projects, #archived-activities {
        height: 4;
        margin-bottom: 0;
    }

    #archived-projects-empty, #archived-activities-empty {
        height: 1;
        color: $text-muted;
    }

    #restore-project-button, #restore-activity-button {
        width: 30;
        margin-bottom: 1;
    }

    .manage-title {
        height: 1;
        text-style: bold;
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
        height: 3;
        align-horizontal: right;
    }

    #load-correction-button, #add-manual-entry-button {
        width: 24;
        margin-right: 1;
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

    #correction-title {
        margin-top: 1;
        text-style: bold;
    }

    #correction-target, #correction-times, #correction-actions {
        height: auto;
    }

    #correction-target Input, #correction-times Input {
        width: 1fr;
    }

    #correction-project, #correction-start {
        margin-right: 1;
    }

    #correction-actions Button {
        width: 1fr;
        margin-right: 1;
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
        self._archived_projects: list[str] = []
        self._archived_activities: list[ArchivedActivity] = []
        self._start_action: StartAction | None = None
        self._editing_entry_id: int | None = None
        self._creating_manual_entry = False
        self._pending_archive_project: tuple[str, str] | None = None
        self._pending_archive_activity: tuple[str, str, str, str] | None = None

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
                        yield Button(
                            "Update active details  F11",
                            id="edit-active-button",
                            disabled=True,
                        )
                with VerticalScroll(id="review-view", classes="view"):
                    with Horizontal(id="export-actions"):
                        yield Input(
                            placeholder="CSV export path (for example ~/times.csv)",
                            id="export-path",
                        )
                        yield Button("Export CSV  F7", id="export-button")
                    with Horizontal(id="history-options"):
                        yield Button(
                            "Load selected entry",
                            id="load-correction-button",
                        )
                        yield Button(
                            "Add missed entry",
                            id="add-manual-entry-button",
                        )
                        yield Static("Daily summaries", id="summary-mode-label")
                        yield Switch(id="summary-mode")
                    yield Static("Completed entries", id="history-title")
                    yield DataTable(
                        id="history",
                        cursor_type="row",
                        zebra_stripes=True,
                    )
                    yield Static("Correct selected entry", id="correction-title")
                    with Horizontal(id="correction-target"):
                        yield Input(
                            placeholder="Project",
                            id="correction-project",
                        )
                        yield Input(
                            placeholder="Activity",
                            id="correction-activity",
                        )
                    yield Input(placeholder="Optional note", id="correction-note")
                    with Horizontal(id="correction-times"):
                        yield Input(
                            placeholder="Start (ISO 8601 with UTC offset)",
                            id="correction-start",
                        )
                        yield Input(
                            placeholder="Stop (ISO 8601 with UTC offset)",
                            id="correction-stop",
                        )
                    with Horizontal(id="correction-actions"):
                        yield Button(
                            "Save correction",
                            id="save-correction-button",
                            variant="primary",
                            disabled=True,
                        )
                with VerticalScroll(id="manage-view", classes="view"):
                    yield Static(
                        "Archive selectable projects and activities after confirming "
                        "the exact target, or restore an archived item below.",
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
                    yield Static("Archived projects", classes="manage-title")
                    yield OptionList(id="archived-projects", compact=True)
                    yield Static(
                        "No archived projects.",
                        id="archived-projects-empty",
                    )
                    yield Button(
                        "Restore selected project",
                        id="restore-project-button",
                        disabled=True,
                    )
                    yield Static("Archived activities", classes="manage-title")
                    yield OptionList(id="archived-activities", compact=True)
                    yield Static(
                        "No archived activities.",
                        id="archived-activities-empty",
                    )
                    yield Button(
                        "Restore selected activity",
                        id="restore-activity-button",
                        disabled=True,
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
            archived_projects = await asyncio.to_thread(
                self.client.list_archived_projects
            )
            archived_activities = await asyncio.to_thread(
                self.client.list_archived_activities
            )
        except Exception as error:
            self._show_message(str(error), error=True)
        else:
            self._set_project_suggestions(projects)
            self._render_history(completed)
            self._render_recent_activities(recent)
            self._render_archived_items(archived_projects, archived_activities)
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
        if (
            self._pending_archive_project is not None
            and self._pending_archive_project[0] != project
        ):
            self._clear_project_archive_confirmation()
        if (
            self._pending_archive_activity is not None
            and self._pending_archive_activity[0] != project
        ):
            self._clear_activity_archive_confirmation()
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

    @on(Input.Changed, "#manage-activity")
    def handle_manage_activity_changed(self, event: Input.Changed) -> None:
        """Cancel activity archive confirmation when its target changes."""
        if (
            self._pending_archive_activity is not None
            and self._pending_archive_activity[1] != event.value.strip()
        ):
            self._clear_activity_archive_confirmation()

    @on(Input.Changed, "#correction-project")
    async def handle_correction_project_changed(self, event: Input.Changed) -> None:
        """Refresh correction activity suggestions for the edited project."""
        project = event.value.strip()
        try:
            activities = await asyncio.to_thread(
                self.client.list_activities,
                project,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        if self.query_one("#correction-project", Input).value.strip() != project:
            return
        self.query_one("#correction-activity", Input).suggester = SuggestFromList(
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

    @on(Button.Pressed, "#edit-active-button")
    async def handle_edit_active_button(self) -> None:
        """Handle pointer activation of active-detail editing."""
        await self._edit_active()

    @on(Button.Pressed, "#export-button")
    async def handle_export_button(self) -> None:
        """Handle pointer activation of the export action."""
        await self._export_current_view()

    @on(Button.Pressed, "#load-correction-button")
    async def handle_load_correction_button(self) -> None:
        """Load the selected completed row into correction fields."""
        await self._load_selected_correction()

    @on(Button.Pressed, "#add-manual-entry-button")
    async def handle_add_manual_entry_button(self) -> None:
        """Prepare the Review editor for one missed-time entry."""
        await self._start_manual_entry()

    @on(Button.Pressed, "#save-correction-button")
    async def handle_save_correction_button(self) -> None:
        """Persist the correction currently shown in Review."""
        await self._save_correction()

    @on(Button.Pressed, "#archive-project-button")
    async def handle_archive_project_button(self) -> None:
        """Handle pointer activation of project archiving."""
        await self._archive_project()

    @on(Button.Pressed, "#archive-activity-button")
    async def handle_archive_activity_button(self) -> None:
        """Handle pointer activation of activity archiving."""
        await self._archive_activity()

    @on(Button.Pressed, "#restore-project-button")
    async def handle_restore_project_button(self) -> None:
        """Restore the archived project selected in Manage."""
        await self._restore_project()

    @on(Button.Pressed, "#restore-activity-button")
    async def handle_restore_activity_button(self) -> None:
        """Restore the archived activity selected in Manage."""
        await self._restore_activity()

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

    async def action_edit_active(self) -> None:
        """Update active details from the F11 binding."""
        await self._edit_active()

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

    async def _edit_active(self) -> None:
        button = self.query_one("#edit-active-button", Button)
        if button.disabled:
            return
        try:
            self.active_timer = await asyncio.to_thread(
                self.client.edit_active,
                self.query_one("#project", Input).value,
                self.query_one("#activity", Input).value,
                self.query_one("#note", Input).value,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        active = self.active_timer
        self.query_one("#project", Input).value = active.project
        self.query_one("#activity", Input).value = active.activity
        self.query_one("#note", Input).value = active.note or ""
        await self._refresh_project_suggestions()
        self._render_active()
        await self._refresh_start_action()
        self._show_message(
            f"Updated active details to {active.project} / {active.activity}."
        )

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

    async def _refresh_all_activity_suggestions(self) -> None:
        for project_selector, activity_selector in (
            ("#project", "#activity"),
            ("#manage-project", "#manage-activity"),
            ("#correction-project", "#correction-activity"),
        ):
            await self._refresh_activity_suggestions(
                self.query_one(project_selector, Input).value.strip(),
                input_selector=activity_selector,
            )

    async def _archive_project(self) -> None:
        project_input = self.query_one("#manage-project", Input)
        project = project_input.value
        try:
            target = await asyncio.to_thread(
                self.client.get_archive_project_target,
                project,
            )
        except Exception as error:
            self._clear_project_archive_confirmation()
            self._show_message(str(error), error=True)
            return
        pending = (project.strip(), target)
        if self._pending_archive_project != pending:
            self._pending_archive_project = pending
            self.query_one(
                "#archive-project-button", Button
            ).label = "Confirm archive  F8"
            self._show_message(
                f"Press Archive project again to confirm {target}. "
                "Any active timer will continue."
            )
            return
        try:
            archived_project = await asyncio.to_thread(
                self.client.archive_project,
                target,
            )
        except Exception as error:
            self._clear_project_archive_confirmation()
            self._show_message(str(error), error=True)
            return
        self._clear_project_archive_confirmation()
        project_input.value = ""
        self.query_one("#manage-activity", Input).value = ""
        await self._refresh_project_suggestions()
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_archived_items()
        self._show_message(f"Archived project {archived_project}.")

    async def _archive_activity(self) -> None:
        project = self.query_one("#manage-project", Input).value
        activity_input = self.query_one("#manage-activity", Input)
        activity = activity_input.value
        try:
            target = await asyncio.to_thread(
                self.client.get_archive_activity_target,
                project,
                activity,
            )
        except Exception as error:
            self._clear_activity_archive_confirmation()
            self._show_message(str(error), error=True)
            return
        pending = (project.strip(), activity.strip(), target[0], target[1])
        if self._pending_archive_activity != pending:
            self._pending_archive_activity = pending
            self.query_one(
                "#archive-activity-button", Button
            ).label = "Confirm archive  F9"
            self._show_message(
                "Press Archive activity again to confirm "
                f"{target[0]} / {target[1]}. Any active timer will continue."
            )
            return
        try:
            archived_project, archived_activity = await asyncio.to_thread(
                self.client.archive_activity,
                *target,
            )
        except Exception as error:
            self._clear_activity_archive_confirmation()
            self._show_message(str(error), error=True)
            return
        self._clear_activity_archive_confirmation()
        self.query_one("#manage-project", Input).value = archived_project
        activity_input.value = ""
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_archived_items()
        self._show_message(
            f"Archived activity {archived_project} / {archived_activity}."
        )

    async def _restore_project(self) -> None:
        option_list = self.query_one("#archived-projects", OptionList)
        index = option_list.highlighted
        if index is None or not 0 <= index < len(self._archived_projects):
            self._show_message("Select an archived project to restore.", error=True)
            return
        project = self._archived_projects[index]
        try:
            restored_project = await asyncio.to_thread(
                self.client.unarchive_project,
                project,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self.query_one("#manage-project", Input).value = restored_project
        self.query_one("#manage-activity", Input).value = ""
        await self._refresh_project_suggestions()
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_archived_items()
        self._show_message(f"Restored project {restored_project}.")

    async def _restore_activity(self) -> None:
        option_list = self.query_one("#archived-activities", OptionList)
        index = option_list.highlighted
        if index is None or not 0 <= index < len(self._archived_activities):
            self._show_message("Select an archived activity to restore.", error=True)
            return
        item = self._archived_activities[index]
        try:
            restored_project, restored_activity = await asyncio.to_thread(
                self.client.unarchive_activity,
                item.project,
                item.activity,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self.query_one("#manage-project", Input).value = restored_project
        self.query_one("#manage-activity", Input).value = restored_activity
        await self._refresh_project_suggestions()
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_archived_items()
        self._show_message(
            f"Restored activity {restored_project} / {restored_activity}."
        )

    def _clear_project_archive_confirmation(self) -> None:
        self._pending_archive_project = None
        buttons = self.query("#archive-project-button")
        if buttons:
            buttons.first(Button).label = "Archive project  F8"

    def _clear_activity_archive_confirmation(self) -> None:
        self._pending_archive_activity = None
        buttons = self.query("#archive-activity-button")
        if buttons:
            buttons.first(Button).label = "Archive activity  F9"

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
        for selector in ("#project", "#manage-project", "#correction-project"):
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

    async def _refresh_history(self, *, preferred_entry_id: int | None = None) -> None:
        try:
            completed = await asyncio.to_thread(self.client.list_completed)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_history(completed, preferred_entry_id=preferred_entry_id)

    async def _load_selected_correction(self) -> None:
        if self.query_one("#summary-mode", Switch).value:
            self._show_message(
                "Switch to completed entries before correcting an entry.",
                error=True,
            )
            return
        table = self.query_one("#history", DataTable)
        if not self._completed_entries or table.cursor_row >= len(
            self._completed_entries
        ):
            self._show_message("Select a completed entry to correct.", error=True)
            return
        entry = self._completed_entries[table.cursor_row]
        self._populate_correction(entry)
        self.query_one("#correction-project", Input).focus()

    async def _start_manual_entry(self) -> None:
        if self.query_one("#summary-mode", Switch).value:
            self._show_message(
                "Switch to completed entries before adding missed time.",
                error=True,
            )
            return
        stopped_at = datetime.now().astimezone().replace(second=0, microsecond=0)
        started_at = stopped_at - timedelta(hours=1)
        self._editing_entry_id = None
        self._creating_manual_entry = True
        self.query_one("#correction-title", Static).update("Add missed entry")
        self.query_one("#correction-project", Input).value = ""
        self.query_one("#correction-activity", Input).value = ""
        self.query_one("#correction-note", Input).value = ""
        self.query_one("#correction-start", Input).value = started_at.isoformat(
            timespec="seconds"
        )
        self.query_one("#correction-stop", Input).value = stopped_at.isoformat(
            timespec="seconds"
        )
        save_button = self.query_one("#save-correction-button", Button)
        save_button.label = "Create missed entry"
        save_button.disabled = False
        self.query_one("#correction-project", Input).focus()

    def _populate_correction(self, entry: CompletedTimer) -> None:
        self._editing_entry_id = entry.entry_id
        self._creating_manual_entry = False
        self.query_one("#correction-title", Static).update("Correct selected entry")
        self.query_one("#correction-project", Input).value = entry.project
        self.query_one("#correction-activity", Input).value = entry.activity
        self.query_one("#correction-note", Input).value = entry.note or ""
        self.query_one(
            "#correction-start", Input
        ).value = entry.started_at.astimezone().isoformat(timespec="seconds")
        self.query_one(
            "#correction-stop", Input
        ).value = entry.stopped_at.astimezone().isoformat(timespec="seconds")
        save_button = self.query_one("#save-correction-button", Button)
        save_button.label = "Save correction"
        save_button.disabled = False

    async def _save_correction(self) -> None:
        entry_id = self._editing_entry_id
        if self.query_one("#summary-mode", Switch).value or (
            entry_id is None and not self._creating_manual_entry
        ):
            self._show_message(
                "Load a completed entry or choose Add missed entry before saving.",
                error=True,
            )
            return
        try:
            started_at = _parse_offset_datetime(
                self.query_one("#correction-start", Input).value,
                "start",
            )
            stopped_at = _parse_offset_datetime(
                self.query_one("#correction-stop", Input).value,
                "stop",
            )
            project = self.query_one("#correction-project", Input).value
            activity = self.query_one("#correction-activity", Input).value
            note = self.query_one("#correction-note", Input).value
            if self._creating_manual_entry:
                persisted = await asyncio.to_thread(
                    self.client.create_manual_entry,
                    project,
                    activity,
                    started_at,
                    stopped_at,
                    note,
                )
            else:
                if entry_id is None:
                    raise RuntimeError("no completed entry is loaded")
                persisted = await asyncio.to_thread(
                    self.client.correct_completed,
                    entry_id,
                    project,
                    activity,
                    started_at,
                    stopped_at,
                    note,
                )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        was_manual_entry = self._creating_manual_entry
        await self._refresh_history(preferred_entry_id=persisted.entry_id)
        await self._refresh_recent_activities()
        await self._refresh_project_suggestions()
        self._populate_correction(persisted)
        verb = "Added missed entry for" if was_manual_entry else "Corrected"
        self._show_message(f"{verb} {persisted.project} / {persisted.activity}.")

    async def _refresh_recent_activities(self) -> None:
        try:
            recent = await asyncio.to_thread(self.client.list_recent_activities)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_recent_activities(recent)

    async def _refresh_archived_items(self) -> None:
        try:
            projects = await asyncio.to_thread(self.client.list_archived_projects)
            activities = await asyncio.to_thread(self.client.list_archived_activities)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_archived_items(projects, activities)

    async def _refresh_start_action(self) -> None:
        project = self.query_one("#project", Input).value
        activity = self.query_one("#activity", Input).value
        note = self.query_one("#note", Input).value
        selection = (project, activity, note)
        button = self.query_one("#start-button", Button)
        edit_button = self.query_one("#edit-active-button", Button)
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
            edit_button.disabled = True
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
        edit_button.disabled = (
            self.active_timer is None or action is StartAction.ALREADY_TRACKING
        )
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

    def _render_history(
        self,
        entries: list[CompletedTimer],
        *,
        preferred_entry_id: int | None = None,
    ) -> None:
        self._completed_entries = entries
        table = self.query_one("#history", DataTable)
        table.clear(columns=True)
        summary_mode = self.query_one("#summary-mode", Switch).value
        title = self.query_one("#history-title", Static)
        load_button = self.query_one("#load-correction-button", Button)
        manual_button = self.query_one("#add-manual-entry-button", Button)
        save_button = self.query_one("#save-correction-button", Button)
        correction_inputs = self.query("#review-view Input").exclude("#export-path")
        for correction_input in correction_inputs:
            correction_input.disabled = summary_mode
        load_button.disabled = summary_mode or not entries
        manual_button.disabled = summary_mode
        save_button.disabled = summary_mode or (
            self._editing_entry_id is None and not self._creating_manual_entry
        )
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
        if preferred_entry_id is not None:
            for index, entry in enumerate(entries):
                if entry.entry_id == preferred_entry_id:
                    table.move_cursor(row=index)
                    break

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

    def _render_archived_items(
        self,
        projects: list[str],
        activities: list[ArchivedActivity],
    ) -> None:
        self._archived_projects = projects
        self._archived_activities = activities

        project_list = self.query_one("#archived-projects", OptionList)
        project_list.set_options(
            Option(project, id=f"archived-project-{index}")
            for index, project in enumerate(projects)
        )
        project_list.highlighted = 0 if projects else None
        project_list.display = bool(projects)
        self.query_one("#archived-projects-empty", Static).display = not projects
        self.query_one("#restore-project-button", Button).disabled = not projects

        activity_list = self.query_one("#archived-activities", OptionList)
        activity_list.set_options(
            Option(
                f"{item.project} / {item.activity}"
                + (" — restore project first" if item.project_archived else ""),
                id=f"archived-activity-{index}",
            )
            for index, item in enumerate(activities)
        )
        activity_list.highlighted = 0 if activities else None
        activity_list.display = bool(activities)
        self.query_one("#archived-activities-empty", Static).display = not activities
        self.query_one("#restore-activity-button", Button).disabled = not activities

    def _render_active(self) -> None:
        active_widgets = self.query("#active-timer")
        stop_buttons = self.query("#stop-button")
        edit_buttons = self.query("#edit-active-button")
        if not active_widgets or not stop_buttons or not edit_buttons:
            return
        active_widget = active_widgets.first(Static)
        stop_button = stop_buttons.first(Button)
        edit_button = edit_buttons.first(Button)
        if self.active_timer is None:
            active_widget.update("No timer running")
            stop_button.disabled = True
            edit_button.disabled = True
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
        panels = self.query("#reminder")
        buttons = self.query("#confirm-active-reminder-button")
        message_widgets = self.query("#reminder-message")
        if not panels or not buttons or not message_widgets:
            return
        panel = panels.first(Horizontal)
        button = buttons.first(Button)
        message_widget = message_widgets.first(Static)
        reminder = self.pending_reminder
        panel.display = reminder is not None
        button.display = reminder is not None and reminder.kind is ReminderKind.ACTIVE
        if reminder is None:
            message_widget.update("")
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
        message_widget.update(message)

    def _show_message(self, message: str, *, error: bool = False) -> None:
        widget = self.query_one("#message", Static)
        widget.update(message)
        widget.styles.color = self.theme_variables["error" if error else "success"]


def _format_duration(duration: timedelta) -> str:
    total_seconds = max(0, int(duration.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _parse_offset_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed
