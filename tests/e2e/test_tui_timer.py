from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from textual.pilot import Pilot
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
)

from time_tracker.agent.server import serve
from time_tracker.application.configuration import ReminderSettings
from time_tracker.application.reminders import Reminder, ReminderIntervals, ReminderKind
from time_tracker.application.tracking import RecentActivity
from time_tracker.infrastructure.configuration import load_config
from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository
from time_tracker.tui.app import TimeTrackerApp


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
            assert (
                first_app.query_one("#archived-projects", OptionList).option_count == 0
            )
            assert first_app.query_one("#archived-projects-empty", Static).display
            assert (
                first_app.query_one("#archived-activities", OptionList).option_count
                == 0
            )
            assert first_app.query_one("#archived-activities-empty", Static).display
            project_input = first_app.query_one("#project", Input)
            first_app.set_focus(project_input)
            await pilot.press("tab")
            assert first_app.focused is first_app.query_one("#activity", Input)
            await pilot.press("tab")
            assert first_app.focused is first_app.query_one("#note", Input)

            project_input.value = "Website"
            first_app.query_one("#activity", Input).value = "Implementation"
            first_app.query_one("#note", Input).value = "Walking skeleton"
            await pilot.click("#start-button")
            await pilot.pause()

            active_text = str(first_app.query_one("#active-timer", Static).render())
            assert "Website / Implementation" in active_text
            assert "Walking skeleton" in active_text

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
            assert recovered_app.query_one("#note", Input).value == "Walking skeleton"
            recovered_start = recovered_app.query_one("#start-button", Button)
            assert str(recovered_start.label) == "Already tracking"
            assert recovered_start.disabled is True

            await pilot.click("#stop-button")
            await pilot.pause()

            assert "No timer running" in str(
                recovered_app.query_one("#active-timer", Static).render()
            )
            history = recovered_app.query_one("#history", DataTable)
            assert history.row_count == 2
            row = history.get_row_at(0)
            assert row[1] == "Website"
            assert row[2] == "Implementation"
            assert row[6] == "Walking skeleton"
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
            recovered_app.query_one("#manage-project", Input).value = "Website"
            recovered_app.query_one("#manage-activity", Input).value = "Implementation"
            await pilot.pause()
            await pilot.click("#archive-activity-button")
            await pilot.pause()

            assert (
                recovered_app.query_one("#manage-activity", Input).value
                == "Implementation"
            )
            assert "Any active timer will continue" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_activities("Website") == ["Implementation"]

            await pilot.press("f9")
            await pilot.pause()

            assert recovered_app.query_one("#manage-activity", Input).value == ""
            assert "Archived activity Website / Implementation" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert (
                recovered_app.query_one("#archived-activities", OptionList).option_count
                == 1
            )
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

            recovered_app.query_one("#manage-project", Input).value = "Website"
            await pilot.press("f4")
            await pilot.press("f8")
            await pilot.pause()

            assert recovered_app.query_one("#manage-project", Input).value == "Website"
            assert client.list_projects() == ["Website"]
            recovered_app.query_one("#manage-project", Input).value = "website"
            await pilot.pause()
            await pilot.press("f8")
            await pilot.pause()

            assert client.list_projects() == ["Website"]
            assert "Press Archive project again" in str(
                recovered_app.query_one("#message", Static).render()
            )
            await pilot.press("f8")
            await pilot.pause()

            assert recovered_app.query_one("#manage-project", Input).value == ""
            assert "Archived project Website" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_projects() == []
            assert "restore project first" in str(
                recovered_app.query_one("#archived-activities", OptionList)
                .get_option_at_index(0)
                .prompt
            )

            await pilot.press("f3")
            restore_activity = recovered_app.query_one(
                "#restore-activity-button", Button
            )
            restore_activity.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert "restore project first" in str(
                recovered_app.query_one("#message", Static).render()
            )

            restore_project = recovered_app.query_one("#restore-project-button", Button)
            restore_project.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert "Restored project Website" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_projects() == ["Website"]
            assert client.list_activities("Website") == []

            restore_activity.focus()
            await pilot.press("enter")
            await pilot.pause()
            assert "Restored activity Website / Implementation" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_activities("Website") == ["Implementation"]

        assert SQLiteTimerRepository(paths.database).get_active() is None
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
            app.query_one("#manage-project", Input).value = "Website"
            app.query_one("#manage-activity", Input).value = "Planning"
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
            assert str(app.query_one("#archive-activity-button", Button).label) == (
                "Archive activity  F9"
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
            await pilot.pause()

            assert "Reminder snoozed" in str(app.query_one("#message", Static).render())
            assert app.pending_reminder is None
            assert client.get_active() == started

            _wait_for_pending_reminder(client, ReminderKind.ACTIVE)
            await app._refresh_reminder()
            await pilot.pause()
            assert await pilot.click("#confirm-active-reminder-button")
            await pilot.pause()

            assert "interval restarted" in str(
                app.query_one("#message", Static).render()
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
            await pilot.pause()

            assert app.pending_reminder is None
            assert client.get_active() == started
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_tracks_again_from_recent_activities(tmp_path: Path) -> None:
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
            assert "Website / Implementation" in str(
                recent.get_option_at_index(0).prompt
            )

            app.query_one("#project", Input).value = "Temporary"
            app.query_one("#activity", Input).value = "Draft"
            app.query_one("#note", Input).value = "Do not preserve this"
            app.set_focus(recent)
            await pilot.press("enter")
            await pilot.pause()

            assert app.query_one("#project", Input).value == "Website"
            assert app.query_one("#activity", Input).value == "Implementation"
            assert app.query_one("#note", Input).value == ""
            assert app.focused is app.query_one("#note", Input)
            assert client.get_active() is None

            await pilot.press("f5")
            await pilot.pause()

            active = client.get_active()
            assert active is not None
            assert active.project == "Website"
            assert active.activity == "Implementation"
            assert active.note is None

            await pilot.press("f6")
            await pilot.pause()

            assert app._recent_activities[0].activity == "Implementation"
            await pilot.press("f3")
            app.query_one("#manage-project", Input).value = "Website"
            app.query_one("#manage-activity", Input).value = "Implementation"
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
            assert app.focused is app.query_one("#manage-project", Input)
            app.query_one("#manage-project", Input).value = "Website"
            app.query_one("#manage-activity", Input).value = "Review"

            await pilot.press("f4")
            assert tabs.active == "settings-tab"
            assert switcher.current == "settings-view"
            assert app.query_one("#inactive-reminders-enabled", Switch).has_focus
            assert "Website / Review" in str(active.render())

            await pilot.press("f1")
            assert app.query_one("#note", Input).value == "Draft replacement"
            await pilot.press("f2")
            assert app.query_one("#export-path", Input).value.endswith("review.csv")
            assert app.query_one("#summary-mode", Switch).value is True
            await pilot.press("f3")
            assert app.query_one("#manage-project", Input).value == "Website"
            assert app.query_one("#manage-activity", Input).value == "Review"
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
            assert str(start_button.label) == "Start  F5"
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
            history = app.query_one("#history", DataTable)

            assert history.row_count == 5
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
                "00:30:00",
                "Across midnight",
            ]
            assert history.get_row_at(1)[1] == "Day total"

            second_segment = history.get_row_at(2)
            assert second_segment[0] == local_midnight.date().isoformat()
            assert second_segment[3:6] == ["00:00", "00:30", "00:30:00"]
            assert history.get_row_at(3)[0] == ""
            assert history.get_row_at(4)[1] == "Day total"
            assert history.get_row_at(4)[5] == "01:15:00"
            assert "Today's completed time: 01:15:00" in str(
                app.query_one("#today-total", Static).render()
            )

            history.move_cursor(row=2)
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

            history.move_cursor(row=4)
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
            app.query_one("#filter-project", Input).value = "client"
            await pilot.pause()

            history = app.query_one("#history", DataTable)
            assert history.row_count == 3
            assert history.get_row_at(0)[0] == "2026-07-20"
            assert history.get_row_at(0)[1:3] == ["Client", "Research"]
            assert history.get_row_at(1)[1:3] == ["Client", "Writing"]
            assert history.get_row_at(2)[1] == "Day total"
            assert "2026-07-20 · client · all activities" in str(
                app.query_one("#active-filter", Static).render()
            )

            range_switch = app.query_one("#range-summary-mode", Switch)
            range_switch.focus()
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()

            assert range_switch.value is True
            assert history.row_count == 2
            assert history.get_row_at(0) == ["Client", "Research", "00:30:00"]
            assert history.get_row_at(1) == ["Client", "Writing", "01:00:00"]
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
            app.query_one("#filter-activity", Input).value = "Missing"
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
            assert app.query_one("#inactive-reminder-minutes", Input).value == "5"

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
            app.query_one("#save-settings-button", Button).press()
            await pilot.pause()

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
            assert "Reminder settings saved and applied" in str(
                app.query_one("#message", Static).render()
            )

            original = paths.config.read_bytes()
            app.query_one("#active-reminder-minutes", Input).value = "0"
            app.query_one("#save-settings-button", Button).press()
            await pilot.pause()
            assert "positive finite number" in str(
                app.query_one("#message", Static).render()
            )
            assert paths.config.read_bytes() == original
            assert client.get_configuration() == expected

        reopened = TimeTrackerApp(AgentClient(paths))
        async with reopened.run_test() as pilot:
            await pilot.press("f4")
            await pilot.pause()
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
            assert "Idle detection:" in str(
                reopened.query_one("#idle-status", Static).render()
            )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def _wait_until_ready(client: AgentClient) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            client.ping()
            return
        except AgentUnavailableError:
            time.sleep(0.01)
    raise AssertionError("agent did not start")


async def _wait_for_ui(
    pilot: Pilot[None],
    condition: Callable[[], bool],
    failure: str,
) -> None:
    deadline = time.monotonic() + 2
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
