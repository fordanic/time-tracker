"""Headless packaged lifecycle validation invoked by the frozen executable."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen

import uvicorn
from textual.widgets import Input

from time_tracker.domain.models import ActiveTimer
from time_tracker.infrastructure.ipc import (
    AgentClient,
    AgentUnavailableError,
    ensure_agent_running,
)
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.tui.app import TimeTrackerApp
from time_tracker.web.server import WebServerSettings, create_web_app


async def run_packaged_lifecycle(directory: Path) -> None:
    """Start, disconnect, recover, and stop through two packaged TUI sessions."""
    paths = AgentPaths.in_directory(directory)
    client = ensure_agent_running(paths)
    try:
        first_app = TimeTrackerApp(client)
        async with first_app.run_test() as pilot:
            first_app.query_one("#project", Input).value = "Packaged smoke"
            first_app.query_one("#activity", Input).value = "Lifecycle"
            await pilot.press("f5")
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
            await pilot.press("f6")
            await _wait_for_active(second_app)
            if second_app.active_timer is not None:
                raise RuntimeError("the packaged TUI did not stop the recovered timer")
            # The model becomes inactive before the handler's awaited history refresh.
            # Keep the screen mounted until Textual has finished that message.
            await pilot.pause()

        await asyncio.to_thread(_run_web_lifecycle, AgentClient(paths))
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


def _run_web_lifecycle(client: AgentClient) -> None:
    """Load embedded assets, persist through server close, recover, and stop."""
    port = _available_loopback_port()
    settings = WebServerSettings(port=port)
    first_token = "packaged-web-smoke-first"
    first_server, first_thread = _start_web_server(client, settings, first_token)
    try:
        index = _http_text(settings.origin)
        if first_token not in index or "/assets/app.js" not in index:
            raise RuntimeError("the packaged web shell did not load embedded assets")
        asset = _http_text(f"{settings.origin}/assets/app.js")
        if "Time Tracker" not in asset:
            raise RuntimeError("the packaged web JavaScript asset was malformed")
        started = _object_dict(
            _http_json(
                f"{settings.origin}/api/timer/start",
                first_token,
                {
                    "project": "Packaged smoke",
                    "activity": "Lifecycle",
                    "note": "Web recovery",
                },
            ).get("data")
        ).get("active")
    finally:
        _stop_web_server(first_server, first_thread)

    if client.get_active() is None:
        raise RuntimeError("closing the packaged web server stopped the timer")

    second_token = "packaged-web-smoke-second"
    second_server, second_thread = _start_web_server(client, settings, second_token)
    try:
        state = _http_json(f"{settings.origin}/api/state")
        if _object_dict(state.get("data")).get("active") != started:
            raise RuntimeError("the packaged web server did not recover the timer")
        _http_json(
            f"{settings.origin}/api/timer/stop",
            second_token,
            {},
        )
    finally:
        _stop_web_server(second_server, second_thread)

    if client.get_active() is not None:
        raise RuntimeError("the packaged web server did not stop the recovered timer")


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _start_web_server(
    client: AgentClient,
    settings: WebServerSettings,
    token: str,
) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(
        uvicorn.Config(
            create_web_app(client, settings, token=token),
            host=settings.host,
            port=settings.port,
            access_log=False,
            log_level="warning",
            server_header=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if server.started:
            return server, thread
        if not thread.is_alive():
            break
        time.sleep(0.01)
    raise RuntimeError("the packaged web server did not start")


def _stop_web_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)
    if thread.is_alive():
        raise RuntimeError("the packaged web server did not stop")


def _http_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:  # noqa: S310
        return cast(bytes, response.read()).decode("utf-8")


def _http_json(
    url: str,
    token: str | None = None,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        origin = url.split("/api/", 1)[0]
        headers.update(
            {
                "Content-Type": "application/json",
                "Origin": origin,
                "X-Time-Tracker-Token": token or "",
            }
        )
    with urlopen(Request(url, data=data, headers=headers), timeout=5) as response:  # noqa: S310
        decoded: object = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("the packaged web server returned malformed JSON")
    return cast(dict[str, object], decoded)


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("the packaged web server returned malformed JSON data")
    return cast(dict[str, object], value)
