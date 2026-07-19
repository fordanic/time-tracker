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

from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.infrastructure.paths import AgentPaths

PROTOCOL_VERSION = 1
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

    def get_active(self) -> ActiveTimer | None:
        """Return the active timer recovered by the background process."""
        result = self._request("get_active", {})
        return None if result is None else _active_from_object(result)

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

    def archive_project(self, project: str) -> str:
        """Archive a project and return its canonical stored name."""
        result = _object_dict(self._request("archive_project", {"project": project}))
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

    def export_completed(self, destination: Path, *, overwrite: bool = False) -> int:
        """Export completed entries without silently replacing a file."""
        try:
            result = self._request(
                "export_completed",
                {"destination": str(destination), "overwrite": overwrite},
            )
        except AgentRequestError as error:
            if error.code == "destination_exists":
                raise ExportDestinationExistsError(str(error)) from error
            raise
        data = _object_dict(result)
        return _object_int(data.get("entry_count"))

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
        self._request("shutdown", {})

    def send_test_notification(self) -> None:
        """Ask the agent to dispatch a native smoke-test notification."""
        self._request("notification_smoke", {})

    def _request(self, method: str, params: dict[str, object]) -> object:
        request_id = str(uuid.uuid4())
        request = {
            "version": PROTOCOL_VERSION,
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AgentRequestError("the agent returned a malformed list")
    return cast(list[str], value)
