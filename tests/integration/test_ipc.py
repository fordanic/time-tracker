from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from time_tracker.agent.server import serve
from time_tracker.infrastructure.instance_lock import (
    AgentAlreadyRunningError,
    instance_lock,
)
from time_tracker.infrastructure.ipc import (
    AgentClient,
    AgentUnavailableError,
    ensure_agent_running,
)
from time_tracker.infrastructure.paths import AgentPaths


def test_authenticated_json_ipc_persists_and_recovers_active_timer(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        started = client.start("Website", "Implementation", "Through IPC")

        assert client.list_projects() == ["Website"]
        assert client.list_activities("website") == ["Implementation"]

        reconnected_client = AgentClient(paths)
        assert reconnected_client.get_active() == started
        completed = reconnected_client.stop()
        assert completed is not None
        assert completed.entry_id == started.entry_id
        assert reconnected_client.get_active() is None
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


def test_instance_lock_rejects_a_second_agent(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)

    with instance_lock(paths.lock):
        with pytest.raises(AgentAlreadyRunningError):
            with instance_lock(paths.lock):
                raise AssertionError("the second process lock was acquired")


def test_agent_can_start_as_a_separate_process(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    client = ensure_agent_running(paths)

    try:
        started = client.start("Process test", "Persist", None)
        assert AgentClient(paths).get_active() == started
    finally:
        client.shutdown()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            client.ping()
        except AgentUnavailableError:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("agent process did not stop")
