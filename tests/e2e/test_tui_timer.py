from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from textual.widgets import Button, DataTable, Input, Static

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
            first_app.query_one("#project", Input).value = "Website"
            first_app.query_one("#activity", Input).value = "Implementation"
            first_app.query_one("#note", Input).value = "Walking skeleton"
            await pilot.click("#start-button")
            await pilot.pause()

            active_text = str(first_app.query_one("#active-timer", Static).render())
            assert "Website / Implementation" in active_text
            assert "Walking skeleton" in active_text

        recovered_app = TimeTrackerApp(AgentClient(paths))
        async with recovered_app.run_test() as pilot:
            await pilot.pause()
            recovered_text = str(
                recovered_app.query_one("#active-timer", Static).render()
            )
            assert "Website / Implementation" in recovered_text

            await pilot.click("#project")
            await pilot.press("w", "e", "b", "right")
            await pilot.pause()
            assert recovered_app.query_one("#project", Input).value == "Website"

            await pilot.click("#activity")
            await pilot.press("i", "m", "p", "right")
            await pilot.pause()
            assert recovered_app.query_one("#activity", Input).value == "Implementation"

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

            destination = tmp_path / "tui-export.csv"
            destination.write_text("existing content", encoding="utf-8")
            recovered_app.query_one("#export-path", Input).value = str(destination)
            assert await pilot.click("#export-button")
            await pilot.pause()

            export_button = recovered_app.query_one("#export-button", Button)
            assert "Overwrite CSV" in str(export_button.label)
            assert destination.read_text(encoding="utf-8") == "existing content"

            await pilot.press("f7")
            await pilot.pause()

            assert "Export CSV" in str(export_button.label)
            assert "Exported 1 entry" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert "Website,Implementation" in destination.read_text(encoding="utf-8")

            await pilot.click("#archive-activity-button")
            await pilot.pause()

            assert recovered_app.query_one("#activity", Input).value == ""
            assert "Archived activity Website / Implementation" in str(
                recovered_app.query_one("#message", Static).render()
            )
            recovered_app.query_one("#activity", Input).value = "Implementation"
            await pilot.click("#start-button")
            await pilot.pause()

            assert "activity is archived: Implementation" in str(
                recovered_app.query_one("#message", Static).render()
            )
            assert "No timer running" in str(
                recovered_app.query_one("#active-timer", Static).render()
            )
            assert history.row_count == 1

            await pilot.click("#archive-project-button")
            await pilot.pause()

            assert recovered_app.query_one("#project", Input).value == ""
            assert recovered_app.query_one("#activity", Input).value == ""
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
