"""Headless packaged lifecycle validation invoked by the frozen executable."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from textual.widgets import Input

from time_tracker.domain.models import ActiveTimer
from time_tracker.infrastructure.ipc import (
    AgentClient,
    AgentUnavailableError,
    ensure_agent_running,
)
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.tui.app import TimeTrackerApp


async def run_packaged_lifecycle(directory: Path) -> None:
    """Start, disconnect, recover, and stop through two packaged TUI sessions."""
    paths = AgentPaths.in_directory(directory)
    client = ensure_agent_running(paths)
    try:
        first_app = TimeTrackerApp(client)
        async with first_app.run_test() as pilot:
            first_app.query_one("#project", Input).value = "Packaged smoke"
            first_app.query_one("#activity", Input).value = "Lifecycle"
            await pilot.click("#start-button")
            await _wait_for_started(first_app)
            started = first_app.active_timer
            if started is None:
                raise RuntimeError("the packaged TUI did not start a timer")
            # The model becomes active before the handler's awaited suggestion refresh.
            # Keep the screen mounted until Textual has finished that message.
            await pilot.pause()

        # The first TUI is closed, but its background process must remain alive.
        AgentClient(paths).ping()

        second_app = TimeTrackerApp(AgentClient(paths))
        async with second_app.run_test() as pilot:
            await _wait_for_active(second_app, started)
            if second_app.active_timer != started:
                raise RuntimeError(
                    "the packaged TUI did not recover the active timer: "
                    f"expected {started!r}, got {second_app.active_timer!r}"
                )
            await pilot.click("#stop-button")
            await _wait_for_active(second_app)
            if second_app.active_timer is not None:
                raise RuntimeError("the packaged TUI did not stop the recovered timer")
            # The model becomes inactive before the handler's awaited history refresh.
            # Keep the screen mounted until Textual has finished that message.
            await pilot.pause()
    finally:
        try:
            client.shutdown()
        except AgentUnavailableError:
            pass
        else:
            _wait_until_stopped(client)


async def _wait_for_active(
    app: TimeTrackerApp,
    expected: ActiveTimer | None = None,
) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if app.active_timer == expected:
            return
        await asyncio.sleep(0.05)


async def _wait_for_started(app: TimeTrackerApp) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if app.active_timer is not None:
            return
        await asyncio.sleep(0.05)


def _wait_until_stopped(client: AgentClient) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.ping()
        except AgentUnavailableError:
            return
        time.sleep(0.05)
    raise RuntimeError("the packaged agent did not stop")
