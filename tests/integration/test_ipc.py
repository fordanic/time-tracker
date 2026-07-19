from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest

from time_tracker.agent.server import serve
from time_tracker.application.reminders import Reminder, ReminderIntervals, ReminderKind
from time_tracker.infrastructure.instance_lock import (
    AgentAlreadyRunningError,
    instance_lock,
)
from time_tracker.infrastructure.ipc import (
    AgentClient,
    AgentUnavailableError,
    _agent_command,
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


def test_active_timer_recovers_after_agent_process_is_killed(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    process = subprocess.Popen(  # noqa: S603
        _agent_command(paths),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        started = client.start("Crash test", "Recovery", "Must remain open")
        process.kill()
        process.wait(timeout=5)
        _wait_until_unavailable(client)

        recovered_client = ensure_agent_running(paths)
        assert recovered_client.get_active() == started
        completed = recovered_client.stop()
        assert completed is not None
        assert completed.entry_id == started.entry_id
        recovered_client.shutdown()
        _wait_until_unavailable(recovered_client)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


class RecordingNotifier:
    def __init__(self) -> None:
        self.reminders: list[Reminder] = []

    async def send(self, reminder: Reminder) -> None:
        self.reminders.append(reminder)


class FailingNotifier:
    def __init__(self) -> None:
        self.attempts = 0

    async def send(self, reminder: Reminder) -> None:
        self.attempts += 1
        raise RuntimeError(f"simulated {reminder.kind.value} delivery failure")


def test_agent_sends_reminders_after_the_tui_disconnects(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    notifier = RecordingNotifier()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": notifier,
            "reminder_intervals": ReminderIntervals(inactive=0.05, active=0.05),
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        # There is no persistent client connection while the scheduler fires.
        _wait_for_reminder(notifier, ReminderKind.INACTIVE)
        before_smoke = len(notifier.reminders)
        client.send_test_notification()
        assert len(notifier.reminders) == before_smoke + 1
        assert notifier.reminders[-1].kind is ReminderKind.INACTIVE
        started = client.start("Background", "Notifications")
        _wait_for_reminder(notifier, ReminderKind.ACTIVE)
        assert AgentClient(paths).get_active() == started
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_notification_failure_is_logged_without_stopping_agent(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    notifier = FailingNotifier()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": notifier,
            "reminder_intervals": ReminderIntervals(inactive=0.05),
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        deadline = time.monotonic() + 2
        while notifier.attempts == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert notifier.attempts > 0
        client.ping()
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert "native reminder delivery failed" in paths.log.read_text(encoding="utf-8")


def _wait_until_unavailable(client: AgentClient) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.ping()
        except AgentUnavailableError:
            return
        time.sleep(0.01)
    raise AssertionError("agent remained available")


def _wait_for_reminder(
    notifier: RecordingNotifier,
    kind: ReminderKind,
) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if any(reminder.kind is kind for reminder in notifier.reminders):
            return
        time.sleep(0.01)
    raise AssertionError(f"{kind.value} reminder was not delivered")
