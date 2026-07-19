"""Single-writer background process for the walking skeleton."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from multiprocessing import AuthenticationError
from multiprocessing.connection import Listener
from pathlib import Path
from typing import cast

from time_tracker.application.tracking import TrackingService
from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.infrastructure.instance_lock import instance_lock
from time_tracker.infrastructure.ipc import PROTOCOL_VERSION
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.sqlite_repository import SQLiteTimerRepository


def serve(paths: AgentPaths) -> None:
    """Serve one authenticated foreground connection at a time."""
    paths.prepare()
    with instance_lock(paths.lock):
        _serve_locked(paths)


def _serve_locked(paths: AgentPaths) -> None:
    """Own the endpoint and database while the instance lock is held."""
    if paths.family == "AF_UNIX":
        Path(paths.address).unlink(missing_ok=True)

    service = TrackingService(SQLiteTimerRepository(paths.database))
    listener = Listener(
        paths.address,
        family=paths.family,
        authkey=paths.authkey(),
    )
    running = True
    try:
        while running:
            try:
                connection = listener.accept()
            except AuthenticationError:
                continue
            try:
                request_bytes = connection.recv_bytes()
                response, running = _handle_request(request_bytes, service)
                connection.send_bytes(json.dumps(response).encode("utf-8"))
            except EOFError:
                continue
            finally:
                connection.close()
    finally:
        listener.close()
        if paths.family == "AF_UNIX":
            Path(paths.address).unlink(missing_ok=True)


def _handle_request(
    payload: bytes,
    service: TrackingService,
) -> tuple[dict[str, object], bool]:
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
        elif method == "shutdown":
            result = None
            return {"request_id": request_id, "result": result}, False
        else:
            raise ValueError(f"unknown method: {method}")
        return {"request_id": request_id, "result": result}, True
    except (RuntimeError, sqlite3.Error, TypeError, ValueError) as error:
        return {
            "request_id": request_id,
            "error": {"code": "invalid_request", "message": str(error)},
        }, True


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
