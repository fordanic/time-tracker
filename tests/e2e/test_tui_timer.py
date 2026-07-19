from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from time_tracker.agent.server import serve
from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository
from time_tracker.tui.app import TimeTrackerApp


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

        assert SQLiteTimerRepository(paths.database).get_active() is None
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
