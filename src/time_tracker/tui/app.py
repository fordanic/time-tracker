"""Textual interface for the first persistent timer workflow."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.theme import Theme
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Header,
    Input,
    OptionList,
    Select,
    Static,
    Switch,
    Tab,
    Tabs,
    Tree,
)
from textual.widgets.option_list import Option

from time_tracker.application.configuration import ReminderSettings
from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.application.idle import IdleDetectionStatus
from time_tracker.application.reminders import Reminder, ReminderKind, ReminderReason
from time_tracker.application.reporting import (
    DatePreset,
    ReviewFilter,
    build_daily_review,
    build_daily_summaries,
    build_range_summaries,
    review_filter_activities,
    review_filter_for_preset,
    review_filter_projects,
)
from time_tracker.application.tracking import (
    ArchivedActivity,
    QuickSwitchAction,
    RecentActivity,
    StartAction,
    classify_quick_switch,
)
from time_tracker.domain.models import ActiveTimer, CompletedTimer

_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class TrackerGateway(Protocol):
    """Operations available to the TUI across the application boundary."""

    def get_active(self) -> ActiveTimer | None:
        """Return the recovered active timer."""
        ...

    @property
    def configuration_path(self) -> Path:
        """Return the durable configuration path shown in Settings."""
        ...

    def get_configuration(self) -> ReminderSettings:
        """Return settings currently used by the background process."""
        ...

    def save_configuration(self, settings: ReminderSettings) -> ReminderSettings:
        """Persist and live-reload reminder settings."""
        ...

    def get_theme(self) -> str:
        """Return the persisted TUI theme name."""
        ...

    def save_theme(self, theme: str) -> str:
        """Persist the selected TUI theme name."""
        ...

    def get_export_delimiter(self) -> str:
        """Return the persisted export delimiter."""
        ...

    def save_export_delimiter(self, delimiter: str) -> str:
        """Persist the selected export delimiter."""
        ...

    def get_idle_detection_status(self) -> IdleDetectionStatus:
        """Return whether idle-duration detection is available this session."""
        ...

    def get_reminder(self) -> Reminder | None:
        """Return the latest reminder due in the background process."""
        ...

    def confirm_active_reminder(self) -> bool:
        """Confirm the active timer and restart its reminder interval."""
        ...

    def snooze_reminder(self) -> bool:
        """Defer the pending reminder without changing timer state."""
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

    def delete_completed(self, entry_id: int) -> CompletedTimer:
        """Delete one completed entry and return its canonical values."""
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

    def create_project(self, project: str) -> str:
        """Create a new project and return its canonical stored name."""
        ...

    def create_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Create a new activity and return its canonical stored names."""
        ...

    def export_completed(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export completed entries to a confirmed destination."""
        ...

    def export_daily_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export daily project/activity summaries to a confirmed destination."""
        ...

    def export_range_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export selected-range project/activity totals."""
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


@dataclass(frozen=True, slots=True)
class ManageTarget:
    """Exact project or activity selected in a Manage tree."""

    project: str
    activity: str | None = None


class QuickSwitchDeck(OptionList):
    """Recent-work list whose pointer selects and Enter confirms."""

    BINDINGS = [
        binding
        for binding in OptionList.BINDINGS
        if cast(Binding, binding).key != "enter"
    ] + [Binding("enter", "confirm", "Confirm", show=False)]

    class Confirmed(Message):
        """The user confirmed the highlighted quick-switch target."""

        def __init__(self, deck: QuickSwitchDeck) -> None:
            super().__init__()
            self.deck = deck

        @property
        def control(self) -> QuickSwitchDeck:
            """Return the deck that sent the confirmation."""
            return self.deck

    class Navigated(Message):
        """The user moved the highlighted target with an arrow key."""

        def __init__(self, deck: QuickSwitchDeck, option_index: int) -> None:
            super().__init__()
            self.deck = deck
            self.option_index = option_index

        @property
        def control(self) -> QuickSwitchDeck:
            """Return the deck that sent the navigation."""
            return self.deck

    def action_confirm(self) -> None:
        """Confirm the highlighted target when the deck handles Enter."""
        highlighted = self.highlighted
        if highlighted is None:
            return
        if not self.get_option_at_index(highlighted).disabled:
            self.post_message(self.Confirmed(self))

    def action_cursor_up(self) -> None:
        """Move upward and report genuine keyboard navigation."""
        previous = self.highlighted
        super().action_cursor_up()
        self._post_navigation_if_changed(previous)

    def action_cursor_down(self) -> None:
        """Move downward and report genuine keyboard navigation."""
        previous = self.highlighted
        super().action_cursor_down()
        self._post_navigation_if_changed(previous)

    def _post_navigation_if_changed(self, previous: int | None) -> None:
        highlighted = self.highlighted
        if highlighted is not None and highlighted != previous:
            self.post_message(self.Navigated(self, highlighted))


class ShortcutHelpScreen(ModalScreen[None]):
    """Read-only overlay containing every application shortcut."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("ctrl+k", "close", "Close", show=False, priority=True),
        Binding("?", "close", "Close", show=False),
    ]
    CSS = """
    ShortcutHelpScreen {
        align: center middle;
        background: $background 70%;
    }

    #shortcut-help {
        width: 64;
        max-width: 95%;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }

    #shortcut-help-title {
        height: 1;
        margin-bottom: 1;
        text-style: bold;
    }

    #shortcut-help-text {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="shortcut-help"):
            yield Static("Keyboard shortcuts", id="shortcut-help-title")
            yield Static(
                "F1 Track · F2 Review · F3 Manage · F4 Settings\n"
                "1–5 Select quick switch · Enter Confirm quick switch\n"
                "F5 Capture start / switch / restart · F6 Stop · F7 Export\n"
                "F8 Archive project · F9 Archive activity\n"
                "F10 Still active · F11 Update active · F12 Snooze\n"
                "Ctrl+P Commands · Ctrl+C Quit · Ctrl+K or Esc Close this help",
                id="shortcut-help-text",
            )

    def action_close(self) -> None:
        self.dismiss(None)


class TimeTrackerApp(App[None]):
    """Keyboard-first focused workflows backed by the local agent."""

    TITLE = "Time Tracker"
    SUB_TITLE = "Local, persistent time tracking"
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (70, "-wide")]
    VERTICAL_BREAKPOINTS = [(0, "-short"), (30, "-tall")]
    BINDINGS = [
        Binding("f1", "show_track", "Track", show=False),
        Binding("f2", "show_review", "Review", show=False),
        Binding("f3", "show_manage", "Manage", show=False),
        Binding("f4", "show_settings", "Settings", show=False),
        Binding("f5", "start_timer", "Timer action", show=False),
        Binding("f6", "stop_timer", "Stop", show=False),
        Binding("f7", "export_csv", "Export CSV", show=False),
        Binding("f8", "archive_project", "Archive project", show=False),
        Binding("f9", "archive_activity", "Archive activity", show=False),
        Binding("f10", "confirm_active_reminder", "Still active", show=False),
        Binding("f11", "edit_active", "Update active", show=False),
        Binding("f12", "snooze_reminder", "Snooze", show=False),
        Binding("1", "select_recent_1", "Select quick switch 1", show=False),
        Binding("2", "select_recent_2", "Select quick switch 2", show=False),
        Binding("3", "select_recent_3", "Select quick switch 3", show=False),
        Binding("4", "select_recent_4", "Select quick switch 4", show=False),
        Binding("5", "select_recent_5", "Select quick switch 5", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding(
            "ctrl+q",
            "ignore_terminal_control",
            show=False,
            priority=True,
        ),
        Binding(
            "ctrl+k",
            "show_shortcuts",
            "Shortcuts",
            show=False,
            priority=True,
        ),
        Binding("?", "show_shortcuts", "Shortcuts", show=False),
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
        "manage-tab": "#active-targets",
        "settings-tab": "#inactive-reminders-enabled",
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

    #track-view {
        overflow-x: hidden;
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

    #snooze-reminder-button {
        display: none;
        width: 16;
        margin-left: 1;
    }

    /* Textual only dims the label of a disabled variant button and keeps its
     * saturated background, which leaves inactive Start, Stop, and Save labels
     * hard to read. Render disabled buttons as flat, fully opaque surface
     * controls instead. These declarations need !important because Textual's
     * own variant rules are more specific than any selector available here. */
    Button:disabled {
        color: $text-muted !important;
        text-opacity: 1 !important;
        background: $surface !important;
        border-top: tall $surface !important;
        border-bottom: tall $surface !important;
    }

    Input {
        margin-bottom: 0;
    }

    #track-target {
        height: 3;
    }

    #project, #activity {
        width: 1fr;
    }

    #project {
        margin-right: 1;
    }

    Screen.-narrow #track-target {
        layout: vertical;
        height: 6;
    }

    Screen.-narrow #project {
        margin-right: 0;
    }

    #active-targets, #archived-targets {
        height: 16;
        min-height: 4;
        margin-bottom: 0;
    }

    Screen.-short #active-targets, Screen.-short #archived-targets {
        height: 8;
    }

    #active-targets-empty, #archived-targets-empty {
        height: 1;
        color: $text-muted;
    }

    #archive-selected-button, #restore-selected-button,
    #create-project-button, #create-activity-button {
        width: 30;
        margin-bottom: 1;
    }

    .manage-title {
        height: 1;
        text-style: bold;
    }

    #actions, #current-timer-actions {
        height: auto;
        margin-top: 0;
    }

    #actions Button, #current-timer-actions Button {
        width: 1fr;
        margin-right: 1;
    }

    #recent-activities {
        height: auto;
        min-height: 1;
        max-height: 5;
        overflow-x: hidden;
    }

    #recent-empty {
        height: 1;
        color: $text-muted;
    }

    #quick-switch-title, #capture-title {
        height: 1;
        text-style: bold;
    }

    #quick-switch-note {
        margin-bottom: 0;
    }

    #quick-switch-action {
        height: auto;
        min-height: 3;
        padding: 0 1;
        content-align: left middle;
    }

    #capture-title {
        margin-top: 1;
    }

    #today-total {
        width: 34;
        color: $text-muted;
    }

    #recent-activities, #recent-empty {
        width: 1fr;
    }

    #export-actions {
        height: auto;
        margin-top: 0;
    }

    #export-path {
        width: 1fr;
    }

    #review-filters, #custom-filter-dates {
        height: auto;
    }

    #date-preset {
        width: 22;
        margin-right: 1;
    }

    #filter-project, #filter-activity,
    #filter-start-date, #filter-end-date {
        width: 1fr;
    }

    #filter-project, #filter-start-date {
        margin-right: 1;
    }

    #custom-filter-dates {
        display: none;
    }

    #active-filter, #history-empty {
        height: 1;
        color: $text-muted;
    }

    #summary-mode-label, #range-summary-mode-label {
        width: auto;
        height: 1;
        padding-right: 1;
    }

    #summary-mode, #summary-mode:focus,
    #range-summary-mode, #range-summary-mode:focus {
        width: auto;
        height: 1;
        padding: 0;
        border: none;
    }

    #summary-mode {
        margin-right: 4;
    }

    #history-options, #representation-options {
        height: 3;
        align-horizontal: left;
    }

    #load-correction-button, #add-manual-entry-button,
    #delete-completed-button {
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

    #message.message-success {
        color: $text-success;
    }

    #message.message-error {
        color: $text-error;
    }

    #shortcut-summary {
        width: 100%;
        height: 1;
        padding: 0 1;
        color: $footer-foreground;
        background: $footer-background;
        text-overflow: ellipsis;
    }

    #manage-help, #settings-info, #settings-path {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }

    .settings-row {
        height: 4;
        align-vertical: middle;
    }

    .settings-row Static {
        width: 32;
        height: 1;
    }

    .settings-row Switch {
        width: 10;
        height: 1;
        padding: 0;
        border: none;
    }

    .settings-row Input {
        width: 24;
        height: 3;
    }

    .settings-row Select {
        width: 24;
    }

    #save-settings-button {
        width: 28;
        margin-top: 1;
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
        self._history_row_entry_ids: list[int | None] = []
        self._review_filter = ReviewFilter()
        self._review_filter_valid = True
        self._today_total_day: date | None = None
        self._recent_activities: list[RecentActivity] = []
        self._selected_recent_pair: RecentActivity | None = None
        self._start_action: StartAction | None = None
        self._editing_entry_id: int | None = None
        self._editing_started_at: datetime | None = None
        self._editing_stopped_at: datetime | None = None
        self._creating_manual_entry = False
        self._pending_delete_entry_id: int | None = None
        self._pending_archive_project: tuple[str, str] | None = None
        self._pending_archive_activity: tuple[str, str, str, str] | None = None
        self._idle_detection_available = False
        self._theme_persistence_ready = False
        self._saved_theme: str | None = None
        self._theme_save_lock = asyncio.Lock()

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
                yield Button("Snooze  F12", id="snooze-reminder-button")
            yield Tabs(
                Tab("Track  F1", id="track-tab"),
                Tab("Review  F2", id="review-tab"),
                Tab("Manage  F3", id="manage-tab"),
                Tab("Settings  F4", id="settings-tab"),
                active="track-tab",
                id="view-tabs",
            )
            with ContentSwitcher(initial="track-view", id="view-switcher"):
                with VerticalScroll(id="track-view", classes="view"):
                    yield Static("Quick switch", id="quick-switch-title")
                    yield QuickSwitchDeck(id="recent-activities", compact=True)
                    yield Static(
                        "No recent work yet. Use Manual entry below.",
                        id="recent-empty",
                    )
                    yield Input(
                        placeholder="Optional note for this quick switch",
                        id="quick-switch-note",
                    )
                    yield Static("Choose recent work", id="quick-switch-action")
                    yield Static("Manual entry", id="capture-title")
                    with Horizontal(id="track-target"):
                        yield Input(
                            placeholder="Project (type to reuse existing)",
                            id="project",
                        )
                        yield Input(
                            placeholder="Activity (type to reuse existing)",
                            id="activity",
                        )
                    yield Input(
                        placeholder="Optional note for this manual entry",
                        id="note",
                    )
                    with Horizontal(id="actions"):
                        yield Button(
                            "Start timer  F5",
                            id="start-button",
                            variant="success",
                        )
                    with Horizontal(id="current-timer-actions"):
                        yield Button(
                            "Stop current timer  F6",
                            id="stop-button",
                            variant="warning",
                        )
                        yield Button(
                            "Update current timer  F11",
                            id="edit-active-button",
                            disabled=True,
                        )
                    yield Static(
                        "Today's completed time: 00:00:00",
                        id="today-total",
                    )
                with VerticalScroll(id="review-view", classes="view"):
                    with Horizontal(id="export-actions"):
                        yield Input(
                            placeholder="CSV export path (for example ~/times.csv)",
                            id="export-path",
                        )
                        yield Button("Export CSV  F7", id="export-button")
                    with Horizontal(id="review-filters"):
                        yield Select(
                            [
                                ("All time", DatePreset.ALL_TIME.value),
                                ("Today", DatePreset.TODAY.value),
                                ("This week", DatePreset.THIS_WEEK.value),
                                ("This month", DatePreset.THIS_MONTH.value),
                                ("Custom", DatePreset.CUSTOM.value),
                            ],
                            value=DatePreset.ALL_TIME.value,
                            allow_blank=False,
                            id="date-preset",
                        )
                        yield Select(
                            [("Any project", "")],
                            value="",
                            allow_blank=False,
                            id="filter-project",
                        )
                        yield Select(
                            [("Any activity", "")],
                            value="",
                            allow_blank=False,
                            id="filter-activity",
                        )
                    with Horizontal(id="custom-filter-dates"):
                        yield Input(
                            placeholder="Start date (YYYY-MM-DD)",
                            id="filter-start-date",
                        )
                        yield Input(
                            placeholder="End date (YYYY-MM-DD)",
                            id="filter-end-date",
                        )
                    yield Static(
                        "All time · all projects · all activities",
                        id="active-filter",
                    )
                    with Horizontal(id="representation-options"):
                        yield Static("Daily summaries", id="summary-mode-label")
                        yield Switch(id="summary-mode")
                        yield Static(
                            "Range totals",
                            id="range-summary-mode-label",
                        )
                        yield Switch(id="range-summary-mode")
                    yield Static("Completed entries", id="history-title")
                    yield Static("No completed time matches.", id="history-empty")
                    yield DataTable(
                        id="history",
                        cursor_type="row",
                        zebra_stripes=True,
                    )
                    with Horizontal(id="history-options"):
                        yield Button(
                            "Load selected entry",
                            id="load-correction-button",
                        )
                        yield Button(
                            "Add missed entry",
                            id="add-manual-entry-button",
                        )
                        yield Button(
                            "Delete selected entry",
                            id="delete-completed-button",
                            variant="error",
                        )
                    yield Static("Correct selected entry", id="correction-title")
                    with Horizontal(id="correction-target"):
                        yield Input(
                            placeholder="Project",
                            id="correction-project",
                            classes="correction-input",
                        )
                        yield Input(
                            placeholder="Activity",
                            id="correction-activity",
                            classes="correction-input",
                        )
                    yield Input(
                        placeholder="Optional note",
                        id="correction-note",
                        classes="correction-input",
                    )
                    with Horizontal(id="correction-times"):
                        yield Input(
                            placeholder="Start (ISO 8601 with UTC offset)",
                            id="correction-start",
                            classes="correction-input",
                        )
                        yield Input(
                            placeholder="Stop (ISO 8601 with UTC offset)",
                            id="correction-stop",
                            classes="correction-input",
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
                        "Select an active project or activity to archive, or select "
                        "an archived item to restore.",
                        id="manage-help",
                    )
                    yield Static(
                        "Active projects and activities",
                        classes="manage-title",
                    )
                    yield Tree("Active", id="active-targets")
                    yield Static(
                        "No active projects or activities.",
                        id="active-targets-empty",
                    )
                    yield Button(
                        "Archive selected",
                        id="archive-selected-button",
                        disabled=True,
                    )
                    yield Static(
                        "Archived projects and activities",
                        classes="manage-title",
                    )
                    yield Tree("Archived", id="archived-targets")
                    yield Static(
                        "No archived projects or activities.",
                        id="archived-targets-empty",
                    )
                    yield Button(
                        "Restore selected",
                        id="restore-selected-button",
                        disabled=True,
                    )
                    yield Static(
                        "Prepare a new project",
                        classes="manage-title",
                    )
                    yield Input(
                        placeholder="New project name",
                        id="new-project",
                    )
                    yield Button(
                        "Add project",
                        id="create-project-button",
                    )
                    yield Static(
                        "Prepare a new activity",
                        classes="manage-title",
                    )
                    yield Input(
                        placeholder="Existing project",
                        id="new-activity-project",
                    )
                    yield Input(
                        placeholder="New activity name",
                        id="new-activity-name",
                    )
                    yield Button(
                        "Add activity",
                        id="create-activity-button",
                    )
                with VerticalScroll(id="settings-view", classes="view"):
                    yield Static(
                        "Configure reminders and export formatting below. Saving "
                        "updates the TOML file and applies changes immediately. The "
                        "color palette applies and is saved as soon as it is "
                        "selected.",
                        id="settings-info",
                    )
                    with Horizontal(classes="settings-row"):
                        yield Static("Inactive-timer reminders")
                        yield Switch(id="inactive-reminders-enabled")
                        yield Input(
                            placeholder="Interval minutes",
                            id="inactive-reminder-minutes",
                        )
                    with Horizontal(classes="settings-row"):
                        yield Static("Active-timer reminders")
                        yield Switch(id="active-reminders-enabled")
                        yield Input(
                            placeholder="Interval minutes",
                            id="active-reminder-minutes",
                        )
                    with Horizontal(classes="settings-row"):
                        yield Static("Weekly reminder window")
                        yield Switch(id="reminder-window-enabled")
                        yield Input(
                            placeholder="Weekdays (Mon,Tue,Wed,Thu,Fri)",
                            id="reminder-window-weekdays",
                        )
                    with Horizontal(classes="settings-row"):
                        yield Static("Window start / end")
                        yield Input(placeholder="09:00", id="reminder-window-start")
                        yield Input(placeholder="17:00", id="reminder-window-end")
                    with Horizontal(classes="settings-row"):
                        yield Static("Snooze minutes")
                        yield Input(placeholder="10", id="reminder-snooze-minutes")
                    with Horizontal(classes="settings-row"):
                        yield Static("Idle-triggered reminders")
                        yield Switch(id="idle-reminders-enabled")
                        yield Input(
                            placeholder="Idle threshold minutes",
                            id="idle-reminder-minutes",
                        )
                    with Horizontal(classes="settings-row"):
                        yield Static("Export delimiter")
                        yield Select(
                            [
                                ("Comma (CSV)", ","),
                                ("Pipe", "|"),
                            ],
                            value=",",
                            allow_blank=False,
                            id="export-delimiter",
                        )
                    with Horizontal(classes="settings-row"):
                        yield Static("Color palette")
                        yield Select(
                            [(name, name) for name in sorted(self.available_themes)],
                            value=self.theme,
                            allow_blank=False,
                            id="color-palette",
                        )
                    yield Static("Idle detection: checking…", id="idle-status")
                    yield Button(
                        "Save settings",
                        id="save-settings-button",
                        variant="primary",
                    )
                    yield Static("", id="settings-path")
            yield Static("", id="message")
        yield Static(
            "Ctrl+K Shortcuts · F5 Timer · F6 Stop · F11 Update",
            id="shortcut-summary",
        )

    async def on_mount(self) -> None:
        """Recover any persisted active timer when the TUI reconnects."""
        self.theme_changed_signal.subscribe(self, self._handle_theme_changed)
        self.set_interval(1.0, self._render_active)
        self.set_interval(1.0, self._refresh_reminder)
        self.set_interval(5.0, self._refresh_idle_status)
        try:
            self.active_timer = await asyncio.to_thread(self.client.get_active)
            projects = await asyncio.to_thread(self.client.list_projects)
            active_hierarchy = [
                (
                    project,
                    await asyncio.to_thread(self.client.list_activities, project),
                )
                for project in projects
            ]
            completed = await asyncio.to_thread(self.client.list_completed)
            recent = await asyncio.to_thread(self.client.list_recent_activities)
            archived_projects = await asyncio.to_thread(
                self.client.list_archived_projects
            )
            archived_activities = await asyncio.to_thread(
                self.client.list_archived_activities
            )
            settings = await asyncio.to_thread(self.client.get_configuration)
            persisted_theme = await asyncio.to_thread(self.client.get_theme)
            export_delimiter = await asyncio.to_thread(self.client.get_export_delimiter)
            idle_status = await asyncio.to_thread(self.client.get_idle_detection_status)
        except Exception as error:
            self._show_message(str(error), error=True)
        else:
            selected_theme = (
                persisted_theme
                if persisted_theme in self.available_themes
                else "textual-dark"
            )
            self._saved_theme = selected_theme
            self.theme = selected_theme
            self._theme_persistence_ready = True
            self._render_theme_selection()
            self._set_project_suggestions(projects)
            self._render_history(completed)
            self._render_recent_activities(recent)
            self._render_manage_items(
                active_hierarchy,
                archived_projects,
                archived_activities,
            )
            self._idle_detection_available = idle_status.available
            self._render_settings(settings, export_delimiter)
            if self.active_timer is not None:
                self.query_one("#project", Input).value = self.active_timer.project
                self.query_one("#activity", Input).value = self.active_timer.activity
                self.query_one("#note", Input).value = self.active_timer.note or ""
            if selected_theme != persisted_theme:
                try:
                    await asyncio.to_thread(self.client.save_theme, selected_theme)
                except Exception as error:
                    self._show_message(str(error), error=True)
        self._render_active()
        await self._refresh_start_action()
        await self._refresh_reminder()
        self._select_view("track-tab")

    async def _handle_theme_changed(self, _theme: Theme) -> None:
        """Persist a theme selected in Settings or through the command palette."""
        self._render_theme_selection()
        await self._persist_theme(self.theme)

    async def _persist_theme(self, selected_theme: str) -> None:
        """Save one applied palette, serializing concurrent theme events."""
        if not self._theme_persistence_ready:
            return
        async with self._theme_save_lock:
            if selected_theme == self._saved_theme:
                return
            try:
                saved = await asyncio.to_thread(
                    self.client.save_theme,
                    selected_theme,
                )
            except Exception as error:
                self._show_message(str(error), error=True)
                return
            self._saved_theme = saved

    @on(Select.Changed, "#color-palette")
    async def handle_color_palette_selected(self, event: Select.Changed) -> None:
        """Apply and durably save the palette selected in Settings."""
        if not isinstance(event.value, str):
            return
        if event.value != self.theme:
            self.theme = event.value
        await self._persist_theme(event.value)

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

    @on(Input.Changed, "#quick-switch-note")
    def handle_quick_switch_note_changed(self) -> None:
        """Keep the pending deck action accurate while its note is edited."""
        self._render_quick_switch_action()

    @on(Input.Submitted, "#quick-switch-note")
    async def handle_quick_switch_note_submitted(self) -> None:
        """Confirm the pending quick switch after its single-line note."""
        await self._confirm_quick_switch()

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

    @on(OptionList.OptionHighlighted, "#recent-activities")
    def handle_recent_activity_highlighted(
        self,
        event: OptionList.OptionHighlighted,
    ) -> None:
        """Select one application-projected pair without changing timer state."""
        if not 0 <= event.option_index < len(self._recent_activities):
            return
        pair = self._recent_activities[event.option_index]
        if pair != self._selected_recent_pair:
            self.query_one("#quick-switch-note", Input).value = ""
        self._selected_recent_pair = pair
        self._render_quick_switch_action()

    @on(QuickSwitchDeck.Navigated, "#recent-activities")
    def handle_recent_activity_navigated(
        self,
        event: QuickSwitchDeck.Navigated,
    ) -> None:
        """Mirror an arrow-key deck selection into Manual entry."""
        self._apply_recent_selection(event.option_index)

    @on(OptionList.OptionSelected, "#recent-activities")
    def handle_recent_activity_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        """Mirror a pointer-selected quick-switch target into Manual entry."""
        self._apply_recent_selection(event.option_index)

    @on(QuickSwitchDeck.Confirmed, "#recent-activities")
    async def handle_quick_switch_confirmed(self) -> None:
        """Confirm the highlighted deck action from Enter."""
        await self._confirm_quick_switch()

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

    @on(Button.Pressed, "#delete-completed-button")
    async def handle_delete_completed_button(self) -> None:
        """Confirm or delete the selected completed entry."""
        await self._delete_selected_completed()

    @on(Button.Pressed, "#save-correction-button")
    async def handle_save_correction_button(self) -> None:
        """Persist the correction currently shown in Review."""
        await self._save_correction()

    @on(Button.Pressed, "#archive-selected-button")
    async def handle_archive_selected_button(self) -> None:
        """Archive the active project or activity selected in Manage."""
        target = self._selected_manage_target("#active-targets")
        if target is None:
            self._show_message("Select a project or activity to archive.", error=True)
        elif target.activity is None:
            await self._archive_project()
        else:
            await self._archive_activity()

    @on(Button.Pressed, "#restore-selected-button")
    async def handle_restore_selected_button(self) -> None:
        """Restore the archived project or activity selected in Manage."""
        target = self._selected_manage_target("#archived-targets")
        if target is None:
            self._show_message("Select an archived item to restore.", error=True)
        elif target.activity is None:
            await self._restore_project()
        else:
            await self._restore_activity()

    @on(Button.Pressed, "#create-project-button")
    async def handle_create_project_button(self) -> None:
        """Create a new project prepared ahead of any timer or entry."""
        await self._create_project()

    @on(Button.Pressed, "#create-activity-button")
    async def handle_create_activity_button(self) -> None:
        """Create a new activity prepared ahead of any timer or entry."""
        await self._create_activity()

    @on(Button.Pressed, "#confirm-active-reminder-button")
    async def handle_confirm_active_reminder_button(self) -> None:
        """Confirm an active reminder from its visible prompt."""
        await self._confirm_active_reminder()

    @on(Button.Pressed, "#snooze-reminder-button")
    async def handle_snooze_reminder_button(self) -> None:
        """Snooze a visible reminder."""
        await self._snooze_reminder()

    @on(Button.Pressed, "#save-settings-button")
    async def handle_save_settings_button(self) -> None:
        """Persist and immediately apply reminder settings."""
        await self._save_settings()

    @on(Input.Changed, "#export-path")
    def handle_export_path_changed(self) -> None:
        """Cancel overwrite confirmation when the destination is edited."""
        if self._pending_export_path is not None:
            self._clear_export_confirmation()

    @on(Select.Changed, "#date-preset")
    def handle_date_preset_changed(self) -> None:
        """Apply one local calendar-date preset to all Review data."""
        value = self.query_one("#date-preset", Select).value
        custom = value == DatePreset.CUSTOM.value
        self.query_one("#custom-filter-dates", Horizontal).display = custom
        self._apply_review_filter()

    @on(Select.Changed, "#filter-project")
    def handle_filter_project_changed(self) -> None:
        """Update historical activity choices and apply the target filter."""
        if not self.query("#filter-activity") or not self.query("#history"):
            return
        self._set_review_activity_options()
        self._apply_review_filter()

    @on(Select.Changed, "#filter-activity")
    def handle_filter_activity_changed(self) -> None:
        """Apply the historical activity filter."""
        if not self.query("#history"):
            return
        self._apply_review_filter()

    @on(Input.Changed, "#filter-start-date")
    @on(Input.Changed, "#filter-end-date")
    def handle_custom_filter_date_changed(self) -> None:
        """Validate and apply custom inclusive local dates."""
        value = self.query_one("#date-preset", Select).value
        if value == DatePreset.CUSTOM.value:
            self._apply_review_filter()

    @on(Switch.Changed, "#summary-mode")
    def handle_summary_mode_changed(self, event: Switch.Changed) -> None:
        """Render and export the representation selected by the user."""
        if event.value:
            self.query_one("#range-summary-mode", Switch).value = False
        self._clear_export_confirmation()
        self._render_history(self._completed_entries)

    @on(Switch.Changed, "#range-summary-mode")
    def handle_range_summary_mode_changed(self, event: Switch.Changed) -> None:
        """Select aggregate project/activity totals for the current range."""
        if event.value:
            self.query_one("#summary-mode", Switch).value = False
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

    def action_show_shortcuts(self) -> None:
        """Toggle every binding without changing workflow state."""
        if isinstance(self.screen, ShortcutHelpScreen):
            self.screen.dismiss(None)
        else:
            self.push_screen(ShortcutHelpScreen())

    def action_ignore_terminal_control(self) -> None:
        """Override Textual's terminal flow-control quit binding."""

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

    async def action_snooze_reminder(self) -> None:
        """Snooze a pending reminder from the F12 binding."""
        await self._snooze_reminder()

    async def action_edit_active(self) -> None:
        """Update active details from the F11 binding."""
        await self._edit_active()

    def action_select_recent_1(self) -> None:
        """Select the first quick-switch target."""
        self._select_recent_shortcut(0)

    def action_select_recent_2(self) -> None:
        """Select the second quick-switch target."""
        self._select_recent_shortcut(1)

    def action_select_recent_3(self) -> None:
        """Select the third quick-switch target."""
        self._select_recent_shortcut(2)

    def action_select_recent_4(self) -> None:
        """Select the fourth quick-switch target."""
        self._select_recent_shortcut(3)

    def action_select_recent_5(self) -> None:
        """Select the fifth quick-switch target."""
        self._select_recent_shortcut(4)

    def _select_recent_shortcut(self, index: int) -> None:
        """Select a numbered deck item and mirror its target into Manual entry."""
        if isinstance(self.focused, Input):
            return
        deck = self.query_one("#recent-activities", QuickSwitchDeck)
        if not 0 <= index < len(self._recent_activities):
            return
        deck.highlighted = index
        self._apply_recent_selection(index)
        deck.focus()

    def _apply_recent_selection(self, index: int) -> None:
        """Apply the shared pointer and number-key selection consequences."""
        if not 0 <= index < len(self._recent_activities):
            return
        pair = self._recent_activities[index]
        self.query_one("#project", Input).value = pair.project
        self.query_one("#activity", Input).value = pair.activity
        self.query_one("#note", Input).value = ""

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
        await self._refresh_recent_activities(
            preferred_pair=RecentActivity(
                self.active_timer.project,
                self.active_timer.activity,
            )
        )
        self._render_active()
        await self._refresh_start_action()

    async def _confirm_quick_switch(self) -> None:
        """Persist the selected deck Start or Switch through the agent."""
        pair = self._selected_recent_activity()
        if pair is None:
            self._show_message("Select recent work before confirming.", error=True)
            return
        if classify_quick_switch(self.active_timer, pair) is QuickSwitchAction.CURRENT:
            self._show_message(
                f"{pair.project} / {pair.activity} is current; timer unchanged."
            )
            return
        previous = self.active_timer
        try:
            persisted = await asyncio.to_thread(
                self.client.start,
                pair.project,
                pair.activity,
                self.query_one("#quick-switch-note", Input).value,
            )
        except Exception as error:
            await self._refresh_recent_activities()
            self._show_message(str(error), error=True)
            return
        self.active_timer = persisted
        self.pending_reminder = None
        self._render_reminder()
        if persisted.note:
            self.query_one("#note", Input).value = persisted.note
        self.query_one("#quick-switch-note", Input).value = ""
        await self._refresh_project_suggestions()
        await self._refresh_history()
        await self._refresh_recent_activities(
            preferred_pair=RecentActivity(persisted.project, persisted.activity)
        )
        self._render_active()
        await self._refresh_start_action()
        if previous is None:
            message = f"Started {persisted.project} / {persisted.activity}."
        else:
            message = f"Switched to {persisted.project} / {persisted.activity}."
        self._show_message(message)

    async def _save_settings(self) -> None:
        try:
            settings = ReminderSettings(
                inactive_enabled=self.query_one(
                    "#inactive-reminders-enabled", Switch
                ).value,
                inactive_interval_minutes=_parse_positive_minutes(
                    self.query_one("#inactive-reminder-minutes", Input).value,
                    "Inactive reminder interval",
                ),
                active_enabled=self.query_one(
                    "#active-reminders-enabled", Switch
                ).value,
                active_interval_minutes=_parse_positive_minutes(
                    self.query_one("#active-reminder-minutes", Input).value,
                    "Active reminder interval",
                ),
                window_enabled=self.query_one("#reminder-window-enabled", Switch).value,
                window_weekdays=_parse_weekdays(
                    self.query_one("#reminder-window-weekdays", Input).value
                ),
                window_start=self.query_one(
                    "#reminder-window-start", Input
                ).value.strip(),
                window_end=self.query_one("#reminder-window-end", Input).value.strip(),
                snooze_minutes=_parse_positive_minutes(
                    self.query_one("#reminder-snooze-minutes", Input).value,
                    "Snooze duration",
                ),
                idle_enabled=self.query_one("#idle-reminders-enabled", Switch).value,
                idle_threshold_minutes=_parse_positive_minutes(
                    self.query_one("#idle-reminder-minutes", Input).value,
                    "Idle reminder threshold",
                ),
            )
            delimiter_value = self.query_one("#export-delimiter", Select).value
            if not isinstance(delimiter_value, str):
                raise ValueError("Select an export delimiter.")
            saved = await asyncio.to_thread(self.client.save_configuration, settings)
            saved_delimiter = await asyncio.to_thread(
                self.client.save_export_delimiter,
                delimiter_value,
            )
            idle_status = await asyncio.to_thread(self.client.get_idle_detection_status)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._idle_detection_available = idle_status.available
        self._render_settings(saved, saved_delimiter)
        self.pending_reminder = None
        self._render_reminder()
        self._show_message("Settings saved and applied.")

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
        await self._refresh_recent_activities(
            preferred_pair=RecentActivity(active.project, active.activity)
        )
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
            ("#correction-project", "#correction-activity"),
        ):
            await self._refresh_activity_suggestions(
                self.query_one(project_selector, Input).value.strip(),
                input_selector=activity_selector,
            )

    async def _archive_project(self) -> None:
        self._clear_activity_archive_confirmation()
        selected = self._selected_manage_target("#active-targets")
        if selected is None or selected.activity is not None:
            self._clear_project_archive_confirmation()
            self._show_message("Select a project to archive.", error=True)
            return
        project = selected.project
        try:
            target = await asyncio.to_thread(
                self.client.get_archive_project_target,
                project,
            )
        except Exception as error:
            self._clear_project_archive_confirmation()
            self._show_message(str(error), error=True)
            return
        pending = (project, target)
        if self._pending_archive_project != pending:
            self._pending_archive_project = pending
            self.query_one(
                "#archive-selected-button", Button
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
        await self._refresh_project_suggestions()
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_manage_items()
        self._show_message(f"Archived project {archived_project}.")

    async def _archive_activity(self) -> None:
        self._clear_project_archive_confirmation()
        selected = self._selected_manage_target("#active-targets")
        if selected is None or selected.activity is None:
            self._clear_activity_archive_confirmation()
            self._show_message("Select an activity to archive.", error=True)
            return
        project = selected.project
        activity = selected.activity
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
        pending = (project, activity, target[0], target[1])
        if self._pending_archive_activity != pending:
            self._pending_archive_activity = pending
            self.query_one(
                "#archive-selected-button", Button
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
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_manage_items()
        self._show_message(
            f"Archived activity {archived_project} / {archived_activity}."
        )

    async def _restore_project(self) -> None:
        selected = self._selected_manage_target("#archived-targets")
        if selected is None or selected.activity is not None:
            self._show_message("Select an archived project to restore.", error=True)
            return
        project = selected.project
        try:
            restored_project = await asyncio.to_thread(
                self.client.unarchive_project,
                project,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        await self._refresh_project_suggestions()
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_manage_items()
        self._show_message(f"Restored project {restored_project}.")

    async def _restore_activity(self) -> None:
        selected = self._selected_manage_target("#archived-targets")
        if selected is None or selected.activity is None:
            self._show_message("Select an archived activity to restore.", error=True)
            return
        try:
            restored_project, restored_activity = await asyncio.to_thread(
                self.client.unarchive_activity,
                selected.project,
                selected.activity,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        await self._refresh_project_suggestions()
        await self._refresh_all_activity_suggestions()
        await self._refresh_recent_activities()
        await self._refresh_manage_items()
        self._show_message(
            f"Restored activity {restored_project} / {restored_activity}."
        )

    async def _create_project(self) -> None:
        project_input = self.query_one("#new-project", Input)
        try:
            created_project = await asyncio.to_thread(
                self.client.create_project,
                project_input.value,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        project_input.value = ""
        await self._refresh_project_suggestions()
        await self._refresh_manage_items()
        self._show_message(f"Created project {created_project}.")

    async def _create_activity(self) -> None:
        project_input = self.query_one("#new-activity-project", Input)
        activity_input = self.query_one("#new-activity-name", Input)
        try:
            created_project, created_activity = await asyncio.to_thread(
                self.client.create_activity,
                project_input.value,
                activity_input.value,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        activity_input.value = ""
        await self._refresh_all_activity_suggestions()
        await self._refresh_manage_items()
        self._show_message(f"Created activity {created_project} / {created_activity}.")

    def _clear_project_archive_confirmation(self) -> None:
        self._pending_archive_project = None
        buttons = self.query("#archive-selected-button")
        if buttons:
            buttons.first(Button).label = "Archive selected"

    def _clear_activity_archive_confirmation(self) -> None:
        self._pending_archive_activity = None
        buttons = self.query("#archive-selected-button")
        if buttons:
            buttons.first(Button).label = "Archive selected"

    def _selected_manage_target(self, selector: str) -> ManageTarget | None:
        tree = self.query_one(selector, Tree)
        node = tree.cursor_node
        if node is None:
            return None
        return node.data if isinstance(node.data, ManageTarget) else None

    def _select_view(self, tab_id: str) -> None:
        """Select one view without changing any workflow state."""
        content_id = self._VIEW_CONTENT[tab_id]
        tabs = self.query_one("#view-tabs", Tabs)
        switcher = self.query_one("#view-switcher", ContentSwitcher)
        view_changed = tabs.active != tab_id or switcher.current != content_id
        tabs.active = tab_id
        switcher.current = content_id
        focus_selector = self._VIEW_FOCUS.get(tab_id)
        if tab_id == "track-tab" and self._recent_activities:
            focus_selector = "#recent-activities"
        if focus_selector is None:
            tabs.focus()
        else:
            self.query_one(focus_selector).focus()
        if tab_id == "manage-tab" and view_changed:
            self.run_worker(
                self._refresh_manage_items(),
                group="manage-refresh",
                exclusive=True,
            )
        self._render_shortcut_summary()

    def _render_shortcut_summary(self) -> None:
        summaries = {
            "track-tab": "1–5 Deck · Enter Confirm · F5 Capture · F6 Stop · F11 Update",
            "review-tab": "F7 Export",
            "manage-tab": "F8 Archive project · F9 Archive activity",
            "settings-tab": "Settings",
        }
        active_tab = self.query_one("#view-tabs", Tabs).active or "track-tab"
        parts = ["Ctrl+K Shortcuts", summaries.get(active_tab, "")]
        reminder = self.pending_reminder
        if reminder is not None:
            if reminder.kind is ReminderKind.ACTIVE:
                parts.append("F10 Still active")
            parts.append("F12 Snooze")
        self.query_one("#shortcut-summary", Static).update(
            " · ".join(part for part in parts if part)
        )

    def _set_project_suggestions(self, projects: list[str]) -> None:
        """Apply canonical project suggestions to Track and Manage inputs."""
        for selector in ("#project", "#correction-project", "#new-activity-project"):
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
            await self._refresh_recent_activities(
                preferred_pair=RecentActivity(completed.project, completed.activity)
            )
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

    async def _refresh_idle_status(self) -> None:
        try:
            status = await asyncio.to_thread(self.client.get_idle_detection_status)
        except Exception:
            return
        if status.available == self._idle_detection_available:
            return
        self._idle_detection_available = status.available
        self._render_idle_status()

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

    async def _snooze_reminder(self) -> None:
        try:
            snoozed = await asyncio.to_thread(self.client.snooze_reminder)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        if not snoozed:
            await self._refresh_reminder()
            self._show_message("No reminder to snooze.", error=True)
            return
        self.pending_reminder = None
        self._render_reminder()
        self._show_message("Reminder snoozed.")

    async def _refresh_history(self, *, preferred_entry_id: int | None = None) -> None:
        try:
            completed = await asyncio.to_thread(self.client.list_completed)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_history(completed, preferred_entry_id=preferred_entry_id)

    async def _load_selected_correction(self) -> None:
        if self._review_summary_mode():
            self._show_message(
                "Switch to completed entries before correcting an entry.",
                error=True,
            )
            return
        table = self.query_one("#history", DataTable)
        if table.cursor_row >= len(self._history_row_entry_ids):
            self._show_message("Select a completed entry row to correct.", error=True)
            return
        entry_id = self._history_row_entry_ids[table.cursor_row]
        if entry_id is None:
            self._show_message("Select a completed entry row to correct.", error=True)
            return
        entry = next(
            (item for item in self._completed_entries if item.entry_id == entry_id),
            None,
        )
        if entry is None:
            self._show_message(
                "The selected completed entry is unavailable.", error=True
            )
            return
        self._populate_correction(entry)
        self.query_one("#correction-project", Input).focus()

    async def _delete_selected_completed(self) -> None:
        if self._review_summary_mode():
            self._clear_delete_confirmation()
            self._show_message(
                "Switch to completed entries before deleting an entry.",
                error=True,
            )
            return
        table = self.query_one("#history", DataTable)
        if table.cursor_row >= len(self._history_row_entry_ids):
            self._clear_delete_confirmation()
            self._show_message("Select a completed entry row to delete.", error=True)
            return
        entry_id = self._history_row_entry_ids[table.cursor_row]
        if entry_id is None:
            self._clear_delete_confirmation()
            self._show_message("Select a completed entry row to delete.", error=True)
            return
        entry = next(
            (item for item in self._completed_entries if item.entry_id == entry_id),
            None,
        )
        if entry is None:
            self._clear_delete_confirmation()
            self._show_message(
                "The selected completed entry is unavailable.", error=True
            )
            return
        if self._pending_delete_entry_id != entry_id:
            self._pending_delete_entry_id = entry_id
            self.query_one(
                "#delete-completed-button", Button
            ).label = "Confirm delete selected"
            local_start = entry.started_at.astimezone().isoformat(timespec="minutes")
            self._show_message(
                "Press Delete selected entry again to permanently delete "
                f"{entry.project} / {entry.activity} from {local_start}."
            )
            return
        try:
            deleted = await asyncio.to_thread(
                self.client.delete_completed,
                entry_id,
            )
        except Exception as error:
            self._clear_delete_confirmation()
            self._show_message(str(error), error=True)
            return

        if self._editing_entry_id == deleted.entry_id:
            self._reset_correction_editor()
        await self._refresh_history()
        await self._refresh_recent_activities()
        await self._refresh_project_suggestions()
        self._show_message(
            f"Deleted {deleted.project} / {deleted.activity} completed entry."
        )

    def _reset_correction_editor(self) -> None:
        self._editing_entry_id = None
        self._editing_started_at = None
        self._editing_stopped_at = None
        self._creating_manual_entry = False
        self.query_one("#correction-title", Static).update("Correct selected entry")
        for selector in (
            "#correction-project",
            "#correction-activity",
            "#correction-note",
            "#correction-start",
            "#correction-stop",
        ):
            self.query_one(selector, Input).value = ""
        save_button = self.query_one("#save-correction-button", Button)
        save_button.label = "Save correction"
        save_button.disabled = True

    def _clear_delete_confirmation(self) -> None:
        self._pending_delete_entry_id = None
        buttons = self.query("#delete-completed-button")
        if buttons:
            buttons.first(Button).label = "Delete selected entry"

    async def _start_manual_entry(self) -> None:
        if self._review_summary_mode():
            self._show_message(
                "Switch to completed entries before adding missed time.",
                error=True,
            )
            return
        stopped_at = datetime.now().astimezone().replace(second=0, microsecond=0)
        started_at = stopped_at - timedelta(hours=1)
        self._editing_entry_id = None
        self._editing_started_at = None
        self._editing_stopped_at = None
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
        self._editing_started_at = entry.started_at
        self._editing_stopped_at = entry.stopped_at
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
            started_at = _restore_stored_precision(
                _parse_offset_datetime(
                    self.query_one("#correction-start", Input).value,
                    "start",
                ),
                self._editing_started_at,
            )
            stopped_at = _restore_stored_precision(
                _parse_offset_datetime(
                    self.query_one("#correction-stop", Input).value,
                    "stop",
                ),
                self._editing_stopped_at,
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

    async def _refresh_recent_activities(
        self,
        *,
        preferred_pair: RecentActivity | None = None,
    ) -> None:
        try:
            recent = await asyncio.to_thread(self.client.list_recent_activities)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_recent_activities(recent, preferred_pair=preferred_pair)

    async def _refresh_manage_items(self) -> None:
        try:
            active_projects = await asyncio.to_thread(self.client.list_projects)
            active_hierarchy = [
                (
                    project,
                    await asyncio.to_thread(self.client.list_activities, project),
                )
                for project in active_projects
            ]
            archived_projects = await asyncio.to_thread(
                self.client.list_archived_projects
            )
            archived_activities = await asyncio.to_thread(
                self.client.list_archived_activities
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._render_manage_items(
            active_hierarchy,
            archived_projects,
            archived_activities,
        )

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
            button.label = "Start timer  F5"
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

    def _apply_review_filter(self) -> None:
        """Render the last valid shared filter and reject invalid custom input."""
        was_invalid = not self._review_filter_valid
        try:
            selected_filter = self._review_filter_from_controls()
        except ValueError as error:
            self._review_filter_valid = False
            self._clear_export_confirmation()
            self._show_message(str(error), error=True)
            return
        self._review_filter = selected_filter
        self._review_filter_valid = True
        self._clear_export_confirmation()
        self._render_history(self._completed_entries)
        if was_invalid:
            self._show_message("Review filter applied.")

    def _review_filter_from_controls(self) -> ReviewFilter:
        value = self.query_one("#date-preset", Select).value
        if not isinstance(value, str):
            raise ValueError("Select a Review date preset.")
        preset = DatePreset(value)
        custom_start = custom_end = None
        if preset is DatePreset.CUSTOM:
            custom_start = _parse_filter_date(
                self.query_one("#filter-start-date", Input).value,
                "start",
            )
            custom_end = _parse_filter_date(
                self.query_one("#filter-end-date", Input).value,
                "end",
            )
        return review_filter_for_preset(
            preset,
            today=datetime.now().astimezone().date(),
            custom_start=custom_start,
            custom_end=custom_end,
            project=self._selected_review_value("#filter-project"),
            activity=self._selected_review_value("#filter-activity"),
        )

    def _selected_review_value(self, selector: str) -> str:
        value = self.query_one(selector, Select).value
        return value if isinstance(value, str) else ""

    def _set_review_filter_options(self) -> None:
        project_select = self.query_one("#filter-project", Select)
        project_value = (
            project_select.value if isinstance(project_select.value, str) else ""
        )
        projects = review_filter_projects(self._completed_entries)
        project_select.set_options(
            [("Any project", ""), *((project, project) for project in projects)]
        )
        project_select.value = project_value if project_value in projects else ""
        self._set_review_activity_options()

    def _set_review_activity_options(self) -> None:
        activity_select = self.query_one("#filter-activity", Select)
        activity_value = (
            activity_select.value if isinstance(activity_select.value, str) else ""
        )
        project = self._selected_review_value("#filter-project")
        activities = review_filter_activities(self._completed_entries, project)
        activity_select.set_options(
            [("Any activity", ""), *((activity, activity) for activity in activities)]
        )
        activity_select.value = activity_value if activity_value in activities else ""

    def _review_summary_mode(self) -> bool:
        return (
            self.query_one("#summary-mode", Switch).value
            or self.query_one("#range-summary-mode", Switch).value
        )

    @staticmethod
    def _describe_review_filter(review_filter: ReviewFilter) -> str:
        start_date = review_filter.start_date
        end_date = review_filter.end_date
        if start_date is None or end_date is None:
            dates = "All time"
        elif start_date == end_date:
            dates = start_date.isoformat()
        else:
            dates = f"{start_date.isoformat()} through {end_date.isoformat()}"
        project = review_filter.project or "all projects"
        activity = review_filter.activity or "all activities"
        return f"{dates} · {project} · {activity}"

    async def _export_current_view(self) -> None:
        if not self._review_filter_valid:
            self._show_message(
                "Fix the Review filter before exporting.",
                error=True,
            )
            return
        raw_destination = self.query_one("#export-path", Input).value.strip()
        if not raw_destination:
            self._show_message("CSV export path is required.", error=True)
            return
        destination = Path(raw_destination).expanduser().resolve()
        overwrite = self._pending_export_path == destination
        summary_mode = self.query_one("#summary-mode", Switch).value
        range_mode = self.query_one("#range-summary-mode", Switch).value
        if range_mode:
            export = self.client.export_range_summaries
        elif summary_mode:
            export = self.client.export_daily_summaries
        else:
            export = self.client.export_completed
        try:
            row_count = await asyncio.to_thread(
                export,
                destination,
                overwrite=overwrite,
                review_filter=self._review_filter,
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
        if range_mode:
            noun = "range total" if row_count == 1 else "range totals"
        elif summary_mode:
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
        self._clear_delete_confirmation()
        entries_changed = entries is not self._completed_entries
        self._completed_entries = entries
        self._render_today_total(entries)
        if entries_changed:
            self._set_review_filter_options()
        table = self.query_one("#history", DataTable)
        table.clear(columns=True)
        self._history_row_entry_ids = []
        summary_mode = self.query_one("#summary-mode", Switch).value
        range_mode = self.query_one("#range-summary-mode", Switch).value
        summaries = build_daily_summaries(entries, review_filter=self._review_filter)
        range_summaries = build_range_summaries(
            entries,
            review_filter=self._review_filter,
        )
        groups = build_daily_review(entries, review_filter=self._review_filter)
        has_entries = any(group.segments for group in groups)
        has_rows = bool(
            range_summaries if range_mode else summaries if summary_mode else groups
        )
        self.query_one("#history-empty", Static).display = not has_rows
        self.query_one("#active-filter", Static).update(
            self._describe_review_filter(self._review_filter)
        )
        title = self.query_one("#history-title", Static)
        load_button = self.query_one("#load-correction-button", Button)
        manual_button = self.query_one("#add-manual-entry-button", Button)
        delete_button = self.query_one("#delete-completed-button", Button)
        save_button = self.query_one("#save-correction-button", Button)
        correction_inputs = self.query(".correction-input")
        correction_disabled = summary_mode or range_mode
        for correction_input in correction_inputs:
            correction_input.disabled = correction_disabled
        load_button.disabled = correction_disabled or not has_entries
        manual_button.disabled = correction_disabled
        delete_button.disabled = correction_disabled or not has_entries
        save_button.disabled = correction_disabled or (
            self._editing_entry_id is None and not self._creating_manual_entry
        )
        if range_mode:
            title.update("Project/activity totals for selected range")
            table.add_columns("Project", "Activity", "Duration")
            for range_summary in range_summaries:
                table.add_row(
                    range_summary.project,
                    range_summary.activity,
                    _format_review_duration(range_summary.duration),
                    key=f"{range_summary.project}\0{range_summary.activity}",
                )
            return
        if summary_mode:
            title.update("Daily summaries")
            table.add_columns("Date", "Project", "Activity", "Duration")
            for daily_summary in summaries:
                table.add_row(
                    daily_summary.day.isoformat(),
                    daily_summary.project,
                    daily_summary.activity,
                    _format_review_duration(daily_summary.duration),
                    key=(
                        f"{daily_summary.day.isoformat()}\0"
                        f"{daily_summary.project}\0{daily_summary.activity}"
                    ),
                )
            return

        title.update("Completed entries by day")
        table.add_columns(
            "Date",
            "Project",
            "Activity",
            "Start",
            "Stop",
            "Duration",
            "Note",
        )
        for group_index, group in enumerate(groups):
            for segment_index, segment in enumerate(group.segments):
                table.add_row(
                    group.day.isoformat() if segment_index == 0 else "",
                    segment.project,
                    segment.activity,
                    segment.started_at.astimezone().strftime("%H:%M"),
                    segment.stopped_at.astimezone().strftime("%H:%M"),
                    _format_review_duration(segment.duration),
                    segment.note or "",
                    key=(f"entry-{segment.entry_id}-{group_index}-{segment_index}"),
                )
                self._history_row_entry_ids.append(segment.entry_id)
            table.add_row(
                "",
                "Day total",
                "",
                "",
                "",
                _format_review_duration(group.duration),
                "",
                key=f"day-total-{group.day.isoformat()}",
            )
            self._history_row_entry_ids.append(None)
        if preferred_entry_id is not None:
            for index, entry_id in enumerate(self._history_row_entry_ids):
                if entry_id == preferred_entry_id:
                    table.move_cursor(row=index)
                    break

    def _render_today_total(self, entries: list[CompletedTimer]) -> None:
        widgets = self.query("#today-total")
        if not widgets:
            return
        today = datetime.now().astimezone().date()
        duration = next(
            (
                group.duration
                for group in build_daily_review(entries)
                if group.day == today
            ),
            timedelta(),
        )
        widgets.first(Static).update(
            f"Today's completed time: {_format_duration(duration)}"
        )
        self._today_total_day = today

    def _render_recent_activities(
        self,
        recent: list[RecentActivity],
        *,
        preferred_pair: RecentActivity | None = None,
    ) -> None:
        selected_pair = preferred_pair or self._selected_recent_activity()
        self._recent_activities = recent
        option_list = self.query_one("#recent-activities", QuickSwitchDeck)
        option_list.set_options(
            Option(
                f"{index + 1}  {pair.project} / {pair.activity}",
                id=f"recent-{index}",
            )
            for index, pair in enumerate(recent)
        )
        selected_index = next(
            (
                index
                for index, pair in enumerate(recent)
                if selected_pair is not None and pair == selected_pair
            ),
            0 if recent else None,
        )
        option_list.highlighted = selected_index
        option_list.display = bool(recent)
        self.query_one("#recent-empty", Static).display = not recent
        note = self.query_one("#quick-switch-note", Input)
        note.display = bool(recent)
        if selected_index is None:
            self._selected_recent_pair = None
        else:
            self._selected_recent_pair = recent[selected_index]
        self._render_quick_switch_action()

    def _selected_recent_activity(self) -> RecentActivity | None:
        """Return the highlighted canonical deck pair, if it is still available."""
        decks = self.query("#recent-activities")
        if not decks:
            return None
        highlighted = decks.first(QuickSwitchDeck).highlighted
        if highlighted is None or not 0 <= highlighted < len(self._recent_activities):
            return None
        return self._recent_activities[highlighted]

    def _render_quick_switch_action(self) -> None:
        """Describe the pending non-persistent deck action."""
        actions = self.query("#quick-switch-action")
        notes = self.query("#quick-switch-note")
        if not actions or not notes:
            return
        action = actions.first(Static)
        note = notes.first(Input)
        pair = self._selected_recent_activity()
        if pair is None:
            action.update("Use Manual entry below to start new work.")
            note.disabled = True
            return
        selected_name = f"{pair.project} / {pair.activity}"
        pending_action = classify_quick_switch(self.active_timer, pair)
        if pending_action is QuickSwitchAction.CURRENT:
            action.update("Current")
            note.disabled = True
            return
        note.disabled = False
        if pending_action is QuickSwitchAction.START:
            action.update(f"Start {selected_name} · Enter to confirm")
            return
        current = self.active_timer
        if current is None:
            return
        current_name = f"{current.project} / {current.activity}"
        action.update(
            f"Switch from {current_name} to {selected_name} · Enter to confirm"
        )

    def _render_manage_items(
        self,
        active_hierarchy: list[tuple[str, list[str]]],
        archived_projects: list[str],
        archived_activities: list[ArchivedActivity],
    ) -> None:
        active_tree = self.query_one("#active-targets", Tree)
        active_tree.reset("Active")
        active_tree.root.expand()
        first_active = None
        for project, activities in active_hierarchy:
            project_node = active_tree.root.add(
                project,
                ManageTarget(project),
                expand=True,
            )
            first_active = first_active or project_node
            for activity in activities:
                project_node.add_leaf(
                    activity,
                    ManageTarget(project, activity),
                )
        active_tree.move_cursor(first_active)
        has_active = bool(active_hierarchy)
        active_tree.display = has_active
        self.query_one("#active-targets-empty", Static).display = not has_active
        self.query_one("#archive-selected-button", Button).disabled = not has_active

        archived_tree = self.query_one("#archived-targets", Tree)
        archived_tree.reset("Archived")
        archived_tree.root.expand()
        archived_project_names = set(archived_projects)
        grouped: dict[str, list[ArchivedActivity]] = {
            project: [] for project in archived_projects
        }
        for item in archived_activities:
            grouped.setdefault(item.project, []).append(item)
        first_archived = None
        for project in sorted(grouped, key=str.casefold):
            project_node = archived_tree.root.add(
                project,
                (ManageTarget(project) if project in archived_project_names else None),
                expand=True,
            )
            if first_archived is None and project_node.data is not None:
                first_archived = project_node
            for item in grouped[project]:
                activity_node = project_node.add_leaf(
                    item.activity
                    + (" — restore project first" if item.project_archived else ""),
                    ManageTarget(item.project, item.activity),
                )
                first_archived = first_archived or activity_node
        archived_tree.move_cursor(first_archived)
        has_archived = bool(grouped)
        archived_tree.display = has_archived
        self.query_one("#archived-targets-empty", Static).display = not has_archived
        self.query_one("#restore-selected-button", Button).disabled = (
            first_archived is None
        )

    def _render_active(self) -> None:
        active_widgets = self.query("#active-timer")
        stop_buttons = self.query("#stop-button")
        edit_buttons = self.query("#edit-active-button")
        if not active_widgets or not stop_buttons or not edit_buttons:
            return
        current_day = datetime.now().astimezone().date()
        if self._today_total_day != current_day:
            self._render_today_total(self._completed_entries)
            preset = self.query_one("#date-preset", Select).value
            if preset in {
                DatePreset.TODAY.value,
                DatePreset.THIS_WEEK.value,
                DatePreset.THIS_MONTH.value,
            }:
                self._apply_review_filter()
        active_widget = active_widgets.first(Static)
        stop_button = stop_buttons.first(Button)
        edit_button = edit_buttons.first(Button)
        if self.active_timer is None:
            active_widget.update("No timer running")
            stop_button.disabled = True
            edit_button.disabled = True
            self._render_quick_switch_action()
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
        self._render_quick_switch_action()

    def _render_reminder(self) -> None:
        panels = self.query("#reminder")
        buttons = self.query("#confirm-active-reminder-button")
        snooze_buttons = self.query("#snooze-reminder-button")
        message_widgets = self.query("#reminder-message")
        if not panels or not buttons or not snooze_buttons or not message_widgets:
            return
        panel = panels.first(Horizontal)
        button = buttons.first(Button)
        snooze_button = snooze_buttons.first(Button)
        message_widget = message_widgets.first(Static)
        reminder = self.pending_reminder
        panel.display = reminder is not None
        button.display = reminder is not None and reminder.kind is ReminderKind.ACTIVE
        snooze_button.display = reminder is not None
        if reminder is None:
            message_widget.update("")
            self._render_shortcut_summary()
            return
        if reminder.kind is ReminderKind.ACTIVE:
            timer_name = " / ".join(
                part for part in (reminder.project, reminder.activity) if part
            )
            if reminder.reason is ReminderReason.IDLE:
                threshold = _format_minutes(reminder.idle_threshold_minutes or 0)
                message = (
                    f"Still tracking {timer_name}? The computer was idle for at "
                    f"least {threshold} minutes. Confirm to keep tracking, snooze, "
                    "or stop the timer; use Review to remove idle time."
                )
            else:
                message = (
                    f"Still tracking {timer_name}? Confirm to restart the reminder "
                    "interval, or stop the timer."
                )
        else:
            message = "No timer is running. Start one if you are working."
        message_widget.update(message)
        self._render_shortcut_summary()

    def _render_settings(
        self,
        settings: ReminderSettings,
        export_delimiter: str,
    ) -> None:
        self.query_one("#settings-path", Static).update(
            f"Configuration file: {self.client.configuration_path}"
        )
        self.query_one(
            "#inactive-reminders-enabled", Switch
        ).value = settings.inactive_enabled
        self.query_one("#inactive-reminder-minutes", Input).value = _format_minutes(
            settings.inactive_interval_minutes
        )
        self.query_one(
            "#active-reminders-enabled", Switch
        ).value = settings.active_enabled
        self.query_one("#active-reminder-minutes", Input).value = _format_minutes(
            settings.active_interval_minutes
        )
        self.query_one(
            "#reminder-window-enabled", Switch
        ).value = settings.window_enabled
        self.query_one("#reminder-window-weekdays", Input).value = ",".join(
            _WEEKDAY_NAMES[day] for day in settings.window_weekdays
        )
        self.query_one("#reminder-window-start", Input).value = settings.window_start
        self.query_one("#reminder-window-end", Input).value = settings.window_end
        self.query_one("#reminder-snooze-minutes", Input).value = _format_minutes(
            settings.snooze_minutes
        )
        self.query_one("#idle-reminders-enabled", Switch).value = settings.idle_enabled
        self.query_one("#idle-reminder-minutes", Input).value = _format_minutes(
            settings.idle_threshold_minutes
        )
        self.query_one("#export-delimiter", Select).value = export_delimiter
        self._render_idle_status()

    def _render_theme_selection(self) -> None:
        """Show the applied palette in Settings without changing the theme."""
        selects = self.query("#color-palette")
        if selects:
            selects.first(Select).value = self.theme

    def _render_idle_status(self) -> None:
        availability = "available" if self._idle_detection_available else "unavailable"
        self.query_one("#idle-status", Static).update(
            f"Idle detection: {availability} in this platform session"
        )

    def _show_message(self, message: str, *, error: bool = False) -> None:
        widget = self.query_one("#message", Static)
        widget.update(message)
        widget.set_class(not error, "message-success")
        widget.set_class(error, "message-error")


def _format_duration(duration: timedelta) -> str:
    total_seconds = max(0, int(duration.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_review_duration(duration: timedelta) -> str:
    total_seconds = max(0.0, duration.total_seconds())
    total_minutes = math.ceil(total_seconds / 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _parse_offset_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed


def _restore_stored_precision(edited: datetime, stored: datetime | None) -> datetime:
    """Return the stored instant when its displayed second precision is unchanged.

    Correction fields show whole seconds, but stored transitions carry
    sub-second precision and a switch makes one entry stop exactly when the next
    starts. Submitting the displayed value therefore moves an untouched boundary
    earlier into its neighbor, which the no-overlap rule rejects.
    """
    if stored is not None and edited == stored.replace(microsecond=0):
        return stored
    return edited


def _parse_filter_date(value: str, label: str) -> date:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"Custom {label} date is required.")
    try:
        return date.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"Custom {label} date must use YYYY-MM-DD format.") from error


def _parse_positive_minutes(value: str, label: str) -> float:
    try:
        parsed = float(value.strip())
    except ValueError as error:
        raise ValueError(f"{label} must be a positive number.") from error
    try:
        ReminderSettings(inactive_interval_minutes=parsed)
    except ValueError as error:
        raise ValueError(f"{label} must be a positive finite number.") from error
    return parsed


def _parse_weekdays(value: str) -> tuple[int, ...]:
    names = [part.strip().title() for part in value.split(",") if part.strip()]
    if not names:
        raise ValueError("Reminder window weekdays must not be empty.")
    if len(set(names)) != len(names):
        raise ValueError("Reminder window weekdays must not contain duplicates.")
    try:
        return tuple(_WEEKDAY_NAMES.index(name) for name in names)
    except ValueError as error:
        raise ValueError(
            "Reminder window weekdays must use Mon,Tue,Wed,Thu,Fri,Sat,Sun."
        ) from error


def _format_minutes(value: float) -> str:
    return format(float(value), ".15g")
