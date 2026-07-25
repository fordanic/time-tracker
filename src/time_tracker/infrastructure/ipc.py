"""Authenticated, versioned JSON client for the local background process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from multiprocessing.connection import Client
from pathlib import Path
from typing import cast

from time_tracker.application.configuration import ReminderSettings
from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.application.idle import IdleDetectionStatus
from time_tracker.application.reminders import Reminder, ReminderKind, ReminderReason
from time_tracker.application.reporting import ReviewFilter
from time_tracker.application.tracking import (
    ArchivedActivity,
    RecentActivity,
    StartAction,
)
from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.infrastructure.paths import AgentPaths

PROTOCOL_VERSION = 4
_WINDOWS_DETACHED_PROCESS_FLAGS = 0x00000208


class AgentUnavailableError(RuntimeError):
    """The local agent could not be reached or started."""


class AgentRequestError(RuntimeError):
    """The agent rejected a well-formed application request."""

    def __init__(self, message: str, *, code: str = "request_failed") -> None:
        super().__init__(message)
        self.code = code


class AgentClient:
    """A short-lived-connection client suitable for one foreground TUI."""

    def __init__(self, paths: AgentPaths) -> None:
        self.paths = paths

    def ping(self) -> None:
        """Verify that an authenticated compatible agent is listening."""
        self._request("ping", {})

    @property
    def configuration_path(self) -> Path:
        """Return the durable user-editable configuration path."""
        return self.paths.config

    def get_configuration(self) -> ReminderSettings:
        """Return reminder settings currently used by the agent."""
        return _settings_from_object(self._request("get_configuration", {}))

    def save_configuration(self, settings: ReminderSettings) -> ReminderSettings:
        """Persist and live-reload validated reminder settings."""
        result = self._request(
            "save_configuration",
            {
                "inactive_enabled": settings.inactive_enabled,
                "inactive_interval_minutes": settings.inactive_interval_minutes,
                "active_enabled": settings.active_enabled,
                "active_interval_minutes": settings.active_interval_minutes,
                "window_enabled": settings.window_enabled,
                "window_weekdays": list(settings.window_weekdays),
                "window_start": settings.window_start,
                "window_end": settings.window_end,
                "snooze_minutes": settings.snooze_minutes,
                "idle_enabled": settings.idle_enabled,
                "idle_threshold_minutes": settings.idle_threshold_minutes,
            },
        )
        return _settings_from_object(result)

    def get_theme(self) -> str:
        """Return the persisted TUI theme name."""
        return _object_str(self._request("get_theme", {}))

    def save_theme(self, theme: str) -> str:
        """Persist the selected TUI theme name."""
        return _object_str(self._request("save_theme", {"theme": theme}))

    def get_export_delimiter(self) -> str:
        """Return the persisted export delimiter."""
        return _object_str(self._request("get_export_delimiter", {}))

    def save_export_delimiter(self, delimiter: str) -> str:
        """Persist the selected export delimiter."""
        return _object_str(
            self._request("save_export_delimiter", {"delimiter": delimiter})
        )

    def get_idle_detection_status(self) -> IdleDetectionStatus:
        """Return whether idle-duration detection is available this session."""
        data = _object_dict(self._request("get_idle_detection_status", {}))
        return IdleDetectionStatus(available=_object_bool(data.get("available")))

    def get_active(self) -> ActiveTimer | None:
        """Return the active timer recovered by the background process."""
        result = self._request("get_active", {})
        return None if result is None else _active_from_object(result)

    def get_reminder(self) -> Reminder | None:
        """Return the latest reminder due in the background process."""
        result = self._request("get_reminder", {})
        return None if result is None else _reminder_from_object(result)

    def confirm_active_reminder(self) -> bool:
        """Confirm an active timer and restart its reminder interval."""
        result = self._request("confirm_active_reminder", {})
        if not isinstance(result, bool):
            raise AgentRequestError("the agent returned malformed confirmation data")
        return result

    def snooze_reminder(self) -> bool:
        """Defer the pending reminder without changing timer state."""
        result = self._request("snooze_reminder", {})
        if not isinstance(result, bool):
            raise AgentRequestError("the agent returned malformed snooze data")
        return result

    def list_projects(self) -> list[str]:
        """Return selectable project names from authoritative storage."""
        return _string_list(self._request("list_projects", {}))

    def list_activities(self, project: str) -> list[str]:
        """Return selectable activities for one project."""
        return _string_list(self._request("list_activities", {"project": project}))

    def list_completed(self) -> list[CompletedTimer]:
        """Return completed entries in chronological order."""
        result = self._request("list_completed", {})
        if not isinstance(result, list):
            raise AgentRequestError("the agent returned malformed history data")
        return [_completed_from_object(item) for item in result]

    def correct_completed(
        self,
        entry_id: int,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer:
        """Persist one completed-entry correction before returning it."""
        result = self._request(
            "correct_completed",
            {
                "entry_id": entry_id,
                "project": project,
                "activity": activity,
                "started_at": started_at.isoformat(),
                "stopped_at": stopped_at.isoformat(),
                "note": note,
            },
        )
        return _completed_from_object(result)

    def create_manual_entry(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer:
        """Persist one manual completed entry before returning it."""
        result = self._request(
            "create_manual_entry",
            {
                "project": project,
                "activity": activity,
                "started_at": started_at.isoformat(),
                "stopped_at": stopped_at.isoformat(),
                "note": note,
            },
        )
        return _completed_from_object(result)

    def edit_active(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> ActiveTimer:
        """Persist active detail changes without restarting the timer."""
        result = self._request(
            "edit_active",
            {"project": project, "activity": activity, "note": note},
        )
        return _active_from_object(result)

    def list_recent_activities(self) -> list[RecentActivity]:
        """Return recent selectable project/activity pairs."""
        result = self._request("list_recent_activities", {})
        if not isinstance(result, list):
            raise AgentRequestError("the agent returned malformed recent activity data")
        return [_recent_activity_from_object(item) for item in result]

    def get_start_action(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> StartAction:
        """Return the application-classified effect of a capture selection."""
        result = self._request(
            "get_start_action",
            {"project": project, "activity": activity, "note": note},
        )
        try:
            return StartAction(_object_str(result))
        except ValueError as error:
            raise AgentRequestError(
                "the agent returned an unknown start action"
            ) from error

    def archive_project(self, project: str) -> str:
        """Archive a project and return its canonical stored name."""
        result = _object_dict(self._request("archive_project", {"project": project}))
        return _object_str(result.get("project"))

    def get_archive_project_target(self, project: str) -> str:
        """Validate and return a canonical project archive target."""
        result = _object_dict(
            self._request("get_archive_project_target", {"project": project})
        )
        return _object_str(result.get("project"))

    def archive_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Archive an activity and return its canonical stored names."""
        result = _object_dict(
            self._request(
                "archive_activity",
                {"project": project, "activity": activity},
            )
        )
        return (
            _object_str(result.get("project")),
            _object_str(result.get("activity")),
        )

    def get_archive_activity_target(
        self,
        project: str,
        activity: str,
    ) -> tuple[str, str]:
        """Validate and return a canonical activity archive target."""
        result = _object_dict(
            self._request(
                "get_archive_activity_target",
                {"project": project, "activity": activity},
            )
        )
        return (
            _object_str(result.get("project")),
            _object_str(result.get("activity")),
        )

    def list_archived_projects(self) -> list[str]:
        """Return canonical archived project names."""
        return _string_list(self._request("list_archived_projects", {}))

    def list_archived_activities(self) -> list[ArchivedActivity]:
        """Return canonical archived activities with parent state."""
        result = self._request("list_archived_activities", {})
        if not isinstance(result, list):
            raise AgentRequestError("the agent returned malformed archived activities")
        return [_archived_activity_from_object(item) for item in result]

    def unarchive_project(self, project: str) -> str:
        """Restore a project and return its canonical stored name."""
        result = _object_dict(self._request("unarchive_project", {"project": project}))
        return _object_str(result.get("project"))

    def unarchive_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Restore an activity and return its canonical stored names."""
        result = _object_dict(
            self._request(
                "unarchive_activity",
                {"project": project, "activity": activity},
            )
        )
        return (
            _object_str(result.get("project")),
            _object_str(result.get("activity")),
        )

    def export_completed(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export completed entries without silently replacing a file."""
        try:
            result = self._request(
                "export_completed",
                {
                    "destination": str(destination),
                    "overwrite": overwrite,
                    **_review_filter_params(review_filter),
                },
            )
        except AgentRequestError as error:
            if error.code == "destination_exists":
                raise ExportDestinationExistsError(str(error)) from error
            raise
        data = _object_dict(result)
        return _object_int(data.get("entry_count"))

    def export_daily_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export daily project/activity summaries without silent replacement."""
        try:
            result = self._request(
                "export_daily_summaries",
                {
                    "destination": str(destination),
                    "overwrite": overwrite,
                    **_review_filter_params(review_filter),
                },
            )
        except AgentRequestError as error:
            if error.code == "destination_exists":
                raise ExportDestinationExistsError(str(error)) from error
            raise
        data = _object_dict(result)
        return _object_int(data.get("summary_count"))

    def export_range_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int:
        """Export selected-range project/activity totals."""
        try:
            result = self._request(
                "export_range_summaries",
                {
                    "destination": str(destination),
                    "overwrite": overwrite,
                    **_review_filter_params(review_filter),
                },
            )
        except AgentRequestError as error:
            if error.code == "destination_exists":
                raise ExportDestinationExistsError(str(error)) from error
            raise
        data = _object_dict(result)
        return _object_int(data.get("summary_count"))

    def start(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> ActiveTimer:
        """Persist a start transition before returning its active state."""
        result = self._request(
            "start",
            {"project": project, "activity": activity, "note": note},
        )
        return _active_from_object(result)

    def stop(self) -> CompletedTimer | None:
        """Persist a stop transition before returning its completed state."""
        result = self._request("stop", {})
        return None if result is None else _completed_from_object(result)

    def shutdown(self) -> None:
        """Ask the background process to stop without closing an active entry."""
        try:
            self._request("shutdown", {})
        except AgentRequestError as error:
            if not _is_protocol_version_error(error):
                raise
            self._request("shutdown", {}, version=PROTOCOL_VERSION - 1)

    def send_test_notification(self) -> None:
        """Ask the agent to dispatch a native smoke-test notification."""
        self._request("notification_smoke", {})

    def _request(
        self,
        method: str,
        params: dict[str, object],
        *,
        version: int = PROTOCOL_VERSION,
    ) -> object:
        request_id = str(uuid.uuid4())
        request = {
            "version": version,
            "request_id": request_id,
            "method": method,
            "params": params,
        }
        try:
            connection = Client(
                self.paths.address,
                family=self.paths.family,
                authkey=self.paths.authkey(),
            )
            try:
                connection.send_bytes(json.dumps(request).encode("utf-8"))
                payload = connection.recv_bytes()
            finally:
                connection.close()
        except (OSError, EOFError) as connection_error:
            raise AgentUnavailableError(
                "the Time Tracker agent is unavailable"
            ) from connection_error

        decoded: object = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise AgentRequestError("the agent returned an invalid response")
        response = cast(dict[str, object], decoded)
        if response.get("request_id") != request_id:
            raise AgentRequestError("the agent response did not match the request")
        response_error = response.get("error")
        if response_error is not None:
            if isinstance(response_error, dict):
                error_data = cast(dict[str, object], response_error)
                message = error_data.get("message")
                code = error_data.get("code")
                if isinstance(message, str):
                    raise AgentRequestError(
                        message,
                        code=code if isinstance(code, str) else "request_failed",
                    )
            raise AgentRequestError("the agent rejected the request")
        return response.get("result")


def ensure_agent_running(
    paths: AgentPaths,
    *,
    timeout_seconds: float = 5.0,
) -> AgentClient:
    """Return a connected client, starting a detached agent when necessary."""
    client = AgentClient(paths)
    try:
        client.ping()
        return client
    except AgentUnavailableError:
        pass
    except AgentRequestError as error:
        if not _is_protocol_version_error(error):
            raise
        client.shutdown()
        _wait_for_agent_exit(client, timeout_seconds)

    paths.prepare()
    command = _agent_command(paths)
    if os.name == "nt":
        subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=_WINDOWS_DETACHED_PROCESS_FLAGS,
        )
    else:
        subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            client.ping()
            return client
        except AgentUnavailableError:
            time.sleep(0.05)
    raise AgentUnavailableError("the Time Tracker agent did not start")


def _is_protocol_version_error(error: AgentRequestError) -> bool:
    return "unsupported protocol version" in str(error)


def _wait_for_agent_exit(client: AgentClient, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            client.ping()
        except AgentUnavailableError:
            return
        except AgentRequestError as error:
            if not _is_protocol_version_error(error):
                raise
        time.sleep(0.05)
    raise AgentUnavailableError("the incompatible Time Tracker agent did not stop")


def _agent_command(paths: AgentPaths, *, frozen: bool | None = None) -> list[str]:
    """Build the background command for source and frozen executables."""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    command = [sys.executable]
    if is_frozen:
        command.append("--agent")
    else:
        command.extend(("-m", "time_tracker.agent"))
    command.extend(
        (
            "--database",
            str(paths.database),
            "--config",
            str(paths.config),
            "--address",
            paths.address,
            "--secret",
            str(paths.secret),
            "--lock",
            str(paths.lock),
            "--log",
            str(paths.log),
            "--family",
            paths.family,
        )
    )
    return command


def _active_from_object(value: object) -> ActiveTimer:
    data = _object_dict(value)
    return ActiveTimer(
        entry_id=_object_int(data.get("entry_id")),
        project=_object_str(data.get("project")),
        activity=_object_str(data.get("activity")),
        started_at=datetime.fromisoformat(_object_str(data.get("started_at"))),
        note=_optional_str(data.get("note")),
    )


def _reminder_from_object(value: object) -> Reminder:
    data = _object_dict(value)
    try:
        kind = ReminderKind(_object_str(data.get("kind")))
        reason = ReminderReason(_object_str(data.get("reason")))
    except ValueError as error:
        raise AgentRequestError(
            "the agent returned an unknown reminder kind or reason"
        ) from error
    try:
        return Reminder(
            kind=kind,
            project=_optional_str(data.get("project")),
            activity=_optional_str(data.get("activity")),
            reason=reason,
            idle_threshold_minutes=_optional_number(data.get("idle_threshold_minutes")),
        )
    except ValueError as error:
        raise AgentRequestError("the agent returned malformed reminder data") from error


def _settings_from_object(value: object) -> ReminderSettings:
    data = _object_dict(value)
    inactive_enabled = data.get("inactive_enabled")
    active_enabled = data.get("active_enabled")
    if not isinstance(inactive_enabled, bool) or not isinstance(active_enabled, bool):
        raise AgentRequestError("the agent returned malformed configuration data")
    return ReminderSettings(
        inactive_enabled=inactive_enabled,
        inactive_interval_minutes=_object_number(data.get("inactive_interval_minutes")),
        active_enabled=active_enabled,
        active_interval_minutes=_object_number(data.get("active_interval_minutes")),
        window_enabled=_object_bool(data.get("window_enabled")),
        window_weekdays=tuple(_object_int_list(data.get("window_weekdays"))),
        window_start=_object_str(data.get("window_start")),
        window_end=_object_str(data.get("window_end")),
        snooze_minutes=_object_number(data.get("snooze_minutes")),
        idle_enabled=_object_bool(data.get("idle_enabled")),
        idle_threshold_minutes=_object_number(data.get("idle_threshold_minutes")),
    )


def _completed_from_object(value: object) -> CompletedTimer:
    data = _object_dict(value)
    return CompletedTimer(
        entry_id=_object_int(data.get("entry_id")),
        project=_object_str(data.get("project")),
        activity=_object_str(data.get("activity")),
        started_at=datetime.fromisoformat(_object_str(data.get("started_at"))),
        stopped_at=datetime.fromisoformat(_object_str(data.get("stopped_at"))),
        note=_optional_str(data.get("note")),
    )


def _review_filter_params(review_filter: ReviewFilter | None) -> dict[str, object]:
    selected = review_filter or ReviewFilter()
    return {
        "filter_start_date": (
            selected.start_date.isoformat() if selected.start_date is not None else None
        ),
        "filter_end_date": (
            selected.end_date.isoformat() if selected.end_date is not None else None
        ),
        "filter_project": selected.project,
        "filter_activity": selected.activity,
    }


def _recent_activity_from_object(value: object) -> RecentActivity:
    data = _object_dict(value)
    return RecentActivity(
        project=_object_str(data.get("project")),
        activity=_object_str(data.get("activity")),
    )


def _archived_activity_from_object(value: object) -> ArchivedActivity:
    data = _object_dict(value)
    project_archived = data.get("project_archived")
    if not isinstance(project_archived, bool):
        raise AgentRequestError("the agent returned malformed archive state")
    return ArchivedActivity(
        project=_object_str(data.get("project")),
        activity=_object_str(data.get("activity")),
        project_archived=project_archived,
    )


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AgentRequestError("the agent returned malformed timer data")
    return cast(dict[str, object], value)


def _object_str(value: object) -> str:
    if not isinstance(value, str):
        raise AgentRequestError("the agent returned malformed text data")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return _object_str(value)


def _object_int(value: object) -> int:
    if not isinstance(value, int):
        raise AgentRequestError("the agent returned malformed numeric data")
    return value


def _object_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentRequestError("the agent returned malformed numeric data")
    return float(value)


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    return _object_number(value)


def _object_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise AgentRequestError("the agent returned malformed boolean data")
    return value


def _object_int_list(value: object) -> list[int]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise AgentRequestError("the agent returned a malformed integer list")
    return cast(list[int], value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AgentRequestError("the agent returned a malformed list")
    return cast(list[str], value)
