"""Single-writer background process for tracking and reminders."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import asdict
from multiprocessing import AuthenticationError
from multiprocessing.connection import Listener
from pathlib import Path
from typing import cast

from time_tracker.agent.reminders import ReminderCoordinator
from time_tracker.application.reminders import Reminder, ReminderIntervals, ReminderKind
from time_tracker.application.tracking import TrackingService
from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.infrastructure.configuration import load_config
from time_tracker.infrastructure.instance_lock import instance_lock
from time_tracker.infrastructure.ipc import PROTOCOL_VERSION
from time_tracker.infrastructure.notifications import (
    NativeNotificationService,
    NotificationService,
)
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository


def serve(
    paths: AgentPaths,
    *,
    notifier: NotificationService | None = None,
    reminder_intervals: ReminderIntervals | None = None,
) -> None:
    """Serve one authenticated foreground connection at a time."""
    paths.prepare()
    with instance_lock(paths.lock):
        _serve_locked(paths, notifier, reminder_intervals)


def _serve_locked(
    paths: AgentPaths,
    notifier: NotificationService | None,
    reminder_intervals: ReminderIntervals | None,
) -> None:
    """Own the endpoint and database while the instance lock is held."""
    intervals = (
        reminder_intervals
        if reminder_intervals is not None
        else load_config(paths.config).reminder_intervals
    )
    if paths.family == "AF_UNIX":
        Path(paths.address).unlink(missing_ok=True)

    log_handler = logging.FileHandler(paths.log, encoding="utf-8")
    log_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    application_logger = logging.getLogger("time_tracker")
    application_logger.addHandler(log_handler)
    application_logger.setLevel(logging.INFO)
    service = TrackingService(SQLiteTimerRepository(paths.database))
    notification_service = notifier or NativeNotificationService()
    listener = Listener(
        paths.address,
        family=paths.family,
        authkey=paths.authkey(),
    )
    try:
        asyncio.run(
            _serve_connections(
                listener,
                service,
                notification_service,
                intervals,
            )
        )
    finally:
        listener.close()
        application_logger.removeHandler(log_handler)
        log_handler.close()
        if paths.family == "AF_UNIX":
            Path(paths.address).unlink(missing_ok=True)


async def _serve_connections(
    listener: Listener,
    service: TrackingService,
    notifier: NotificationService,
    reminder_intervals: ReminderIntervals | None,
) -> None:
    """Keep reminder scheduling responsive while IPC and SQLite block in threads."""
    coordinator = ReminderCoordinator(service, notifier, reminder_intervals)
    reminder_task = asyncio.create_task(coordinator.run())
    running = True
    try:
        while running:
            try:
                connection = await asyncio.to_thread(listener.accept)
            except AuthenticationError:
                continue
            try:
                request_bytes = await asyncio.to_thread(connection.recv_bytes)
                (
                    response,
                    running,
                    timer_changed,
                    notification_smoke,
                ) = await asyncio.to_thread(
                    _handle_request,
                    request_bytes,
                    service,
                )
                if notification_smoke:
                    try:
                        await notifier.send(Reminder(ReminderKind.INACTIVE))
                    except Exception as error:
                        response = {
                            "request_id": response.get("request_id"),
                            "error": {
                                "code": "notification_failed",
                                "message": str(error),
                            },
                        }
                await asyncio.to_thread(
                    connection.send_bytes,
                    json.dumps(response).encode("utf-8"),
                )
                if timer_changed:
                    coordinator.timer_changed()
            except EOFError:
                continue
            finally:
                connection.close()
    finally:
        coordinator.stop()
        await reminder_task


def _handle_request(
    payload: bytes,
    service: TrackingService,
) -> tuple[dict[str, object], bool, bool, bool]:
    request_id: object = None
    try:
        decoded: object = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("request must be a JSON object")
        request = cast(dict[str, object], decoded)
        request_id = request.get("request_id")
        if request.get("version") != PROTOCOL_VERSION:
            raise ValueError("unsupported protocol version")
        if not isinstance(request_id, str):
            raise ValueError("request_id must be a string")
        method = request.get("method")
        params_value = request.get("params")
        if not isinstance(method, str) or not isinstance(params_value, dict):
            raise ValueError("method and params are required")
        params = cast(dict[str, object], params_value)

        if method == "ping":
            result: object = {"version": PROTOCOL_VERSION}
        elif method == "get_active":
            result = _timer_dict(service.get_active())
        elif method == "list_projects":
            result = service.list_projects()
        elif method == "list_activities":
            result = service.list_activities(_required_str(params, "project"))
        elif method == "start":
            result = _timer_dict(
                service.start(
                    _required_str(params, "project"),
                    _required_str(params, "activity"),
                    _optional_str(params, "note"),
                )
            )
        elif method == "stop":
            result = _timer_dict(service.stop())
        elif method == "notification_smoke":
            result = None
        elif method == "shutdown":
            result = None
            return {"request_id": request_id, "result": result}, False, False, False
        else:
            raise ValueError(f"unknown method: {method}")
        return (
            {
                "request_id": request_id,
                "result": result,
            },
            True,
            method in {"start", "stop"},
            method == "notification_smoke",
        )
    except (RuntimeError, sqlite3.Error, TypeError, ValueError) as error:
        return (
            {
                "request_id": request_id,
                "error": {"code": "invalid_request", "message": str(error)},
            },
            True,
            False,
            False,
        )


def _timer_dict(timer: ActiveTimer | CompletedTimer | None) -> object:
    if timer is None:
        return None
    values = asdict(timer)
    values["started_at"] = timer.started_at.isoformat()
    if isinstance(timer, CompletedTimer):
        values["stopped_at"] = timer.stopped_at.isoformat()
    return values


def _required_str(params: dict[str, object], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _optional_str(params: dict[str, object], name: str) -> str | None:
    value = params.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    return value
