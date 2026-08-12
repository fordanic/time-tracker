"""Run a disposable real-agent web server for browser and Playwright tests."""

from __future__ import annotations

import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from time_tracker.agent.server import serve
from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.web.server import run_web_server

PORT = 48125


def _wait_until_ready(client: AgentClient) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            client.ping()
            return
        except AgentUnavailableError:
            time.sleep(0.01)
    raise RuntimeError("fixture agent did not start")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="time-tracker-web-") as directory:
        paths = AgentPaths.in_directory(Path(directory))
        thread = threading.Thread(target=serve, args=(paths,), daemon=True)
        thread.start()
        client = AgentClient(paths)
        _wait_until_ready(client)
        now = datetime.now(UTC)
        client.create_project("Launch work")
        client.create_activity("Launch work", "Web GUI")
        client.create_activity("Launch work", "Documentation")
        client.create_manual_entry(
            "Launch work",
            "Documentation",
            now - timedelta(hours=3),
            now - timedelta(hours=2, minutes=12),
            "Implementation plan",
        )
        client.create_manual_entry(
            "Launch work",
            "Web GUI",
            now - timedelta(hours=2),
            now - timedelta(hours=1, minutes=5),
            "Responsive shell",
        )
        client.start("Launch work", "Web GUI", "Browser validation")
        try:
            run_web_server(client, port=PORT, open_browser=False)
        finally:
            client.shutdown()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
