from __future__ import annotations

import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from time_tracker.agent.server import serve
from time_tracker.application.configuration import ReminderSettings
from time_tracker.application.reminders import (
    Reminder,
    ReminderIntervals,
    ReminderKind,
    ReminderReason,
)
from time_tracker.application.reporting import ReviewFilter
from time_tracker.application.tracking import (
    ArchivedActivity,
    RecentActivity,
    StartAction,
)
from time_tracker.infrastructure.configuration import load_config
from time_tracker.infrastructure.instance_lock import (
    AgentAlreadyRunningError,
    instance_lock,
)
from time_tracker.infrastructure.ipc import (
    AgentClient,
    AgentRequestError,
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
        assert reconnected_client.list_completed() == [completed]
        assert reconnected_client.list_recent_activities() == [
            RecentActivity("Website", "Implementation")
        ]
        destination = tmp_path / "ipc-export.csv"
        assert reconnected_client.export_completed(destination) == 1
        assert destination.read_text(encoding="utf-8").startswith(
            "project,activity,start_time,stop_time,duration_seconds,note"
        )
        assert reconnected_client.save_export_delimiter("|") == "|"
        pipe_destination = tmp_path / "ipc-export.psv"
        assert reconnected_client.export_completed(pipe_destination) == 1
        assert pipe_destination.read_text(encoding="utf-8").startswith(
            "project|activity|start_time|stop_time|duration_seconds|note"
        )
        assert reconnected_client.save_export_delimiter(",") == ","
        summary_destination = tmp_path / "ipc-daily-summary.csv"
        assert reconnected_client.export_daily_summaries(summary_destination) == 1
        assert summary_destination.read_text(encoding="utf-8").startswith(
            "date,project,activity,duration_seconds"
        )
        range_destination = tmp_path / "ipc-range-summary.csv"
        assert (
            reconnected_client.export_range_summaries(
                range_destination,
                review_filter=ReviewFilter(project="website"),
            )
            == 1
        )
        assert range_destination.read_text(encoding="utf-8").startswith(
            "project,activity,duration_seconds"
        )
        assert reconnected_client.get_archive_activity_target(
            "website", "implementation"
        ) == ("Website", "Implementation")
        assert reconnected_client.archive_activity("website", "implementation") == (
            "Website",
            "Implementation",
        )
        assert reconnected_client.list_activities("Website") == []
        assert reconnected_client.list_recent_activities() == []
        with pytest.raises(AgentRequestError, match="activity is archived"):
            reconnected_client.start("Website", "Implementation", None)
        assert reconnected_client.list_completed() == [completed]
        assert reconnected_client.get_archive_project_target("website") == "Website"
        assert reconnected_client.archive_project("website") == "Website"
        assert reconnected_client.list_projects() == []
        assert reconnected_client.list_archived_projects() == ["Website"]
        assert reconnected_client.list_archived_activities() == [
            ArchivedActivity("Website", "Implementation", project_archived=True)
        ]
        with pytest.raises(AgentRequestError, match="restore project first"):
            reconnected_client.unarchive_activity("Website", "Implementation")
        assert reconnected_client.unarchive_project("website") == "Website"
        assert reconnected_client.unarchive_activity("website", "implementation") == (
            "Website",
            "Implementation",
        )
        assert reconnected_client.list_projects() == ["Website"]
        assert reconnected_client.list_activities("Website") == ["Implementation"]
        assert reconnected_client.list_archived_projects() == []
        assert reconnected_client.list_archived_activities() == []
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


def test_start_action_preview_matches_noop_restart_and_switch_transitions(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        assert (
            client.get_start_action("Website", "Implementation", "Original")
            is StartAction.START
        )
        original = client.start("Website", "Implementation", "Original")

        assert (
            client.get_start_action(" website ", "IMPLEMENTATION", " Original ")
            is StartAction.ALREADY_TRACKING
        )
        with pytest.raises(AgentRequestError, match="already tracking"):
            client.start(" website ", "IMPLEMENTATION", " Original ")
        assert client.get_active() == original
        assert client.list_completed() == []

        assert (
            client.get_start_action("Website", "Implementation", "New note")
            is StartAction.RESTART
        )
        restarted = client.start("Website", "Implementation", "New note")
        first_completed = client.list_completed()
        assert len(first_completed) == 1
        assert first_completed[0].stopped_at == restarted.started_at
        assert restarted.project == original.project
        assert restarted.activity == original.activity
        assert restarted.note == "New note"

        assert (
            client.get_start_action("Website", "Review", "New note")
            is StartAction.SWITCH
        )
        switched = client.start("Website", "Review", "New note")
        completed = client.list_completed()
        assert len(completed) == 2
        assert completed[1].stopped_at == switched.started_at
        assert completed[1].entry_id == restarted.entry_id
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_completed_entry_correction_round_trips_over_ipc(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        started = client.start("Website", "Planning", "Original")
        completed = client.stop()
        assert completed is not None
        corrected = client.correct_completed(
            completed.entry_id,
            " Client ",
            " Review ",
            completed.started_at,
            completed.stopped_at + timedelta(seconds=1),
            " Revised ",
        )

        assert corrected.entry_id == started.entry_id
        assert corrected.project == "Client"
        assert corrected.activity == "Review"
        assert corrected.note == "Revised"
        assert client.list_completed() == [corrected]

        with pytest.raises(AgentRequestError, match="must include a UTC offset"):
            client._request(
                "correct_completed",
                {
                    "entry_id": corrected.entry_id,
                    "project": corrected.project,
                    "activity": corrected.activity,
                    "started_at": "2026-07-20T10:00:00",
                    "stopped_at": "2026-07-20T11:00:00+00:00",
                    "note": None,
                },
            )
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_manual_entry_round_trips_over_ipc_without_changing_active_timer(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        active = client.start("Website", "Implementation", "Still running")
        started_at = datetime(2026, 7, 19, 10, tzinfo=UTC)
        manual = client.create_manual_entry(
            " Client ",
            " Review ",
            started_at,
            started_at + timedelta(hours=1),
            " Missed work ",
        )

        assert manual.project == "Client"
        assert manual.activity == "Review"
        assert manual.note == "Missed work"
        assert client.get_active() == active
        assert client.list_completed() == [manual]
        assert AgentClient(paths).list_completed() == [manual]

        client.shutdown()
        thread.join(timeout=2)
        assert not thread.is_alive()
        thread = threading.Thread(target=serve, args=(paths,), daemon=True)
        thread.start()
        client = AgentClient(paths)
        _wait_until_ready(client)
        assert client.list_completed() == [manual]
        assert client.get_active() == active
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_create_project_and_activity_round_trip_and_reject_duplicates_over_ipc(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        assert client.create_project(" Research ") == "Research"
        assert client.list_projects() == ["Research"]

        with pytest.raises(AgentRequestError, match="project already exists"):
            client.create_project("research")

        assert client.create_activity(" research ", " Literature review ") == (
            "Research",
            "Literature review",
        )
        assert client.list_activities("Research") == ["Literature review"]

        with pytest.raises(AgentRequestError, match="activity already exists"):
            client.create_activity("Research", "literature review")

        with pytest.raises(AgentRequestError, match="project not found"):
            client.create_activity("Unknown", "Planning")

        client.archive_project("Research")
        with pytest.raises(AgentRequestError, match="project is archived"):
            client.create_activity("Research", "Planning")
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_instance_lock_rejects_a_second_agent(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)

    with instance_lock(paths.lock):
        with pytest.raises(AgentAlreadyRunningError):
            with instance_lock(paths.lock):
                raise AssertionError("the second process lock was acquired")


def test_agent_can_start_as_a_separate_process(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    client = ensure_agent_running(paths, timeout_seconds=15.0)

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


class MonotonicIdleDetector:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._started = time.monotonic()

    def idle_seconds(self) -> float:
        return time.monotonic() - self._started


class FailingIdleDetector:
    def idle_seconds(self) -> float:
        raise OSError("simulated idle detector failure")


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
        started = client.start("Background", "Notifications")
        _wait_for_reminder(notifier, ReminderKind.ACTIVE)
        assert AgentClient(paths).get_active() == started
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_agent_dispatches_notification_smoke(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    notifier = RecordingNotifier()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": notifier,
            "reminder_intervals": ReminderIntervals(inactive=None, active=None),
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.send_test_notification()
        assert notifier.reminders == [Reminder(ReminderKind.INACTIVE)]
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_idle_detection_triggers_active_reminder_without_mutating_timer(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    notifier = RecordingNotifier()
    detector = MonotonicIdleDetector()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": notifier,
            "idle_detector": detector,
            "idle_poll_seconds": 0.01,
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        assert client.get_idle_detection_status().available is True
        client.save_configuration(
            ReminderSettings(
                inactive_enabled=False,
                active_enabled=False,
                idle_enabled=True,
                idle_threshold_minutes=0.001,
                snooze_minutes=0.001,
            )
        )
        started = client.start("Idle", "Reminder")
        detector.reset()

        reminder = _wait_for_pending_reminder(client, ReminderKind.ACTIVE)

        assert reminder.reason is ReminderReason.IDLE
        assert reminder.idle_threshold_minutes == 0.001
        assert client.get_active() == started
        assert client.list_completed() == []
        assert notifier.reminders[-1] == reminder

        edited = client.edit_active("Idle", "Updated")
        pending_after_edit = client.get_reminder()
        assert pending_after_edit is not None
        assert pending_after_edit.reason is ReminderReason.IDLE
        assert pending_after_edit.activity == "Updated"
        assert edited.entry_id == started.entry_id
        assert edited.started_at == started.started_at

        assert client.snooze_reminder() is True
        snoozed = _wait_for_pending_reminder(client, ReminderKind.ACTIVE)
        assert snoozed.reason is ReminderReason.IDLE
        assert client.get_active() == edited

        assert client.confirm_active_reminder() is True
        detector.reset()
        repeated = _wait_for_pending_reminder(client, ReminderKind.ACTIVE)
        assert repeated.reason is ReminderReason.IDLE
        assert client.get_active() == edited
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_idle_detector_failure_reports_unavailable_without_timer_mutation(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": RecordingNotifier(),
            "idle_detector": FailingIdleDetector(),
            "idle_poll_seconds": 0.01,
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.save_configuration(
            ReminderSettings(
                inactive_enabled=False,
                active_enabled=False,
                idle_enabled=True,
                idle_threshold_minutes=0.001,
            )
        )
        started = client.start("Idle", "Failure")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not client.get_idle_detection_status().available:
                break
            time.sleep(0.01)
        assert client.get_idle_detection_status().available is False
        assert client.get_active() == started
        assert client.get_reminder() is None
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_active_reminder_can_be_polled_confirmed_or_ignored(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    notifier = RecordingNotifier()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": notifier,
            "reminder_intervals": ReminderIntervals(inactive=None, active=0.15),
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        client.save_configuration(
            ReminderSettings(
                inactive_enabled=False,
                active_enabled=True,
                active_interval_minutes=0.0025,
                snooze_minutes=0.001,
            )
        )
        started = client.start("Connected", "Confirmation")
        reminder = _wait_for_pending_reminder(client, ReminderKind.ACTIVE)

        assert reminder == Reminder(
            ReminderKind.ACTIVE,
            project="Connected",
            activity="Confirmation",
        )
        edited = client.edit_active("Updated", "Details", "Still running")
        assert edited.entry_id == started.entry_id
        assert edited.started_at == started.started_at
        assert client.list_completed() == []
        assert client.get_reminder() == Reminder(
            ReminderKind.ACTIVE,
            project="Updated",
            activity="Details",
        )
        started = edited
        first_count = len(notifier.reminders)
        _wait_for_reminder_count(notifier, first_count + 1)
        assert client.get_active() == started

        assert client.snooze_reminder() is True
        assert client.get_reminder() is None
        assert client.snooze_reminder() is False
        _wait_for_pending_reminder(client, ReminderKind.ACTIVE)
        assert client.get_active() == started

        assert client.confirm_active_reminder() is True
        assert client.get_reminder() is None
        assert client.get_active() == started
        assert client.confirm_active_reminder() is False

        _wait_for_pending_reminder(client, ReminderKind.ACTIVE)
        assert client.get_active() == started
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_active_detail_edit_round_trips_and_rejects_a_noop_over_ipc(
    tmp_path: Path,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    thread = threading.Thread(target=serve, args=(paths,), daemon=True)
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        original = client.start("Website", "Planning", "Original")
        with pytest.raises(AgentRequestError, match="details are unchanged"):
            client.edit_active(" website ", "PLANNING", " Original ")
        assert client.get_active() == original

        edited = client.edit_active(" Client ", " Review ", " Revised ")
        assert edited.entry_id == original.entry_id
        assert edited.started_at == original.started_at
        assert edited.project == "Client"
        assert edited.activity == "Review"
        assert edited.note == "Revised"
        assert client.list_completed() == []

        client.shutdown()
        thread.join(timeout=2)
        assert not thread.is_alive()
        thread = threading.Thread(target=serve, args=(paths,), daemon=True)
        thread.start()
        client = AgentClient(paths)
        _wait_until_ready(client)
        assert client.get_active() == edited
        assert client.list_completed() == []
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_agent_uses_reminder_intervals_from_configuration(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    paths.config.write_text(
        """
[reminders]
inactive_interval_minutes = 0.001
active_enabled = false
""".strip(),
        encoding="utf-8",
    )
    notifier = RecordingNotifier()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={"notifier": notifier},
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    try:
        _wait_for_reminder(notifier, ReminderKind.INACTIVE)
    finally:
        client.shutdown()
        thread.join(timeout=2)

    assert not thread.is_alive()


def test_agent_persists_and_live_reloads_reminder_settings(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    notifier = RecordingNotifier()
    thread = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={
            "notifier": notifier,
            "reminder_intervals": ReminderIntervals(inactive=None, active=None),
        },
        daemon=True,
    )
    thread.start()
    client = AgentClient(paths)
    _wait_until_ready(client)

    enabled = ReminderSettings(
        inactive_enabled=True,
        inactive_interval_minutes=0.001,
        active_enabled=False,
        active_interval_minutes=7.5,
        snooze_minutes=0.001,
    )
    disabled = ReminderSettings(
        inactive_enabled=False,
        inactive_interval_minutes=0.001,
        active_enabled=False,
        active_interval_minutes=7.5,
    )
    durable = ReminderSettings(
        inactive_enabled=False,
        inactive_interval_minutes=3,
        active_enabled=True,
        active_interval_minutes=9.5,
    )
    try:
        assert client.get_theme() == "textual-dark"
        assert client.save_theme("nord") == "nord"
        assert client.get_theme() == "nord"
        assert client.get_export_delimiter() == ","
        assert client.save_export_delimiter("|") == "|"
        assert client.get_export_delimiter() == "|"
        assert client.save_configuration(enabled) == enabled
        assert client.get_configuration() == enabled
        _wait_for_pending_reminder(client, ReminderKind.INACTIVE)
        assert client.snooze_reminder() is True
        assert client.get_reminder() is None
        _wait_for_pending_reminder(client, ReminderKind.INACTIVE)

        count = len(notifier.reminders)
        assert client.save_configuration(disabled) == disabled
        assert client.get_reminder() is None
        time.sleep(0.1)
        assert len(notifier.reminders) == count

        assert client.save_configuration(durable) == durable
        assert load_config(paths.config).reminder_settings == durable
        assert load_config(paths.config).ui_settings.theme == "nord"
        assert load_config(paths.config).export_settings.delimiter == "|"
    finally:
        client.shutdown()
        thread.join(timeout=2)

    restarted = threading.Thread(
        target=serve,
        args=(paths,),
        kwargs={"notifier": notifier},
        daemon=True,
    )
    restarted.start()
    recovered_client = AgentClient(paths)
    _wait_until_ready(recovered_client)
    try:
        assert recovered_client.get_configuration() == durable
        assert recovered_client.get_theme() == "nord"
        assert recovered_client.get_export_delimiter() == "|"
    finally:
        recovered_client.shutdown()
        restarted.join(timeout=2)

    assert not thread.is_alive()
    assert not restarted.is_alive()


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


def _wait_for_pending_reminder(
    client: AgentClient,
    kind: ReminderKind,
) -> Reminder:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        reminder = client.get_reminder()
        if reminder is not None and reminder.kind is kind:
            return reminder
        time.sleep(0.01)
    raise AssertionError(f"{kind.value} reminder was not exposed over IPC")


def _wait_for_reminder_count(notifier: RecordingNotifier, count: int) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if len(notifier.reminders) >= count:
            return
        time.sleep(0.01)
    raise AssertionError(f"fewer than {count} reminders were delivered")
