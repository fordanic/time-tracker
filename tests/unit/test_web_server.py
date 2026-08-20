from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from starlette.testclient import TestClient

from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.web import server as web_server
from time_tracker.web.api import WebAgent
from time_tracker.web.server import (
    MAX_JSON_BODY_BYTES,
    WebServerSettings,
    create_web_app,
)

PORT = 48123
ORIGIN = f"http://127.0.0.1:{PORT}"
TOKEN = "test-launch-token"


class ReadyServer:
    started = True
    should_exit = False


class FakeAgent:
    def __init__(self) -> None:
        self.active: ActiveTimer | None = ActiveTimer(
            entry_id=7,
            project="Project",
            activity="Activity",
            started_at=datetime(2026, 8, 12, 8, tzinfo=UTC),
            note="Focused work",
        )
        self.stop_calls = 0

    def ping(self) -> None:
        return None

    def get_active(self) -> ActiveTimer | None:
        return self.active

    def get_reminder(self) -> None:
        return None

    def stop(self) -> CompletedTimer | None:
        self.stop_calls += 1
        active = self.active
        if active is None:
            return None
        self.active = None
        return active.stop(datetime(2026, 8, 12, 9, tzinfo=UTC))


@pytest.fixture
def agent() -> FakeAgent:
    return FakeAgent()


@pytest.fixture
def client(agent: FakeAgent) -> TestClient:
    app = create_web_app(
        cast(WebAgent, agent), WebServerSettings(port=PORT), token=TOKEN
    )
    return TestClient(app, base_url=ORIGIN)


def mutation_headers(**replacements: str) -> dict[str, str]:
    headers = {
        "Origin": ORIGIN,
        "X-Time-Tracker-Token": TOKEN,
        "Content-Type": "application/json",
    }
    headers.update(replacements)
    return headers


def test_index_embeds_launch_token_and_security_headers(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert f'content="{TOKEN}"' in response.text
    assert "__TIME_TRACKER_TOKEN__" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "access-control-allow-origin" not in response.headers

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.headers["content-type"].split(";", 1)[0] in {
        "application/javascript",
        "text/javascript",
    }


def test_state_returns_authoritative_timer(client: TestClient) -> None:
    response = client.get("/api/state")

    assert response.status_code == 200
    assert response.json()["data"]["active"] == {
        "entry_id": 7,
        "project": "Project",
        "activity": "Activity",
        "started_at": "2026-08-12T08:00:00+00:00",
        "note": "Focused work",
    }


def test_mutation_requires_origin_token_and_json(
    client: TestClient, agent: FakeAgent
) -> None:
    assert client.post("/api/timer/stop", json={}).status_code == 403
    assert (
        client.post(
            "/api/timer/stop",
            content="{}",
            headers=mutation_headers(Origin="http://example.test"),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/timer/stop",
            content="{}",
            headers=mutation_headers(**{"X-Time-Tracker-Token": "wrong"}),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/timer/stop",
            content="plain text",
            headers={
                "Origin": ORIGIN,
                "X-Time-Tracker-Token": TOKEN,
                "Content-Type": "text/plain",
            },
        ).status_code
        == 415
    )
    assert agent.stop_calls == 0


def test_mutation_rejects_invalid_or_oversized_json(
    client: TestClient, agent: FakeAgent
) -> None:
    invalid = client.post(
        "/api/timer/stop", content="not-json", headers=mutation_headers()
    )
    oversized = client.post(
        "/api/timer/stop",
        content=b"{" + b'"padding":"' + b"x" * MAX_JSON_BODY_BYTES + b'"}',
        headers=mutation_headers(),
    )

    assert invalid.status_code == 400
    assert oversized.status_code == 413
    assert agent.stop_calls == 0


def test_valid_mutation_is_durable_response_and_has_no_get_route(
    client: TestClient, agent: FakeAgent
) -> None:
    response = client.post("/api/timer/stop", content="{}", headers=mutation_headers())

    assert response.status_code == 200
    assert response.json()["data"]["completed"]["stopped_at"] == (
        "2026-08-12T09:00:00+00:00"
    )
    assert agent.stop_calls == 1
    assert client.get("/api/timer/stop").status_code == 405


def test_unexpected_host_is_rejected(client: TestClient) -> None:
    response = client.get("/api/state", headers={"Host": "localhost:48123"})

    assert response.status_code == 400


def test_non_loopback_binding_is_rejected() -> None:
    with pytest.raises(ValueError, match="only to 127.0.0.1"):
        WebServerSettings(port=PORT, host="0.0.0.0")


def test_no_open_prints_the_ready_url_without_calling_a_browser(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_browser(_url: str) -> bool:
        raise AssertionError("--no-open must skip the browser adapter")

    monkeypatch.setattr(web_server, "open_default_browser", reject_browser)

    web_server._announce_ready(cast(Any, ReadyServer()), ORIGIN, False)

    assert capsys.readouterr().out == f"Time Tracker web interface: {ORIGIN}\n"


def test_browser_failure_prints_the_ready_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(web_server, "open_default_browser", lambda _url: False)

    web_server._announce_ready(cast(Any, ReadyServer()), ORIGIN, True)

    assert capsys.readouterr().out == f"Time Tracker web interface: {ORIGIN}\n"
