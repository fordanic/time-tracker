"""Single-writer background process for tracking and reminders."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from dataclasses import asdict, replace
from datetime import date, datetime
from multiprocessing import AuthenticationError
from multiprocessing.connection import Listener
from pathlib import Path
from typing import cast

from time_tracker.agent.reminders import ReminderCoordinator
from time_tracker.application.configuration import (
    ConfigurationService,
    ReminderSettings,
)
from time_tracker.application.exporting import (
    ExportDestinationExistsError,
    ExportService,
)
from time_tracker.application.idle import IdleDetectionStatus, IdleDetector
from time_tracker.application.reminders import Reminder, ReminderIntervals, ReminderKind
from time_tracker.application.reporting import ReviewFilter
from time_tracker.application.tracking import TrackingService
from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.infrastructure.configuration import (
    TomlConfigurationStore,
    load_config,
)
from time_tracker.infrastructure.csv_export import (
    CsvCompletedEntryWriter,
    CsvDailySummaryWriter,
    CsvRangeSummaryWriter,
)
from time_tracker.infrastructure.idle_detection import create_idle_detector
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
    idle_detector: IdleDetector | None = None,
    idle_poll_seconds: float = 15.0,
) -> None:
    """Serve one authenticated foreground connection at a time."""
    paths.prepare()
    with instance_lock(paths.lock):
        _serve_locked(
            paths,
            notifier,
            reminder_intervals,
            idle_detector,
            idle_poll_seconds,
        )


def _serve_locked(
    paths: AgentPaths,
    notifier: NotificationService | None,
    reminder_intervals: ReminderIntervals | None,
    idle_detector: IdleDetector | None,
    idle_poll_seconds: float,
) -> None:
    """Own the endpoint and database while the instance lock is held."""
    loaded_config = load_config(paths.config)
    config = (
        replace(
            loaded_config,
            reminder_settings=ReminderSettings.from_intervals(reminder_intervals),
        )
        if reminder_intervals is not None
        else loaded_config
    )
    settings = config.reminder_settings
    configuration_service = ConfigurationService(
        TomlConfigurationStore(paths.config),
        config,
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
    repository = SQLiteTimerRepository(paths.database)
    service = TrackingService(repository)
    export_service = ExportService(
        repository,
        CsvCompletedEntryWriter(),
        CsvDailySummaryWriter(),
        range_writer=CsvRangeSummaryWriter(),
        delimiter=configuration_service.get_export_delimiter,
    )
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
                export_service,
                configuration_service,
                notification_service,
                settings,
                idle_detector,
                idle_poll_seconds,
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
    export_service: ExportService,
    configuration_service: ConfigurationService,
    notifier: NotificationService,
    reminder_settings: ReminderSettings,
    idle_detector: IdleDetector | None,
    idle_poll_seconds: float,
) -> None:
    """Keep reminder scheduling responsive while IPC and SQLite block in threads."""
    coordinator = ReminderCoordinator(
        service,
        notifier,
        reminder_settings.intervals,
        window=reminder_settings.window,
        snooze_seconds=reminder_settings.snooze_seconds,
        idle_enabled=reminder_settings.idle_enabled,
        idle_threshold_minutes=reminder_settings.idle_threshold_minutes,
        idle_detector=idle_detector,
        idle_detector_factory=(
            None if idle_detector is not None else create_idle_detector
        ),
        idle_poll_seconds=idle_poll_seconds,
    )
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
                    active_confirmed,
                    reminder_snoozed,
                    active_edited,
                    reloaded_settings,
                ) = await asyncio.to_thread(
                    _handle_request,
                    request_bytes,
                    service,
                    export_service,
                    configuration_service,
                    coordinator.pending_reminder(),
                    coordinator.idle_detection_status(),
                )
                if reloaded_settings is not None:
                    coordinator.reload_settings(
                        reloaded_settings.intervals,
                        reloaded_settings.window,
                        reloaded_settings.snooze_seconds,
                        reloaded_settings.idle_enabled,
                        reloaded_settings.idle_threshold_minutes,
                    )
                if active_confirmed:
                    coordinator.confirm_active()
                if reminder_snoozed:
                    coordinator.snooze()
                if active_edited:
                    edited_active = await asyncio.to_thread(service.get_active)
                    if edited_active is not None:
                        coordinator.active_edited(edited_active)
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
    export_service: ExportService,
    configuration_service: ConfigurationService,
    pending_reminder: Reminder | None = None,
    idle_detection_status: IdleDetectionStatus | None = None,
) -> tuple[
    dict[str, object],
    bool,
    bool,
    bool,
    bool,
    bool,
    bool,
    ReminderSettings | None,
]:
    request_id: object = None
    reloaded_settings: ReminderSettings | None = None
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
        elif method == "get_reminder":
            result = _reminder_dict(pending_reminder)
        elif method == "confirm_active_reminder":
            result = (
                pending_reminder is not None
                and pending_reminder.kind is ReminderKind.ACTIVE
            )
        elif method == "snooze_reminder":
            result = pending_reminder is not None
        elif method == "get_configuration":
            result = _settings_dict(configuration_service.get())
        elif method == "get_theme":
            result = configuration_service.get_theme()
        elif method == "get_export_delimiter":
            result = configuration_service.get_export_delimiter()
        elif method == "get_idle_detection_status":
            result = asdict(idle_detection_status or IdleDetectionStatus(False))
        elif method == "save_configuration":
            settings = configuration_service.save(
                ReminderSettings(
                    inactive_enabled=_required_bool(params, "inactive_enabled"),
                    inactive_interval_minutes=_required_number(
                        params, "inactive_interval_minutes"
                    ),
                    active_enabled=_required_bool(params, "active_enabled"),
                    active_interval_minutes=_required_number(
                        params, "active_interval_minutes"
                    ),
                    window_enabled=_required_bool(params, "window_enabled"),
                    window_weekdays=_required_int_tuple(params, "window_weekdays"),
                    window_start=_required_str(params, "window_start"),
                    window_end=_required_str(params, "window_end"),
                    snooze_minutes=_required_number(params, "snooze_minutes"),
                    idle_enabled=_required_bool(params, "idle_enabled"),
                    idle_threshold_minutes=_required_number(
                        params, "idle_threshold_minutes"
                    ),
                )
            )
            result = _settings_dict(settings)
            reloaded_settings = settings
        elif method == "save_theme":
            result = configuration_service.save_theme(_required_str(params, "theme"))
        elif method == "save_export_delimiter":
            result = configuration_service.save_export_delimiter(
                _required_str(params, "delimiter")
            )
        elif method == "list_projects":
            result = service.list_projects()
        elif method == "list_activities":
            result = service.list_activities(_required_str(params, "project"))
        elif method == "list_completed":
            result = [_timer_dict(timer) for timer in service.list_completed()]
        elif method == "correct_completed":
            result = _timer_dict(
                service.correct_completed(
                    _required_int(params, "entry_id"),
                    _required_str(params, "project"),
                    _required_str(params, "activity"),
                    _required_datetime(params, "started_at"),
                    _required_datetime(params, "stopped_at"),
                    _optional_str(params, "note"),
                )
            )
        elif method == "delete_completed":
            result = _timer_dict(
                service.delete_completed(_required_int(params, "entry_id"))
            )
        elif method == "create_manual_entry":
            result = _timer_dict(
                service.create_manual_entry(
                    _required_str(params, "project"),
                    _required_str(params, "activity"),
                    _required_datetime(params, "started_at"),
                    _required_datetime(params, "stopped_at"),
                    _optional_str(params, "note"),
                )
            )
        elif method == "edit_active":
            result = _timer_dict(
                service.edit_active(
                    _required_str(params, "project"),
                    _required_str(params, "activity"),
                    _optional_str(params, "note"),
                )
            )
        elif method == "list_recent_activities":
            result = [asdict(pair) for pair in service.list_recent_activities()]
        elif method == "get_start_action":
            result = service.get_start_action(
                _required_str(params, "project"),
                _required_str(params, "activity"),
                _optional_str(params, "note"),
            ).value
        elif method == "get_archive_project_target":
            result = {
                "project": service.get_archive_project_target(
                    _required_str(params, "project")
                )
            }
        elif method == "get_archive_activity_target":
            project, activity = service.get_archive_activity_target(
                _required_str(params, "project"),
                _required_str(params, "activity"),
            )
            result = {"project": project, "activity": activity}
        elif method == "list_archived_projects":
            result = service.list_archived_projects()
        elif method == "list_archived_activities":
            result = [asdict(item) for item in service.list_archived_activities()]
        elif method == "archive_project":
            result = {
                "project": service.archive_project(_required_str(params, "project"))
            }
        elif method == "archive_activity":
            project, activity = service.archive_activity(
                _required_str(params, "project"),
                _required_str(params, "activity"),
            )
            result = {"project": project, "activity": activity}
        elif method == "unarchive_project":
            result = {
                "project": service.unarchive_project(_required_str(params, "project"))
            }
        elif method == "unarchive_activity":
            project, activity = service.unarchive_activity(
                _required_str(params, "project"),
                _required_str(params, "activity"),
            )
            result = {"project": project, "activity": activity}
        elif method == "create_project":
            result = {
                "project": service.create_project(_required_str(params, "project"))
            }
        elif method == "create_activity":
            project, activity = service.create_activity(
                _required_str(params, "project"),
                _required_str(params, "activity"),
            )
            result = {"project": project, "activity": activity}
        elif method == "export_completed":
            result = {
                "entry_count": export_service.export_completed(
                    Path(_required_str(params, "destination")),
                    overwrite=_required_bool(params, "overwrite"),
                    review_filter=_review_filter_from_params(params),
                )
            }
        elif method == "export_daily_summaries":
            result = {
                "summary_count": export_service.export_daily_summaries(
                    Path(_required_str(params, "destination")),
                    overwrite=_required_bool(params, "overwrite"),
                    review_filter=_review_filter_from_params(params),
                )
            }
        elif method == "export_range_summaries":
            result = {
                "summary_count": export_service.export_range_summaries(
                    Path(_required_str(params, "destination")),
                    overwrite=_required_bool(params, "overwrite"),
                    review_filter=_review_filter_from_params(params),
                )
            }
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
            return (
                {"request_id": request_id, "result": result},
                False,
                False,
                False,
                False,
                False,
                False,
                None,
            )
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
            method == "confirm_active_reminder" and result is True,
            method == "snooze_reminder" and result is True,
            method == "edit_active",
            reloaded_settings,
        )
    except ExportDestinationExistsError as error:
        return (
            {
                "request_id": request_id,
                "error": {"code": "destination_exists", "message": str(error)},
            },
            True,
            False,
            False,
            False,
            False,
            False,
            None,
        )
    except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError) as error:
        return (
            {
                "request_id": request_id,
                "error": {"code": "invalid_request", "message": str(error)},
            },
            True,
            False,
            False,
            False,
            False,
            False,
            None,
        )


def _timer_dict(timer: ActiveTimer | CompletedTimer | None) -> object:
    if timer is None:
        return None
    values = asdict(timer)
    values["started_at"] = timer.started_at.isoformat()
    if isinstance(timer, CompletedTimer):
        values["stopped_at"] = timer.stopped_at.isoformat()
    return values


def _reminder_dict(reminder: Reminder | None) -> object:
    if reminder is None:
        return None
    return {
        "kind": reminder.kind.value,
        "project": reminder.project,
        "activity": reminder.activity,
        "reason": reminder.reason.value,
        "idle_threshold_minutes": reminder.idle_threshold_minutes,
    }


def _settings_dict(settings: ReminderSettings) -> dict[str, object]:
    return asdict(settings)


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


def _required_bool(params: dict[str, object], name: str) -> bool:
    value = params.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _required_int(params: dict[str, object], name: str) -> int:
    value = params.get(name)
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _required_int_tuple(params: dict[str, object], name: str) -> tuple[int, ...]:
    value = params.get(name)
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise ValueError(f"{name} must be an integer array")
    return tuple(value)


def _required_number(params: dict[str, object], name: str) -> float:
    value = params.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _required_datetime(params: dict[str, object], name: str) -> datetime:
    value = _required_str(params, name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a UTC offset")
    return parsed


def _review_filter_from_params(params: dict[str, object]) -> ReviewFilter:
    start_value = _optional_str(params, "filter_start_date")
    end_value = _optional_str(params, "filter_end_date")
    try:
        start_date = (
            date.fromisoformat(start_value) if start_value is not None else None
        )
        end_date = date.fromisoformat(end_value) if end_value is not None else None
    except ValueError as error:
        raise ValueError("filter dates must use ISO 8601 YYYY-MM-DD format") from error
    return ReviewFilter(
        start_date=start_date,
        end_date=end_date,
        project=_optional_str(params, "filter_project"),
        activity=_optional_str(params, "filter_activity"),
    )
