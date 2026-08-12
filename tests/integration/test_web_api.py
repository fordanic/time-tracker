from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from starlette.testclient import TestClient

from time_tracker.agent.server import serve
from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.web.server import WebServerSettings, create_web_app

PORT = 48124
ORIGIN = f"http://127.0.0.1:{PORT}"
TOKEN = "integration-launch-token"


def _headers() -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "X-Time-Tracker-Token": TOKEN,
        "Content-Type": "application/json",
    }


def _wait_until_ready(client: AgentClient) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            client.ping()
            return
        except AgentUnavailableError:
            time.sleep(0.01)
    raise AssertionError("agent did not start")


def test_web_api_round_trips_all_four_workflows(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    agent = AgentClient(paths)
    _wait_until_ready(agent)
    client = TestClient(
        create_web_app(agent, WebServerSettings(port=PORT), token=TOKEN),
        base_url=ORIGIN,
    )
    try:
        create_project = client.post(
            "/api/manage/create-project",
            json={"project": "Client"},
            headers=_headers(),
        )
        create_activity = client.post(
            "/api/manage/create-activity",
            json={"project": "Client", "activity": "Build"},
            headers=_headers(),
        )
        assert create_project.json()["data"] == {"project": "Client"}
        assert create_activity.json()["data"] == {
            "project": "Client",
            "activity": "Build",
        }

        classified = client.post(
            "/api/track/classify",
            json={
                "project": "Client",
                "activity": "Build",
                "note": "Web work",
                "quick": False,
            },
            headers=_headers(),
        )
        started = client.post(
            "/api/timer/start",
            json={
                "project": "Client",
                "activity": "Build",
                "note": "Web work",
            },
            headers=_headers(),
        )
        assert classified.json()["data"]["action"] == "start"
        assert started.json()["data"]["active"]["note"] == "Web work"
        current_quick_switch = client.post(
            "/api/track/classify",
            json={
                "project": "Client",
                "activity": "Build",
                "note": "A quick note must not restart current work",
                "quick": True,
            },
            headers=_headers(),
        )
        assert current_quick_switch.json()["data"]["action"] == "already_tracking"

        updated = client.post(
            "/api/timer/edit",
            json={
                "project": "Client",
                "activity": "Build",
                "note": "Updated without restart",
            },
            headers=_headers(),
        )
        assert (
            updated.json()["data"]["active"]["started_at"]
            == (started.json()["data"]["active"]["started_at"])
        )
        client.post("/api/timer/stop", json={}, headers=_headers()).raise_for_status()

        now = datetime.now(UTC)
        manual = client.post(
            "/api/review/create",
            json={
                "project": "Client",
                "activity": "Build",
                "started_at": (now - timedelta(hours=2)).isoformat(),
                "stopped_at": (now - timedelta(hours=1)).isoformat(),
                "note": "Missed",
            },
            headers=_headers(),
        )
        entry_id = manual.json()["data"]["entry"]["entry_id"]
        corrected = client.post(
            "/api/review/correct",
            json={
                "entry_id": entry_id,
                "project": "Client",
                "activity": "Build",
                "started_at": (now - timedelta(hours=2)).isoformat(),
                "stopped_at": (now - timedelta(minutes=45)).isoformat(),
                "note": "Corrected",
            },
            headers=_headers(),
        )
        assert corrected.json()["data"]["entry"]["note"] == "Corrected"
        review = client.post(
            "/api/review/query",
            json={
                "preset": "all_time",
                "start_date": None,
                "end_date": None,
                "project": "Client",
                "activity": "Build",
            },
            headers=_headers(),
        )
        assert review.status_code == 200
        assert review.json()["data"]["groups"]
        assert review.json()["data"]["daily_summaries"]
        assert review.json()["data"]["range_summaries"]

        bootstrap = client.get("/api/bootstrap")
        assert bootstrap.status_code == 200
        settings = bootstrap.json()["data"]["settings"]
        settings["inactive_interval_minutes"] = 7.5
        saved = client.post(
            "/api/settings",
            json={**settings, "export_delimiter": "|"},
            headers=_headers(),
        )
        assert saved.json()["data"]["settings"]["inactive_interval_minutes"] == 7.5
        assert saved.json()["data"]["export_delimiter"] == "|"

        target = client.post(
            "/api/manage/archive-activity-target",
            json={"project": "Client", "activity": "Build"},
            headers=_headers(),
        )
        assert target.json()["data"] == {
            "project": "Client",
            "activity": "Build",
        }
        client.post(
            "/api/manage/archive-activity",
            json={"project": "Client", "activity": "Build"},
            headers=_headers(),
        ).raise_for_status()
        restored = client.post(
            "/api/manage/unarchive-activity",
            json={"project": "Client", "activity": "Build"},
            headers=_headers(),
        )
        assert restored.status_code == 200
    finally:
        agent.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_web_api_returns_stable_field_error(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    agent = AgentClient(paths)
    _wait_until_ready(agent)
    client = TestClient(
        create_web_app(agent, WebServerSettings(port=PORT), token=TOKEN),
        base_url=ORIGIN,
    )
    try:
        response = client.post(
            "/api/timer/start",
            json={"project": 1, "activity": "Build"},
            headers=_headers(),
        )
        assert response.status_code == 400
        assert response.json() == {
            "error": {
                "code": "invalid_field",
                "message": "must be text",
                "field": "project",
            }
        }
    finally:
        agent.shutdown()
        thread.join(timeout=2)
