from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from rich.color_triplet import ColorTriplet
from textual.pilot import Pilot
from textual.widget import Widget
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Input,
    OptionList,
    Select,
    Static,
    Switch,
    Tabs,
    Tree,
)

from time_tracker.agent.server import serve
from time_tracker.application.configuration import (
    ApplicationConfig,
    ReminderSettings,
    UiSettings,
)
from time_tracker.application.reminders import Reminder, ReminderIntervals, ReminderKind
from time_tracker.application.tracking import RecentActivity
from time_tracker.infrastructure.configuration import (
    TomlConfigurationStore,
    load_config,
)
from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository
from time_tracker.tui.app import ReviewDataTable, ShortcutHelpScreen, TimeTrackerApp


class SilentNotifier:
    async def send(self, reminder: Reminder) -> None:
        """Accept test reminders without contacting the host desktop."""


class MonotonicIdleDetector:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._started = time.monotonic()

    def idle_seconds(self) -> float:
        return time.monotonic() - self._started


@pytest.mark.asyncio
async def test_narrow_footer_keeps_complete_shortcut_help_discoverable(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.start("Website", "Planning")
        client.stop()
        app = TimeTrackerApp(client)
        async with app.run_test(size=(40, 24)) as pilot:
            await pilot.pause()
            base_screen = app.screen
            summary = str(app.query_one("#shortcut-summary", Static).render())
            project = app.query_one("#project", Input)
            activity = app.query_one("#activity", Input)

            assert summary.startswith("Ctrl+K Shortcuts")
            assert "F5 Capture" in summary
            assert "F8 Archive project" not in summary
            assert project.region.y < activity.region.y
            assert app.query_one("#track-view").show_horizontal_scrollbar is False
            recent = app.query_one("#recent-activities", OptionList)
            assert recent.option_count == 1
            assert not app.query("#quick-switch-button")
            assert recent.region.y < project.region.y
            assert (
                app.query_one("#quick-switch-note", Input).region.y < project.region.y
            )
            assert (
                app.query_one("#start-button", Button).region.y
                < app.query_one("#stop-button", Button).region.y
            )
            assert app.active_bindings["ctrl+k"].binding.action == "show_shortcuts"
            assert app.active_bindings["ctrl+c"].binding.action == "quit"
            assert (
                app.active_bindings["ctrl+q"].binding.action
                == "ignore_terminal_control"
            )

            await pilot.press("ctrl+k")

            assert isinstance(app.screen, ShortcutHelpScreen)
            help_text = str(
                app.screen.query_one("#shortcut-help-text", Static).render()
            )
            assert "F1 Track" in help_text
            assert "F12 Snooze" in help_text

            await pilot.press("ctrl+k")
            assert app.screen is base_screen

            await pilot.press("ctrl+k")
            assert isinstance(app.screen, ShortcutHelpScreen)
            await pilot.press("escape")
            assert app.screen is base_screen
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_starts_recovers_and_stops_a_persisted_timer(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        first_app = TimeTrackerApp(client)
        async with first_app.run_test() as pilot:
            assert first_app.query_one("#active-targets-empty", Static).display
            assert first_app.query_one("#archived-targets-empty", Static).display
            project_input = first_app.query_one("#project", Input)
            assert (
                project_input.region.y
                == first_app.query_one("#activity", Input).region.y
            )
            first_app.set_focus(project_input)
            await pilot.press("tab")
            assert first_app.focused is first_app.query_one("#activity", Input)
            await pilot.press("tab")
            assert first_app.query_one("#note", Input).has_focus

            project_input.value = "Website"
            first_app.query_one("#activity", Input).value = "Implementation"
            first_app.query_one("#note", Input).value = "Walking skeleton details"
            await pilot.click("#start-button")
            await pilot.pause()

            active_text = str(first_app.query_one("#active-timer", Static).render())
            elapsed_widget = first_app.query_one("#active-elapsed", Static)
            started_widget = first_app.query_one("#active-started", Static)
            active = client.get_active()
            assert active is not None
            local_start = active.started_at.astimezone()
            assert "Website / Implementation" in active_text
            assert "Walking skeleton" in active_text
            assert "Walking skeleton details" in active_text
            started_text = str(started_widget.render())
            assert local_start.strftime("Started %Y-%m-%d %H:%M:%S") in started_text
            assert local_start.isoformat(timespec="seconds") not in started_text
            assert len(str(elapsed_widget.render()).splitlines()) == 3
            assert first_app.query_one("#active-timer", Static).region.x < (
                elapsed_widget.region.x
            )
            assert started_widget.region.y > elapsed_widget.region.y

        assert not first_app.query("#active-timer")
        first_app._render_active()
        first_app._render_reminder()

        recovered_app = TimeTrackerApp(AgentClient(paths))
        async with recovered_app.run_test() as pilot:
            await pilot.pause()
            recovered_text = str(
                recovered_app.query_one("#active-timer", Static).render()
            )
            assert "Website / Implementation" in recovered_text
            assert recovered_app.query_one("#project", Input).value == "Website"
            assert recovered_app.query_one("#activity", Input).value == "Implementation"
            assert recovered_app.query_one("#note", Input).value == (
                "Walking skeleton details"
            )
            recovered_start = recovered_app.query_one("#start-button", Button)
            assert str(recovered_start.label) == "Already tracking"
            assert recovered_start.disabled is True

            stop_button = recovered_app.query_one("#stop-button", Button)
            stop_button.scroll_visible(False, immediate=True)
            await pilot.pause()
            assert await pilot.click(stop_button)
            await pilot.pause()

            assert "No timer running" in str(
                recovered_app.query_one("#active-timer", Static).render()
            )
            assert not recovered_app.query_one("#active-clock-panel").display
            assert (
                str(recovered_app.query_one("#active-elapsed", Static).render()) == ""
            )
            history = recovered_app.query_one("#history", DataTable)
            assert history.row_count == 2
            row = history.get_row_at(0)
            assert row[1] == "Website"
            assert row[2] == "Implementation"
            assert row[6] == "Walking skeleton details"
            assert len(str(row[3])) == 5
            assert history.get_row_at(1)[1] == "Day total"

            await pilot.press("f2")
            await pilot.pause()
            assert recovered_app.query_one(
                "#view-switcher", ContentSwitcher
            ).current == ("review-view")
            assert recovered_app.focused is history

            destination = tmp_path / "tui-export.csv"
            destination.write_text("existing content", encoding="utf-8")
            recovered_app.query_one("#export-path", Input).value = str(destination)
            assert await pilot.click("#export-button")
            await pilot.pause()

            export_button = recovered_app.query_one("#export-button", Button)
            assert "Overwrite CSV" in str(export_button.label)
            assert destination.read_text(encoding="utf-8") == "existing content"

            await pilot.press("f4")
            await pilot.pause()
            assert recovered_app.query_one("#review-view").display is False
            assert "No timer running" in str(
                recovered_app.query_one("#active-timer", Static).render()
            )

            await pilot.press("f7")
            await pilot.pause()

            assert "Export CSV" in str(export_button.label)
            assert "Exported 1 entry" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert "Website,Implementation" in destination.read_text(encoding="utf-8")

            await pilot.press("f2")
            assert await pilot.click("#summary-mode")
            await pilot.pause()

            assert recovered_app.query_one("#summary-mode", Switch).value is True
            summary_row = history.get_row_at(0)
            assert summary_row[1] == "Website"
            assert summary_row[2] == "Implementation"
            assert "Daily summaries" in str(
                recovered_app.query_one("#history-title", Static).render()
            )

            summary_destination = tmp_path / "tui-daily-summary.csv"
            recovered_app.query_one("#export-path", Input).value = str(
                summary_destination
            )
            await pilot.press("f7")
            await pilot.pause()

            assert "Exported 1 daily summary" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert summary_destination.read_text(encoding="utf-8").startswith(
                "date,project,activity,duration_seconds"
            )

            await pilot.press("f3")
            active_tree = recovered_app.query_one("#active-targets", Tree)
            active_tree.move_cursor(active_tree.root.children[0].children[0])
            await pilot.pause()
            recovered_app.query_one("#archive-selected-button", Button).focus()
            await pilot.press("enter")
            await pilot.pause()

            assert "Any active timer will continue" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_activities("Website") == ["Implementation"]

            await pilot.press("f9")
            await pilot.pause()

            assert "Archived activity Website / Implementation" in str(
                recovered_app.query_one("#message", Static).render()
            )
            archived_tree = recovered_app.query_one("#archived-targets", Tree)
            assert len(archived_tree.root.children[0].children) == 1
            await pilot.press("f1")
            await pilot.press("f5")
            await pilot.pause()

            assert "activity is archived: Implementation" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert "No timer running" in str(
                recovered_app.query_one("#active-timer", Static).render()
            )
            assert history.row_count == 1

            await pilot.press("f3")
            active_tree = recovered_app.query_one("#active-targets", Tree)
            active_tree.move_cursor(active_tree.root.children[0])
            await pilot.pause()
            await pilot.press("f4")
            await pilot.press("f8")
            await pilot.pause()

            assert client.list_projects() == ["Website"]
            assert "Press Archive project again" in str(
                recovered_app.query_one("#message", Static).render()
            )
            await pilot.press("f8")
            await pilot.pause()

            assert "Archived project Website" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_projects() == []

            await pilot.press("f3")
            archived_tree = recovered_app.query_one("#archived-targets", Tree)
            project_node = archived_tree.root.children[0]
            assert "restore project first" in str(project_node.children[0].label)
            archived_tree.move_cursor(project_node.children[0])
            recovered_app.query_one("#restore-selected-button", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert "restore project first" in str(
                recovered_app.query_one("#message", Static).render()
            )

            archived_tree.move_cursor(project_node)
            recovered_app.query_one("#restore-selected-button", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert "Restored project Website" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_projects() == ["Website"]
            assert client.list_activities("Website") == []

            archived_tree = recovered_app.query_one("#archived-targets", Tree)
            archived_tree.move_cursor(archived_tree.root.children[0].children[0])
            await pilot.pause()
            restore_button = recovered_app.query_one("#restore-selected-button", Button)
            assert restore_button.disabled is False
            restore_button.focus()
            await pilot.pause()
            restore_button.press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Restored activity Website / Implementation"
                    in str(recovered_app.query_one("#message", Static).render())
                ),
                "archived activity was not restored",
            )
            assert client.list_activities("Website") == ["Implementation"]

        assert SQLiteTimerRepository(paths.database).get_active() is None
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_prepares_a_project_and_activity_without_starting_a_timer(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f3")
            await pilot.pause()

            app.query_one("#new-project", Input).value = "Research"
            create_project_button = app.query_one("#create-project-button", Button)
            assert str(create_project_button.label) == "Add project"
            create_project_button.focus()
            await pilot.pause()
            create_project_button.press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Created project Research"
                    in str(app.query_one("#message", Static).render())
                ),
                "project was not created",
            )
            assert app.query_one("#new-project", Input).value == ""
            active_tree = app.query_one("#active-targets", Tree)
            assert [str(node.label) for node in active_tree.root.children] == [
                "Research"
            ]
            assert client.list_projects() == ["Research"]

            app.query_one("#new-project", Input).value = "research"
            create_project_button.focus()
            await pilot.pause()
            create_project_button.press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "project already exists: Research"
                    in str(app.query_one("#message", Static).render())
                ),
                "duplicate project was not rejected",
            )

            app.query_one("#new-activity-project", Input).value = "research"
            app.query_one("#new-activity-name", Input).value = "Literature review"
            create_activity_button = app.query_one("#create-activity-button", Button)
            assert str(create_activity_button.label) == "Add activity"
            create_activity_button.focus()
            await pilot.pause()
            create_activity_button.press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Created activity Research / Literature review"
                    in str(app.query_one("#message", Static).render())
                ),
                "activity was not created",
            )
            assert app.query_one("#new-activity-name", Input).value == ""
            active_tree = app.query_one("#active-targets", Tree)
            assert [
                str(node.label) for node in active_tree.root.children[0].children
            ] == ["Literature review"]
            assert client.list_activities("Research") == ["Literature review"]

            app.query_one("#new-activity-name", Input).value = "literature review"
            create_activity_button.focus()
            await pilot.pause()
            create_activity_button.press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "activity already exists: Research/Literature review"
                    in str(app.query_one("#message", Static).render())
                ),
                "duplicate activity was not rejected",
            )

            app.query_one("#new-activity-project", Input).value = "Unknown"
            app.query_one("#new-activity-name", Input).value = "Planning"
            create_activity_button.focus()
            await pilot.pause()
            create_activity_button.press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "project not found: Unknown"
                    in str(app.query_one("#message", Static).render())
                ),
                "missing project was not rejected",
            )
            assert client.list_activities("Research") == ["Literature review"]
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_rejected_second_archive_invocation_clears_confirmation(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.start("Website", "Planning")
        client.stop()
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f3")
            active_tree = app.query_one("#active-targets", Tree)
            active_tree.move_cursor(active_tree.root.children[0].children[0])
            await pilot.pause()

            await pilot.press("f9")
            await pilot.pause()
            assert app._pending_archive_activity is not None

            client.archive_activity("Website", "Planning")
            await pilot.press("f9")
            await pilot.pause()

            assert app._pending_archive_activity is None
            assert "activity is already archived: Planning" in str(
                app.query_one("#message", Static).render()
            )
            assert (
                str(app.query_one("#archive-selected-button", Button).label)
                == "Archive selected"
            )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_snoozes_and_confirms_an_active_reminder_from_the_tui(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": SilentNotifier(),
            "reminder_intervals": ReminderIntervals(inactive=None, active=0.25),
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.save_configuration(
            ReminderSettings(
                inactive_enabled=False,
                active_interval_minutes=0.004,
                snooze_minutes=0.001,
            )
        )
        started = client.start("Reminder", "Interaction")
        _wait_for_pending_reminder(client, ReminderKind.ACTIVE)

        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.pause()
            prompt = str(app.query_one("#reminder-message", Static).render())
            assert "Still tracking Reminder / Interaction?" in prompt

            await pilot.press("f12")
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Reminder snoozed"
                    in str(app.query_one("#message", Static).render())
                ),
                "snooze was not reported in the interface",
            )

            assert app.pending_reminder is None
            assert client.get_active() == started

            _wait_for_pending_reminder(client, ReminderKind.ACTIVE)
            await app._refresh_reminder()
            await pilot.pause()
            assert await pilot.click("#confirm-active-reminder-button")
            await _wait_for_ui(
                pilot,
                lambda: (
                    "interval restarted"
                    in str(app.query_one("#message", Static).render())
                ),
                "confirmation was not reported in the interface",
            )

            assert app.pending_reminder is None
            assert client.get_active() == started
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_tui_identifies_idle_triggered_active_reminder(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    detector = MonotonicIdleDetector()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": SilentNotifier(),
            "idle_detector": detector,
            "idle_poll_seconds": 0.01,
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.save_configuration(
            ReminderSettings(
                inactive_enabled=False,
                active_enabled=False,
                idle_enabled=True,
                idle_threshold_minutes=0.001,
            )
        )
        started = client.start("Idle", "TUI")
        detector.reset()
        _wait_for_pending_reminder(client, ReminderKind.ACTIVE)

        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await _wait_for_ui(
                pilot,
                lambda: (
                    "computer was idle"
                    in str(app.query_one("#reminder-message", Static).render())
                ),
                "idle reminder was not rendered",
            )
            prompt = str(app.query_one("#reminder-message", Static).render())
            assert "at least 0.001 minutes" in prompt
            assert "use Review to remove idle time" in prompt

            await pilot.press("f10")
            # The fake detector never observes input, so the agent becomes
            # eligible to prompt again immediately. Assert the confirmation was
            # reported rather than the momentary cleared prompt, which the next
            # reminder refresh legitimately repopulates.
            await _wait_for_ui(
                pilot,
                lambda: (
                    "interval restarted"
                    in str(app.query_one("#message", Static).render())
                ),
                "confirmed idle reminder was not reported",
            )

            assert client.get_active() == started
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_quick_switches_from_recent_activities(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.start("Website", "Planning", "First historical note")
        client.stop()
        client.start("Website", "Implementation", "Most recent historical note")
        client.stop()

        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.pause()
            recent = app.query_one("#recent-activities", OptionList)
            assert recent.option_count == 2
            assert "1  Website / Implementation" in str(
                recent.get_option_at_index(0).prompt
            )
            assert app.focused is recent
            assert "Start Website / Implementation" in str(
                app.query_one("#quick-switch-action", Static).render()
            )

            app.query_one("#project", Input).value = "Temporary"
            app.query_one("#activity", Input).value = "Draft"
            app.query_one("#note", Input).value = "Do not preserve this"
            app.query_one("#project", Input).focus()
            await pilot.press("1")
            await pilot.pause()

            assert app.query_one("#project", Input).value == "1"
            assert recent.highlighted == 0
            assert client.get_active() is None

            recent.focus()
            await pilot.pause(0.2)
            content_offset = recent.content_region.offset - recent.region.offset
            second_option_line = recent._index_to_line[1] - recent.scroll_offset.y
            pointer_offset = (
                content_offset.x + 2,
                content_offset.y + second_option_line,
            )
            assert await pilot.click(
                "#recent-activities",
                offset=pointer_offset,
            )
            await pilot.pause()
            assert recent.highlighted == 1
            assert client.get_active() is None
            assert app.query_one("#project", Input).value == "Website"
            assert app.query_one("#activity", Input).value == "Planning"
            assert app.query_one("#note", Input).value == ""

            app.query_one("#project", Input).value = "Temporary"
            app.query_one("#activity", Input).value = "Draft"
            app.query_one("#note", Input).value = "Clear with arrows"
            recent.focus()
            await pilot.press("up")
            await pilot.pause()
            assert recent.highlighted == 0
            assert app.query_one("#project", Input).value == "Website"
            assert app.query_one("#activity", Input).value == "Implementation"
            assert app.query_one("#note", Input).value == ""

            await pilot.press("down")
            await pilot.pause()
            assert recent.highlighted == 1
            assert app.query_one("#project", Input).value == "Website"
            assert app.query_one("#activity", Input).value == "Planning"

            app.query_one("#project", Input).value = "Temporary"
            app.query_one("#activity", Input).value = "Draft"
            app.query_one("#note", Input).value = "Clear this too"

            app.query_one("#start-button", Button).focus()
            await pilot.press("2")
            await pilot.pause()

            assert recent.highlighted == 1
            assert app.focused is recent
            assert client.get_active() is None
            assert app.query_one("#project", Input).value == "Website"
            assert app.query_one("#activity", Input).value == "Planning"
            assert app.query_one("#note", Input).value == ""
            assert "Start Website / Planning" in str(
                app.query_one("#quick-switch-action", Static).render()
            )

            quick_note = app.query_one("#quick-switch-note", Input)
            quick_note.value = "Fresh deck note"
            quick_note.focus()
            await pilot.press("enter")
            await pilot.pause()

            active = client.get_active()
            assert active is not None
            assert active.project == "Website"
            assert active.activity == "Planning"
            assert active.note == "Fresh deck note"
            assert app.query_one("#project", Input).value == "Website"
            assert app.query_one("#activity", Input).value == "Planning"
            assert app.query_one("#note", Input).value == "Fresh deck note"
            assert quick_note.value == ""
            assert str(app.query_one("#quick-switch-action", Static).render()) == (
                "Current"
            )

            original = active
            history_before_current = client.list_completed()
            recent.focus()
            await pilot.press("enter")
            await pilot.pause()

            assert client.get_active() == original
            assert client.list_completed() == history_before_current

            await pilot.press("1")
            await pilot.pause()
            assert "Switch from Website / Planning to Website / Implementation" in str(
                app.query_one("#quick-switch-action", Static).render()
            )
            recent.focus()
            await pilot.press("enter")
            await pilot.pause()

            switched = client.get_active()
            assert switched is not None
            assert switched.activity == "Implementation"
            assert switched.note is None
            planning_entry = client.list_completed()[-1]
            assert planning_entry.entry_id == original.entry_id
            assert planning_entry.stopped_at == switched.started_at

            await pilot.press("f6")
            await pilot.pause()

            assert app._recent_activities[0].activity == "Implementation"
            await pilot.press("f3")
            active_tree = app.query_one("#active-targets", Tree)
            implementation_node = next(
                node
                for node in active_tree.root.children[0].children
                if str(node.label) == "Implementation"
            )
            active_tree.move_cursor(implementation_node)
            await pilot.pause()
            await pilot.press("f9")
            await pilot.pause()

            assert [pair.activity for pair in app._recent_activities] == [
                "Implementation",
                "Planning",
            ]
            await pilot.press("f9")
            await pilot.pause()

            assert [pair.activity for pair in app._recent_activities] == ["Planning"]
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_navigates_focused_views_without_losing_workflow_state(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.start("Website", "Review", "Persistent context")
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.pause()
            tabs = app.query_one("#view-tabs", Tabs)
            switcher = app.query_one("#view-switcher", ContentSwitcher)
            active = app.query_one("#active-timer", Static)

            assert tabs.active == "track-tab"
            assert switcher.current == "track-view"
            assert app.focused is app.query_one("#project", Input)
            assert "Website / Review" in str(active.render())

            app.query_one("#note", Input).value = "Draft replacement"
            await pilot.press("f2")
            assert tabs.active == "review-tab"
            assert switcher.current == "review-view"
            assert app.query_one("#history", DataTable).has_focus
            app.query_one("#export-path", Input).value = str(tmp_path / "review.csv")
            app.query_one("#summary-mode", Switch).value = True

            await pilot.click("#manage-tab")
            await pilot.pause()
            assert tabs.active == "manage-tab"
            assert switcher.current == "manage-view"
            manage_tree = app.query_one("#active-targets", Tree)
            assert manage_tree.has_focus
            manage_tree.move_cursor(manage_tree.root.children[0].children[0])

            await pilot.press("f4")
            assert tabs.active == "settings-tab"
            assert switcher.current == "settings-view"
            assert app.query_one("#inactive-reminders-enabled", Switch).has_focus
            assert "Website / Review" in str(active.render())

            client.archive_activity("Website", "Review")
            await pilot.press("f1")
            assert app.query_one("#note", Input).value == "Draft replacement"
            await pilot.press("f2")
            assert app.query_one("#export-path", Input).value.endswith("review.csv")
            assert app.query_one("#summary-mode", Switch).value is True
            await pilot.press("f3")
            await _wait_for_ui(
                pilot,
                lambda: any(
                    str(activity.label).startswith("Review")
                    for project in app.query_one(
                        "#archived-targets", Tree
                    ).root.children
                    for activity in project.children
                ),
                "Manage trees did not refresh when the view was selected",
            )
            assert len(manage_tree.root.children[0].children) == 0
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_primary_action_distinguishes_start_restart_and_switch(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            start_button = app.query_one("#start-button", Button)
            assert str(start_button.label) == "Start timer  F5"
            assert start_button.disabled is False

            app.query_one("#project", Input).value = "Website"
            app.query_one("#activity", Input).value = "Implementation"
            app.query_one("#note", Input).value = "Original note"
            await pilot.pause()
            await pilot.press("f5")
            await pilot.pause()

            original = client.get_active()
            assert original is not None
            assert str(start_button.label) == "Already tracking"
            assert start_button.disabled is True

            await pilot.press("f5")
            await pilot.pause()
            assert client.get_active() == original
            assert client.list_completed() == []

            app.query_one("#note", Input).value = "New note"
            await pilot.pause()
            assert str(start_button.label) == "Restart with new note  F5"
            assert start_button.disabled is False

            await pilot.press("f5")
            await pilot.pause()
            restarted = client.get_active()
            assert restarted is not None
            assert restarted.entry_id != original.entry_id
            assert restarted.note == "New note"
            completed = client.list_completed()
            assert len(completed) == 1
            assert completed[0].stopped_at == restarted.started_at
            assert str(start_button.label) == "Already tracking"

            app.query_one("#activity", Input).value = "Review"
            await pilot.pause()
            assert "Switch from Website / Implementation to Website / Review" in str(
                start_button.label
            )
            assert start_button.disabled is False

            await pilot.press("f5")
            await pilot.pause()
            switched = client.get_active()
            assert switched is not None
            assert switched.activity == "Review"
            completed = client.list_completed()
            assert len(completed) == 2
            assert completed[1].stopped_at == switched.started_at
            assert str(start_button.label) == "Already tracking"
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_review_groups_local_days_and_loads_an_overnight_entry_segment(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    repository = SQLiteTimerRepository(paths.database)
    local_midnight = (
        datetime.now()
        .astimezone()
        .replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )
    overnight_start = local_midnight - timedelta(minutes=30)
    overnight_stop = local_midnight + timedelta(minutes=30)
    overnight = repository.start(
        "Client",
        "Release",
        overnight_start,
        "Across midnight",
    )
    repository.stop(overnight_stop)
    repository.start(
        "Client",
        "Review",
        local_midnight + timedelta(hours=1),
        None,
    )
    repository.stop(local_midnight + timedelta(hours=1, minutes=45))
    repository.start(
        "Client",
        "Active",
        local_midnight + timedelta(hours=2),
        None,
    )
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f2")
            await pilot.pause()
            history = app.query_one("#history", ReviewDataTable)

            assert history.row_count == 6
            assert history.is_date_divider(0) is False
            assert history.is_date_divider(2) is True
            assert all(set(str(cell)) == {"─"} for cell in history.get_row_at(2))
            first_segment = history.get_row_at(0)
            assert (
                first_segment[0]
                == (local_midnight.date() - timedelta(days=1)).isoformat()
            )
            assert first_segment[1:7] == [
                "Client",
                "Release",
                "23:30",
                "00:00",
                "0h 30m",
                "Across midnight",
            ]
            assert history.get_row_at(1)[1] == "Day total"

            second_segment = history.get_row_at(3)
            assert second_segment[0] == local_midnight.date().isoformat()
            assert second_segment[3:6] == ["00:00", "00:30", "0h 30m"]
            assert history.get_row_at(4)[0] == ""
            assert history.get_row_at(5)[1] == "Day total"
            assert history.get_row_at(5)[5] == "1h 15m"
            assert "Today's completed time: 01:15:00" in str(
                app.query_one("#today-total", Static).render()
            )

            summary_mode = app.query_one("#summary-mode", Switch)
            summary_mode.value = True
            await pilot.pause()
            assert history.row_count == 4
            assert history.is_date_divider(0) is False
            assert history.is_date_divider(1) is True
            assert all(set(str(cell)) == {"─"} for cell in history.get_row_at(1))
            assert history.get_row_at(2)[0] == local_midnight.date().isoformat()

            summary_mode.value = False
            await pilot.pause()
            assert history.row_count == 6
            assert history.is_date_divider(2) is True

            history.move_cursor(row=3)
            app.query_one("#load-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: app._editing_entry_id == overnight.entry_id,
                "overnight entry segment did not load its source entry",
            )
            assert datetime.fromisoformat(
                app.query_one("#correction-start", Input).value
            ).astimezone(UTC) == overnight_start.astimezone(UTC)
            assert datetime.fromisoformat(
                app.query_one("#correction-stop", Input).value
            ).astimezone(UTC) == overnight_stop.astimezone(UTC)

            history.move_cursor(row=5)
            app.query_one("#load-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Select a completed entry row"
                    in str(app.query_one("#message", Static).render())
                ),
                "day-total selection was not rejected",
            )
            assert app._editing_entry_id == overnight.entry_id
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_review_deletes_selected_entry_and_rounds_duration_up(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    repository = SQLiteTimerRepository(paths.database)
    local_midnight = (
        datetime.now()
        .astimezone()
        .replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )
    completed_active = repository.start(
        "Client",
        "Overnight",
        local_midnight - timedelta(minutes=30),
        "Delete all segments",
    )
    completed = repository.stop(local_midnight + timedelta(minutes=30, seconds=1))
    assert completed is not None
    active = repository.start(
        "Client",
        "Keep active",
        local_midnight + timedelta(hours=1),
        None,
    )
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f2")
            await pilot.pause()
            history = app.query_one("#history", DataTable)
            delete_button = app.query_one("#delete-completed-button", Button)

            assert history.row_count == 5
            assert history.get_row_at(0)[5] == "0h 30m"
            assert history.get_row_at(3)[5] == "0h 31m"
            assert "Today's completed time: 00:30:01" in str(
                app.query_one("#today-total", Static).render()
            )

            history.move_cursor(row=3)
            delete_button.press()
            await pilot.pause()
            assert client.list_completed() == [completed]
            assert "Confirm delete" in str(delete_button.label)
            delete_message = str(app.query_one("#message", Static).render())
            local_start = completed.started_at.astimezone()
            assert local_start.strftime("%Y-%m-%d %H:%M") in delete_message
            assert local_start.isoformat(timespec="minutes") not in delete_message

            history.move_cursor(row=4)
            delete_button.press()
            await pilot.pause()
            assert client.list_completed() == [completed]
            assert "Select a completed entry row" in str(
                app.query_one("#message", Static).render()
            )

            history.move_cursor(row=3)
            delete_button.press()
            await pilot.pause()
            assert client.list_completed() == [completed]
            delete_button.press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Deleted Client / Overnight"
                    in str(app.query_one("#message", Static).render())
                ),
                "selected entry was not deleted",
            )

            assert history.row_count == 0
            assert client.list_completed() == []
            assert client.get_active() == active
            assert completed_active.entry_id != active.entry_id
            assert "Deleted Client / Overnight" in str(
                app.query_one("#message", Static).render()
            )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_review_filters_range_totals_and_export_share_one_selection(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    repository = SQLiteTimerRepository(paths.database)
    local_timezone = datetime.now().astimezone().tzinfo

    def utc_instant(day: int, hour: int, minute: int = 0) -> datetime:
        return datetime(
            2026,
            7,
            day,
            hour,
            minute,
            tzinfo=local_timezone,
        ).astimezone(UTC)

    repository.start("Client", "Research", utc_instant(19, 23, 30), "Overnight")
    repository.stop(utc_instant(20, 0, 30))
    repository.start("Client", "Writing", utc_instant(20, 9), None)
    repository.stop(utc_instant(20, 10))
    repository.start("Internal", "Research", utc_instant(20, 11), None)
    repository.stop(utc_instant(20, 11, 30))

    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.archive_project("Client")
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f2")
            app.query_one("#date-preset", Select).value = "custom"
            app.query_one("#filter-start-date", Input).value = "2026-07-20"
            app.query_one("#filter-end-date", Input).value = "2026-07-20"
            app.query_one("#filter-project", Select).value = "Client"
            await pilot.pause()

            history = app.query_one("#history", DataTable)
            assert history.row_count == 3
            assert history.get_row_at(0)[0] == "2026-07-20"
            assert history.get_row_at(0)[1:3] == ["Client", "Research"]
            assert history.get_row_at(1)[1:3] == ["Client", "Writing"]
            assert history.get_row_at(2)[1] == "Day total"
            assert "2026-07-20 · Client · all activities" in str(
                app.query_one("#active-filter", Static).render()
            )

            activity_select = app.query_one("#filter-activity", Select)
            activity_select.value = "Writing"
            await pilot.pause()
            assert history.row_count == 2
            assert history.get_row_at(0)[1:3] == ["Client", "Writing"]
            activity_select.value = ""
            await pilot.pause()

            range_switch = app.query_one("#range-summary-mode", Switch)
            range_switch.focus()
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            assert range_switch.value is True
            assert history.row_count == 2
            assert history.get_row_at(0) == ["Client", "Research", "0h 30m"]
            assert history.get_row_at(1) == ["Client", "Writing", "1h 00m"]
            assert "Project/activity totals" in str(
                app.query_one("#history-title", Static).render()
            )

            destination = tmp_path / "filtered-range.csv"
            app.query_one("#export-path", Input).value = str(destination)
            await pilot.press("f7")
            await pilot.pause()

            assert destination.read_text(encoding="utf-8").splitlines() == [
                "project,activity,duration_seconds",
                "Client,Research,1800",
                "Client,Writing,3600",
            ]

            app.query_one("#filter-end-date", Input).value = "invalid"
            invalid_destination = tmp_path / "invalid.csv"
            app.query_one("#export-path", Input).value = str(invalid_destination)
            await pilot.press("f7")
            await pilot.pause()

            assert history.row_count == 2
            assert not invalid_destination.exists()
            assert "Fix the Review filter" in str(
                app.query_one("#message", Static).render()
            )

            app.query_one("#filter-end-date", Input).value = "2026-07-20"
            app.query_one("#filter-start-date", Input).value = "2026-07-21"
            app.query_one("#filter-end-date", Input).value = "2026-07-21"
            await pilot.pause()

            assert history.row_count == 0
            assert app.query_one("#history-empty", Static).display
            empty_destination = tmp_path / "empty.csv"
            app.query_one("#export-path", Input).value = str(empty_destination)
            await pilot.press("f7")
            await pilot.pause()
            assert empty_destination.read_text(encoding="utf-8") == (
                "project,activity,duration_seconds\n"
            )
            assert "Exported 0 range totals" in str(
                app.query_one("#message", Static).render()
            )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_corrects_a_selected_completed_entry_in_review(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    repository = SQLiteTimerRepository(paths.database)
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    original = repository.start("Website", "Planning", started_at, "Original")
    repository.stop(started_at + timedelta(hours=1))
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f2")
            await pilot.pause()
            app.query_one("#load-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: app.query_one("#correction-project", Input).value == "Website",
                "selected entry was not loaded into the correction form",
            )

            assert app.query_one("#correction-project", Input).value == "Website"
            assert app.query_one("#correction-note", Input).value == "Original"
            app.query_one("#correction-project", Input).value = "Client"
            app.query_one("#correction-activity", Input).value = "Review"
            app.query_one("#correction-note", Input).value = "Revised"
            app.query_one("#correction-start", Input).value = (
                started_at + timedelta(minutes=5)
            ).isoformat()
            app.query_one("#correction-stop", Input).value = (
                started_at + timedelta(minutes=55)
            ).isoformat()

            app.query_one("#save-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Corrected Client / Review"
                    in str(app.query_one("#message", Static).render())
                ),
                "correction did not complete",
            )

            corrected = client.list_completed()[0]
            assert corrected.entry_id == original.entry_id
            assert corrected.project == "Client"
            assert corrected.activity == "Review"
            assert corrected.note == "Revised"
            row = app.query_one("#history", DataTable).get_row_at(0)
            assert row[1] == "Client"
            assert row[2] == "Review"
            assert row[6] == "Revised"
            assert "Corrected Client / Review" in str(
                app.query_one("#message", Static).render()
            )

            app.query_one("#correction-start", Input).value = "2026-07-20T08:00:00"
            app.query_one("#save-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "start must include a UTC offset"
                    in str(app.query_one("#message", Static).render())
                ),
                "invalid correction was not reported",
            )
            assert "start must include a UTC offset" in str(
                app.query_one("#message", Static).render()
            )
            assert client.list_completed() == [corrected]

            app.query_one("#summary-mode", Switch).value = True
            await pilot.pause()
            assert app.query_one("#load-correction-button", Button).disabled is True
            assert app.query_one("#save-correction-button", Button).disabled is True
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_correction_keeps_untouched_switch_boundaries(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    repository = SQLiteTimerRepository(paths.database)
    # Switching records one sub-second instant as the first entry's stop and the
    # second entry's start, so a second-precision round trip of either boundary
    # would move it into its neighbor.
    started_at = datetime(2026, 7, 20, 8, 0, 0, 123456, tzinfo=UTC)
    switched_at = datetime(2026, 7, 20, 9, 30, 0, 654321, tzinfo=UTC)
    stopped_at = datetime(2026, 7, 20, 10, 30, 0, 789012, tzinfo=UTC)
    repository.start("Website", "Planning", started_at, None)
    repository.start("Website", "Implementation", switched_at, "Original")
    repository.stop(stopped_at)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f2")
            await pilot.pause()
            app.query_one("#history", DataTable).move_cursor(row=1)
            app.query_one("#load-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    app.query_one("#correction-activity", Input).value
                    == "Implementation"
                ),
                "the switched entry was not loaded into the correction form",
            )

            assert app.query_one("#correction-start", Input).value == (
                switched_at.astimezone().isoformat(timespec="seconds")
            )
            app.query_one("#correction-note", Input).value = "Revised"
            app.query_one("#save-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Corrected Website / Implementation"
                    in str(app.query_one("#message", Static).render())
                ),
                "correcting a note next to a switch boundary was rejected",
            )

            first, corrected = client.list_completed()
            assert corrected.note == "Revised"
            assert corrected.started_at == switched_at
            assert corrected.stopped_at == stopped_at
            assert first.stopped_at == switched_at
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_adds_missed_time_without_changing_active_timer(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    repository = SQLiteTimerRepository(paths.database)
    started_at = datetime(2026, 7, 20, 8, tzinfo=UTC)
    repository.start("Website", "Planning", started_at, None)
    repository.stop(started_at + timedelta(hours=1))
    active = repository.start(
        "Website",
        "Implementation",
        started_at + timedelta(hours=4),
        "Current work",
    )
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f2")
            await pilot.pause()
            app.query_one("#add-manual-entry-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    str(app.query_one("#save-correction-button", Button).label)
                    == "Create missed entry"
                ),
                "missed-entry form was not prepared",
            )

            assert app.query_one("#correction-project", Input).value == ""
            assert (
                datetime.fromisoformat(
                    app.query_one("#correction-start", Input).value
                ).tzinfo
                is not None
            )
            assert (
                str(app.query_one("#save-correction-button", Button).label)
                == "Create missed entry"
            )

            app.query_one("#correction-project", Input).value = "Client"
            app.query_one("#correction-activity", Input).value = "Review"
            app.query_one("#correction-note", Input).value = "Missed work"
            app.query_one("#correction-start", Input).value = (
                started_at + timedelta(hours=1)
            ).isoformat()
            app.query_one("#correction-stop", Input).value = (
                started_at + timedelta(hours=2)
            ).isoformat()
            app.query_one("#save-correction-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Added missed entry for Client / Review"
                    in str(app.query_one("#message", Static).render())
                ),
                "missed entry did not complete",
            )

            assert client.get_active() == active
            entries = client.list_completed()
            assert len(entries) == 2
            manual = entries[1]
            assert manual.project == "Client"
            assert manual.activity == "Review"
            assert manual.note == "Missed work"
            assert app.query_one("#history", DataTable).row_count == 3
            assert "Added missed entry for Client / Review" in str(
                app.query_one("#message", Static).render()
            )
            assert app._recent_activities[0] == RecentActivity("Client", "Review")

            app.query_one("#summary-mode", Switch).value = True
            await pilot.pause()
            assert app.query_one("#add-manual-entry-button", Button).disabled is True
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_updates_active_details_without_restarting_timer(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        original = client.start("Website", "Planning", "Original")
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.pause()
            edit_button = app.query_one("#edit-active-button", Button)
            assert edit_button.disabled is True

            app.query_one("#project", Input).value = "Client"
            app.query_one("#activity", Input).value = "Review"
            app.query_one("#note", Input).value = "Revised"
            await pilot.pause()
            assert edit_button.disabled is False

            await pilot.press("f11")
            await pilot.pause()

            edited = client.get_active()
            assert edited is not None
            assert edited.entry_id == original.entry_id
            assert edited.started_at == original.started_at
            assert edited.project == "Client"
            assert edited.activity == "Review"
            assert edited.note == "Revised"
            assert client.list_completed() == []
            assert edit_button.disabled is True
            assert "Updated active details to Client / Review" in str(
                app.query_one("#message", Static).render()
            )
            assert "Client / Review" in str(
                app.query_one("#active-timer", Static).render()
            )

            app.query_one("#note", Input).value = "Pointer update"
            await pilot.pause()
            assert await pilot.click("#edit-active-button")
            await pilot.pause()
            pointer_edited = client.get_active()
            assert pointer_edited is not None
            assert pointer_edited.entry_id == original.entry_id
            assert pointer_edited.started_at == original.started_at
            assert pointer_edited.note == "Pointer update"

        recovered_app = TimeTrackerApp(AgentClient(paths))
        async with recovered_app.run_test() as pilot:
            await pilot.pause()
            assert recovered_app.query_one("#project", Input).value == "Client"
            assert recovered_app.query_one("#activity", Input).value == "Review"
            assert recovered_app.query_one("#note", Input).value == "Pointer update"
            recovered = client.get_active()
            assert recovered is not None
            assert recovered.entry_id == original.entry_id
            assert recovered.started_at == original.started_at
            assert (
                recovered_app.query_one("#edit-active-button", Button).disabled is True
            )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_edits_and_live_applies_reminder_settings(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": SilentNotifier(),
            "reminder_intervals": ReminderIntervals(inactive=None, active=None),
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f4")
            await pilot.pause()
            assert app.focused is app.query_one("#inactive-reminders-enabled", Switch)
            assert str(paths.config) in str(
                app.query_one("#settings-path", Static).render()
            )
            assert not app.query_one("#inactive-reminders-enabled", Switch).value
            inactive_minutes = app.query_one("#inactive-reminder-minutes", Input)
            assert inactive_minutes.value == "5"
            assert inactive_minutes.region.height == 3
            assert inactive_minutes.content_region.height == 1
            assert app.query_one("#export-delimiter", Select).value == ","
            app.theme = "nord"
            await _wait_for_ui(
                pilot,
                lambda: client.get_theme() == "nord",
                "selected theme was not persisted",
            )

            app.query_one("#inactive-reminders-enabled", Switch).value = True
            app.query_one("#inactive-reminder-minutes", Input).value = "2.5"
            app.query_one("#active-reminders-enabled", Switch).value = True
            app.query_one("#active-reminder-minutes", Input).value = "12"
            app.query_one("#reminder-window-enabled", Switch).value = True
            app.query_one("#reminder-window-weekdays", Input).value = "Mon,Wed,Fri"
            app.query_one("#reminder-window-start", Input).value = "08:30"
            app.query_one("#reminder-window-end", Input).value = "18:00"
            app.query_one("#reminder-snooze-minutes", Input).value = "7.5"
            app.query_one("#idle-reminders-enabled", Switch).value = True
            app.query_one("#idle-reminder-minutes", Input).value = "22.5"
            app.query_one("#export-delimiter", Select).value = "|"
            app.query_one("#save-settings-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "Settings saved and applied"
                    in str(app.query_one("#message", Static).render())
                ),
                "settings success message was not shown",
            )

            expected = ReminderSettings(
                inactive_enabled=True,
                inactive_interval_minutes=2.5,
                active_enabled=True,
                active_interval_minutes=12,
                window_enabled=True,
                window_weekdays=(0, 2, 4),
                window_start="08:30",
                window_end="18:00",
                snooze_minutes=7.5,
                idle_enabled=True,
                idle_threshold_minutes=22.5,
            )
            assert client.get_configuration() == expected
            assert load_config(paths.config).reminder_settings == expected
            assert client.get_export_delimiter() == "|"
            assert load_config(paths.config).export_settings.delimiter == "|"
            assert "Settings saved and applied" in str(
                app.query_one("#message", Static).render()
            )
            assert app.query_one("#message", Static).has_class("message-success")

            original = paths.config.read_bytes()
            app.query_one("#active-reminder-minutes", Input).value = "0"
            app.query_one("#save-settings-button", Button).press()
            await _wait_for_ui(
                pilot,
                lambda: (
                    "positive finite number"
                    in str(app.query_one("#message", Static).render())
                ),
                "settings validation error was not shown",
            )
            assert "positive finite number" in str(
                app.query_one("#message", Static).render()
            )
            assert app.query_one("#message", Static).has_class("message-error")
            assert paths.config.read_bytes() == original
            assert client.get_configuration() == expected

        reopened = TimeTrackerApp(AgentClient(paths))
        async with reopened.run_test() as pilot:
            await pilot.press("f4")
            await pilot.pause()
            assert reopened.theme == "nord"
            assert reopened.query_one("#inactive-reminder-minutes", Input).value == (
                "2.5"
            )
            assert reopened.query_one("#active-reminder-minutes", Input).value == "12"
            assert (
                reopened.query_one("#reminder-window-weekdays", Input).value
                == "Mon,Wed,Fri"
            )
            assert reopened.query_one("#reminder-snooze-minutes", Input).value == "7.5"
            assert reopened.query_one("#idle-reminders-enabled", Switch).value is True
            assert reopened.query_one("#idle-reminder-minutes", Input).value == "22.5"
            assert reopened.query_one("#export-delimiter", Select).value == "|"
            assert "Idle detection:" in str(
                reopened.query_one("#idle-status", Static).render()
            )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_selects_a_color_palette_in_settings(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.press("f4")
            await pilot.pause()
            palette = app.query_one("#color-palette", Select)

            assert palette.value == "textual-dark"

            for available in sorted(app.available_themes):

                def palette_is_saved(expected: str = available) -> bool:
                    return app.theme == expected and app._saved_theme == expected

                palette.value = available
                await _wait_for_ui(
                    pilot,
                    palette_is_saved,
                    f"the {available} palette was not applied and persisted",
                )

            palette.value = "gruvbox"
            await _wait_for_ui(
                pilot,
                lambda: app.theme == "gruvbox" and app._saved_theme == "gruvbox",
                "the selected palette was not persisted",
            )
            assert app.theme == "gruvbox"
            assert load_config(paths.config).ui_settings.theme == "gruvbox"

            app.theme = "nord"
            await _wait_for_ui(
                pilot,
                lambda: palette.value == "nord" and app._saved_theme == "nord",
                "Settings did not follow a palette applied elsewhere",
            )
            assert client.get_theme() == "nord"

        reopened = TimeTrackerApp(AgentClient(paths))
        async with reopened.run_test() as pilot:
            await pilot.press("f4")
            await pilot.pause()
            assert reopened.theme == "nord"
            assert reopened.query_one("#color-palette", Select).value == "nord"
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_inactive_buttons_stay_legible_in_every_palette(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.start("Website", "Planning")
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            start_button = app.query_one("#start-button", Button)
            edit_button = app.query_one("#edit-active-button", Button)
            await _wait_for_ui(
                pilot,
                lambda: start_button.disabled and edit_button.disabled,
                "the recovered timer did not make Start and Update inactive",
            )
            stop_button = app.query_one("#stop-button", Button)
            assert start_button.region.height == stop_button.region.height
            assert "No note" in str(app.query_one("#active-timer", Static).render())

            for palette in sorted(app.available_themes):
                app.theme = palette
                await pilot.pause()
                for button in (start_button, edit_button):
                    ratio = _contrast_ratio(button)
                    assert ratio is None or ratio >= 4.5, (
                        f"{button.id} is unreadable in {palette}: {ratio}"
                    )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_manage_trees_use_the_available_terminal_height(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.start("Website", "Planning")
        client.stop()
        client.archive_activity("Website", "Planning")
        for size, minimum, maximum in (((80, 40), 12, 40), ((80, 24), 1, 8)):
            app = TimeTrackerApp(client)
            async with app.run_test(size=size) as pilot:
                await pilot.press("f3")
                await pilot.pause()
                for selector in ("#active-targets", "#archived-targets"):
                    rows = app.query_one(selector, Tree).content_region.height
                    assert minimum <= rows <= maximum, f"{selector} at {size}: {rows}"
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_removed_persisted_theme_falls_back_safely(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    TomlConfigurationStore(paths.config).save(
        ApplicationConfig(ui_settings=UiSettings("removed-theme"))
    )
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await _wait_for_ui(
                pilot,
                lambda: client.get_theme() == "textual-dark",
                "fallback theme was not made durable",
            )
            assert app.theme == "textual-dark"
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def _wait_until_ready(client: AgentClient) -> None:
    # Windows agents build the WinRT notification backend before opening their
    # endpoint, so a slow host needs noticeably longer than a local Linux one.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            client.ping()
            return
        except AgentUnavailableError:
            time.sleep(0.01)
    _stop_late_agent(client)
    raise AssertionError("agent did not start")


def _stop_late_agent(client: AgentClient) -> None:
    """Stop an agent that answered too late to keep its test.

    A caller that never reaches its own cleanup would otherwise leave the agent
    blocked in `accept`. That call occupies a default-executor thread, which is
    not a daemon and is joined at interpreter shutdown, so one abandoned agent
    hangs the whole session after pytest has already reported its result.
    """
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.shutdown()
        except AgentUnavailableError:
            time.sleep(0.05)
        else:
            return


def _contrast_ratio(widget: Widget) -> float | None:
    """Return the WCAG contrast ratio of one widget's rendered label.

    ANSI palettes leave the concrete colors to the terminal, so their ratio is
    unknowable here and reported as None.
    """
    style = widget.rich_style
    foreground = None if style.color is None else style.color.triplet
    background = None if style.bgcolor is None else style.bgcolor.triplet
    if foreground is None or background is None:
        return None
    darker, lighter = sorted(
        (_relative_luminance(foreground), _relative_luminance(background))
    )
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(triplet: ColorTriplet) -> float:
    red, green, blue = (_linear_channel(value) for value in triplet)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _linear_channel(value: int) -> float:
    channel = value / 255
    if channel <= 0.03928:
        return channel / 12.92
    return float(((channel + 0.055) / 1.055) ** 2.4)


async def _wait_for_ui(
    pilot: Pilot[None],
    condition: Callable[[], bool],
    failure: str,
) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if condition():
            return
        await pilot.pause(0.01)
    raise AssertionError(failure)


def _wait_for_pending_reminder(
    client: AgentClient,
    kind: ReminderKind,
) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        reminder = client.get_reminder()
        if reminder is not None and reminder.kind is kind:
            return
        time.sleep(0.01)
    raise AssertionError(f"{kind.value} reminder was not exposed over IPC")
