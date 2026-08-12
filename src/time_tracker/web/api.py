"""HTTP-to-agent translation and shared web presentation projections."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from time_tracker.application.configuration import ExportSettings, ReminderSettings
from time_tracker.application.exporting import ExportDestinationExistsError
from time_tracker.application.idle import IdleDetectionStatus
from time_tracker.application.reminders import Reminder
from time_tracker.application.reporting import (
    DatePreset,
    ReviewFilter,
    build_daily_review,
    build_daily_summaries,
    build_range_summaries,
    review_filter_activities,
    review_filter_for_preset,
    review_filter_projects,
)
from time_tracker.application.tracking import (
    ArchivedActivity,
    QuickSwitchAction,
    RecentActivity,
    StartAction,
    classify_quick_switch,
)
from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.infrastructure.ipc import AgentRequestError


class WebAgent(Protocol):
    """Agent operations exposed through the approved web interface."""

    @property
    def configuration_path(self) -> Path: ...

    def get_active(self) -> ActiveTimer | None: ...

    def get_reminder(self) -> Reminder | None: ...

    def confirm_active_reminder(self) -> bool: ...

    def snooze_reminder(self) -> bool: ...

    def list_projects(self) -> list[str]: ...

    def list_activities(self, project: str) -> list[str]: ...

    def list_completed(self) -> list[CompletedTimer]: ...

    def list_recent_activities(self) -> list[RecentActivity]: ...

    def get_start_action(
        self, project: str, activity: str, note: str | None = None
    ) -> StartAction: ...

    def start(
        self, project: str, activity: str, note: str | None = None
    ) -> ActiveTimer: ...

    def stop(self) -> CompletedTimer | None: ...

    def edit_active(
        self, project: str, activity: str, note: str | None = None
    ) -> ActiveTimer: ...

    def correct_completed(
        self,
        entry_id: int,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer: ...

    def create_manual_entry(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None = None,
    ) -> CompletedTimer: ...

    def delete_completed(self, entry_id: int) -> CompletedTimer: ...

    def export_completed(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int: ...

    def export_daily_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int: ...

    def export_range_summaries(
        self,
        destination: Path,
        *,
        overwrite: bool = False,
        review_filter: ReviewFilter | None = None,
    ) -> int: ...

    def create_project(self, project: str) -> str: ...

    def create_activity(self, project: str, activity: str) -> tuple[str, str]: ...

    def get_archive_project_target(self, project: str) -> str: ...

    def archive_project(self, project: str) -> str: ...

    def get_archive_activity_target(
        self, project: str, activity: str
    ) -> tuple[str, str]: ...

    def archive_activity(self, project: str, activity: str) -> tuple[str, str]: ...

    def list_archived_projects(self) -> list[str]: ...

    def list_archived_activities(self) -> list[ArchivedActivity]: ...

    def unarchive_project(self, project: str) -> str: ...

    def unarchive_activity(self, project: str, activity: str) -> tuple[str, str]: ...

    def get_configuration(self) -> ReminderSettings: ...

    def save_configuration(self, settings: ReminderSettings) -> ReminderSettings: ...

    def get_export_delimiter(self) -> str: ...

    def save_export_delimiter(self, delimiter: str) -> str: ...

    def get_idle_detection_status(self) -> IdleDetectionStatus: ...


class SerializedAgent:
    """Run blocking agent calls one at a time outside the ASGI event loop."""

    def __init__(self, client: WebAgent) -> None:
        self.client = client
        self._lock = asyncio.Lock()

    async def call(self, method: str, *args: object, **kwargs: object) -> object:
        async with self._lock:
            operation = getattr(self.client, method)
            return await asyncio.to_thread(operation, *args, **kwargs)


class WebApi:
    """Explicit local JSON endpoints with stable response envelopes."""

    def __init__(self, client: WebAgent) -> None:
        self.client = client
        self.agent = SerializedAgent(client)

    def routes(self) -> list[Route]:
        """Return the complete version-one API route set."""
        return [
            Route("/api/bootstrap", self.bootstrap),
            Route("/api/state", self.state),
            Route("/api/track/classify", self.classify, methods=["POST"]),
            Route("/api/timer/start", self.start, methods=["POST"]),
            Route("/api/timer/stop", self.stop, methods=["POST"]),
            Route("/api/timer/edit", self.edit_active, methods=["POST"]),
            Route("/api/reminder/confirm", self.confirm_reminder, methods=["POST"]),
            Route("/api/reminder/snooze", self.snooze_reminder, methods=["POST"]),
            Route("/api/review/query", self.review, methods=["POST"]),
            Route("/api/review/correct", self.correct, methods=["POST"]),
            Route("/api/review/create", self.create_manual, methods=["POST"]),
            Route("/api/review/delete", self.delete, methods=["POST"]),
            Route("/api/review/export", self.export, methods=["POST"]),
            Route("/api/manage/create-project", self.create_project, methods=["POST"]),
            Route(
                "/api/manage/create-activity", self.create_activity, methods=["POST"]
            ),
            Route(
                "/api/manage/archive-project-target",
                self.archive_project_target,
                methods=["POST"],
            ),
            Route(
                "/api/manage/archive-project", self.archive_project, methods=["POST"]
            ),
            Route(
                "/api/manage/archive-activity-target",
                self.archive_activity_target,
                methods=["POST"],
            ),
            Route(
                "/api/manage/archive-activity",
                self.archive_activity,
                methods=["POST"],
            ),
            Route(
                "/api/manage/unarchive-project",
                self.unarchive_project,
                methods=["POST"],
            ),
            Route(
                "/api/manage/unarchive-activity",
                self.unarchive_activity,
                methods=["POST"],
            ),
            Route("/api/settings", self.save_settings, methods=["POST"]),
        ]

    async def bootstrap(self, _request: Request) -> Response:
        async def operation() -> dict[str, object]:
            projects = cast(list[str], await self.agent.call("list_projects"))
            activities: dict[str, list[str]] = {}
            for project in projects:
                activities[project] = cast(
                    list[str], await self.agent.call("list_activities", project)
                )
            completed = cast(
                list[CompletedTimer], await self.agent.call("list_completed")
            )
            today_filter = review_filter_for_preset(
                DatePreset.TODAY, today=date.today()
            )
            today_seconds = sum(
                (
                    group.duration.total_seconds()
                    for group in build_daily_review(
                        completed, review_filter=today_filter
                    )
                ),
                start=0.0,
            )
            return {
                "active": _timer_json(await self.agent.call("get_active")),
                "reminder": _dataclass_json(await self.agent.call("get_reminder")),
                "projects": projects,
                "activities": activities,
                "recent": _dataclass_list_json(
                    await self.agent.call("list_recent_activities")
                ),
                "completed": [_timer_json(entry) for entry in completed],
                "today_completed_seconds": today_seconds,
                "archived_projects": await self.agent.call("list_archived_projects"),
                "archived_activities": _dataclass_list_json(
                    await self.agent.call("list_archived_activities")
                ),
                "settings": _dataclass_json(await self.agent.call("get_configuration")),
                "export_delimiter": await self.agent.call("get_export_delimiter"),
                "idle_detection": _dataclass_json(
                    await self.agent.call("get_idle_detection_status")
                ),
                "configuration_path": str(self.client.configuration_path),
            }

        return await self._respond(operation)

    async def state(self, _request: Request) -> Response:
        async def operation() -> dict[str, object]:
            return {
                "active": _timer_json(await self.agent.call("get_active")),
                "reminder": _dataclass_json(await self.agent.call("get_reminder")),
            }

        return await self._respond(operation)

    async def classify(self, request: Request) -> Response:
        body = await _body(request)

        async def operation() -> dict[str, object]:
            if _boolean(body, "quick", default=False):
                selected = RecentActivity(
                    _text(body, "project"), _text(body, "activity")
                )
                active = cast(ActiveTimer | None, await self.agent.call("get_active"))
                quick_action = classify_quick_switch(active, selected)
                return {
                    "action": (
                        StartAction.START.value
                        if quick_action is QuickSwitchAction.START
                        else StartAction.SWITCH.value
                        if quick_action is QuickSwitchAction.SWITCH
                        else StartAction.ALREADY_TRACKING.value
                    )
                }
            action = await self.agent.call(
                "get_start_action",
                _text(body, "project"),
                _text(body, "activity"),
                _optional_text(body, "note"),
            )
            return {"action": cast(StartAction, action).value}

        return await self._respond(operation)

    async def start(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "active",
            "start",
            _text(body, "project"),
            _text(body, "activity"),
            _optional_text(body, "note"),
        )

    async def stop(self, _request: Request) -> Response:
        return await self._agent_result("completed", "stop")

    async def edit_active(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "active",
            "edit_active",
            _text(body, "project"),
            _text(body, "activity"),
            _optional_text(body, "note"),
        )

    async def confirm_reminder(self, _request: Request) -> Response:
        return await self._agent_result("confirmed", "confirm_active_reminder")

    async def snooze_reminder(self, _request: Request) -> Response:
        return await self._agent_result("snoozed", "snooze_reminder")

    async def review(self, request: Request) -> Response:
        body = await _body(request)

        async def operation() -> dict[str, object]:
            entries = cast(
                list[CompletedTimer], await self.agent.call("list_completed")
            )
            review_filter = _review_filter(body)
            groups = build_daily_review(entries, review_filter=review_filter)
            return {
                "groups": [
                    {
                        "day": group.day.isoformat(),
                        "duration_seconds": group.duration.total_seconds(),
                        "segments": [
                            {
                                **asdict(segment),
                                "day": segment.day.isoformat(),
                                "started_at": segment.started_at.isoformat(),
                                "stopped_at": segment.stopped_at.isoformat(),
                                "duration_seconds": segment.duration.total_seconds(),
                            }
                            for segment in group.segments
                        ],
                    }
                    for group in groups
                ],
                "daily_summaries": [
                    {
                        "day": summary.day.isoformat(),
                        "project": summary.project,
                        "activity": summary.activity,
                        "duration_seconds": summary.duration.total_seconds(),
                    }
                    for summary in build_daily_summaries(
                        entries, review_filter=review_filter
                    )
                ],
                "range_summaries": [
                    {
                        "project": summary.project,
                        "activity": summary.activity,
                        "duration_seconds": summary.duration.total_seconds(),
                    }
                    for summary in build_range_summaries(
                        entries, review_filter=review_filter
                    )
                ],
                "projects": review_filter_projects(entries),
                "activities": review_filter_activities(entries, review_filter.project),
            }

        return await self._respond(operation)

    async def correct(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "entry",
            "correct_completed",
            _integer(body, "entry_id"),
            _text(body, "project"),
            _text(body, "activity"),
            _instant(body, "started_at"),
            _instant(body, "stopped_at"),
            _optional_text(body, "note"),
        )

    async def create_manual(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "entry",
            "create_manual_entry",
            _text(body, "project"),
            _text(body, "activity"),
            _instant(body, "started_at"),
            _instant(body, "stopped_at"),
            _optional_text(body, "note"),
        )

    async def delete(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "deleted", "delete_completed", _integer(body, "entry_id")
        )

    async def export(self, request: Request) -> Response:
        body = await _body(request)
        representation = _text(body, "representation")
        method = {
            "completed": "export_completed",
            "daily": "export_daily_summaries",
            "range": "export_range_summaries",
        }.get(representation)
        if method is None:
            return _error(
                "invalid_field", "unknown export representation", "representation"
            )

        async def operation() -> dict[str, object]:
            count = await self.agent.call(
                method,
                Path(_text(body, "destination")),
                overwrite=_boolean(body, "overwrite", default=False),
                review_filter=_review_filter(body),
            )
            return {"count": count, "destination": _text(body, "destination")}

        return await self._respond(operation)

    async def create_project(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "project", "create_project", _text(body, "project")
        )

    async def create_activity(self, request: Request) -> Response:
        body = await _body(request)
        return await self._pair_result("create_activity", body)

    async def archive_project_target(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "project", "get_archive_project_target", _text(body, "project")
        )

    async def archive_project(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "project", "archive_project", _text(body, "project")
        )

    async def archive_activity_target(self, request: Request) -> Response:
        body = await _body(request)
        return await self._pair_result("get_archive_activity_target", body)

    async def archive_activity(self, request: Request) -> Response:
        body = await _body(request)
        return await self._pair_result("archive_activity", body)

    async def unarchive_project(self, request: Request) -> Response:
        body = await _body(request)
        return await self._agent_result(
            "project", "unarchive_project", _text(body, "project")
        )

    async def unarchive_activity(self, request: Request) -> Response:
        body = await _body(request)
        return await self._pair_result("unarchive_activity", body)

    async def save_settings(self, request: Request) -> Response:
        body = await _body(request)

        async def operation() -> dict[str, object]:
            delimiter = ExportSettings(_text(body, "export_delimiter")).delimiter
            settings = ReminderSettings(
                inactive_enabled=_boolean(body, "inactive_enabled"),
                inactive_interval_minutes=_number(body, "inactive_interval_minutes"),
                active_enabled=_boolean(body, "active_enabled"),
                active_interval_minutes=_number(body, "active_interval_minutes"),
                window_enabled=_boolean(body, "window_enabled"),
                window_weekdays=tuple(_integer_list(body, "window_weekdays")),
                window_start=_text(body, "window_start"),
                window_end=_text(body, "window_end"),
                snooze_minutes=_number(body, "snooze_minutes"),
                idle_enabled=_boolean(body, "idle_enabled"),
                idle_threshold_minutes=_number(body, "idle_threshold_minutes"),
            )
            saved = await self.agent.call("save_configuration", settings)
            saved_delimiter = await self.agent.call("save_export_delimiter", delimiter)
            return {
                "settings": _dataclass_json(saved),
                "export_delimiter": saved_delimiter,
            }

        return await self._respond(operation)

    async def _pair_result(self, method: str, body: dict[str, object]) -> Response:
        async def operation() -> dict[str, object]:
            pair = cast(
                tuple[str, str],
                await self.agent.call(
                    method, _text(body, "project"), _text(body, "activity")
                ),
            )
            return {"project": pair[0], "activity": pair[1]}

        return await self._respond(operation)

    async def _agent_result(self, key: str, method: str, *args: object) -> Response:
        async def operation() -> dict[str, object]:
            value = await self.agent.call(method, *args)
            if isinstance(value, (ActiveTimer, CompletedTimer)) or value is None:
                value = _timer_json(value)
            return {key: value}

        return await self._respond(operation)

    async def _respond(
        self, operation: Callable[[], Awaitable[dict[str, object]]]
    ) -> Response:
        try:
            result = await operation()
        except InputError as error:
            return _error("invalid_field", str(error), error.field)
        except ExportDestinationExistsError as error:
            return _error("destination_exists", str(error), "destination", status=409)
        except AgentRequestError as error:
            return _error(error.code, str(error))
        except ValueError as error:
            return _error("validation_failed", str(error))
        return JSONResponse({"data": result})


class InputError(ValueError):
    """A malformed HTTP field with an optional accessible field association."""

    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.field = field


async def _body(request: Request) -> dict[str, object]:
    value = await request.json()
    return cast(dict[str, object], value)


def _text(body: dict[str, object], field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str):
        raise InputError("must be text", field)
    return value


def _optional_text(body: dict[str, object], field: str) -> str | None:
    value = body.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InputError("must be text or null", field)
    return value


def _integer(body: dict[str, object], field: str) -> int:
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError("must be an integer", field)
    return value


def _integer_list(body: dict[str, object], field: str) -> list[int]:
    value = body.get(field)
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise InputError("must be a list of integers", field)
    return cast(list[int], value)


def _number(body: dict[str, object], field: str) -> float:
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError("must be a number", field)
    return float(value)


def _boolean(
    body: dict[str, object], field: str, *, default: bool | None = None
) -> bool:
    value = body.get(field, default)
    if not isinstance(value, bool):
        raise InputError("must be true or false", field)
    return value


def _instant(body: dict[str, object], field: str) -> datetime:
    try:
        value = datetime.fromisoformat(_text(body, field))
    except ValueError as error:
        raise InputError("must be an ISO 8601 date and time", field) from error
    if value.tzinfo is None:
        raise InputError("must include a UTC offset", field)
    return value


def _review_filter(body: dict[str, object]) -> ReviewFilter:
    preset_value = body.get("preset", DatePreset.ALL_TIME.value)
    try:
        preset = DatePreset(cast(str, preset_value))
    except (TypeError, ValueError) as error:
        raise InputError("unknown date preset", "preset") from error
    try:
        custom_start = (
            date.fromisoformat(value)
            if isinstance((value := body.get("start_date")), str) and value
            else None
        )
        custom_end = (
            date.fromisoformat(value)
            if isinstance((value := body.get("end_date")), str) and value
            else None
        )
    except ValueError as error:
        raise InputError("must be an ISO calendar date", "start_date") from error
    return review_filter_for_preset(
        preset,
        today=date.today(),
        custom_start=custom_start,
        custom_end=custom_end,
        project=_optional_text(body, "project"),
        activity=_optional_text(body, "activity"),
    )


def _timer_json(value: object) -> object:
    if value is None:
        return None
    timer = cast(ActiveTimer | CompletedTimer, value)
    data = asdict(timer)
    data["started_at"] = timer.started_at.isoformat()
    if isinstance(timer, CompletedTimer):
        data["stopped_at"] = timer.stopped_at.isoformat()
        data["duration_seconds"] = timer.duration.total_seconds()
    return data


def _dataclass_json(value: object) -> object:
    if value is None:
        return None
    data = asdict(cast(Any, value))
    for key, item in data.items():
        if hasattr(item, "value"):
            data[key] = item.value
        elif isinstance(item, timedelta):
            data[key] = item.total_seconds()
    return data


def _dataclass_list_json(value: object) -> list[object]:
    return [_dataclass_json(item) for item in cast(list[object], value)]


def _error(
    code: str,
    message: str,
    field: str | None = None,
    *,
    status: int = 400,
) -> JSONResponse:
    error: dict[str, object] = {"code": code, "message": message}
    if field is not None:
        error["field"] = field
    return JSONResponse({"error": error}, status_code=status)


async def input_error_response(_request: Request, error: Exception) -> Response:
    """Turn fields parsed before an operation closure into the common envelope."""
    if isinstance(error, InputError):
        return _error("invalid_field", str(error), error.field)
    return _error("validation_failed", str(error))
