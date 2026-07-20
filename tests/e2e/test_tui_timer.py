from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Input,
    OptionList,
    Static,
    Switch,
    Tabs,
)

from time_tracker.agent.server import serve
from time_tracker.application.reminders import Reminder, ReminderIntervals, ReminderKind
from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository
from time_tracker.tui.app import TimeTrackerApp


class SilentNotifier:
    async def send(self, reminder: Reminder) -> None:
        """Accept test reminders without contacting the host desktop."""


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
            assert history.row_count == 1
            row = history.get_row_at(0)
            assert row[0] == "Website"
            assert row[1] == "Implementation"
            assert row[5] == "Walking skeleton"

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

            assert recovered_app.query_one("#manage-activity", Input).value == ""
            assert "Archived activity Website / Implementation" in str(
                recovered_app.query_one("#message", Static).render()
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

            assert recovered_app.query_one("#manage-project", Input).value == ""
            assert "Archived project Website" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert client.list_projects() == []

        assert SQLiteTimerRepository(paths.database).get_active() is None
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_user_confirms_an_active_reminder_from_the_tui(tmp_path: Path) -> None:
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
        started = client.start("Reminder", "Interaction")
        _wait_for_pending_reminder(client, ReminderKind.ACTIVE)

        app = TimeTrackerApp(client)
        async with app.run_test() as pilot:
            await pilot.pause()
            prompt = str(app.query_one("#reminder-message", Static).render())
            assert "Still tracking Reminder / Interaction?" in prompt

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
            assert tabs.has_focus
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


def _wait_until_ready(client: AgentClient) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            client.ping()
            return
        except AgentUnavailableError:
            time.sleep(0.01)
    raise AssertionError("agent did not start")


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
