"""Native desktop notification adapter."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from desktop_notifier import Button, Capability, DesktopNotifier

from time_tracker.application.reminders import (
    AutoStoppedNotification,
    CheckpointAction,
    Reminder,
    ReminderKind,
    ReminderReason,
)
from time_tracker.infrastructure.wsl_toast import WindowsToastDispatcher, is_wsl_host

logger = logging.getLogger(__name__)

CheckpointActionHandler = Callable[[CheckpointAction, str], Awaitable[bool]]


class NotificationService(Protocol):
    """Asynchronous boundary used by the background reminder scheduler."""

    async def send(self, reminder: Reminder | AutoStoppedNotification) -> None:
        """Deliver one reminder, or raise when the platform rejects it."""
        ...


@runtime_checkable
class CheckpointActionNotificationService(Protocol):
    """Notification adapter that can route native checkpoint actions."""

    def set_checkpoint_action_handler(
        self,
        handler: CheckpointActionHandler,
    ) -> None:
        """Bind actions to the agent-owned checkpoint operation."""
        ...


class NativeNotificationService:
    """Deliver native notifications and route supported checkpoint actions."""

    def __init__(self) -> None:
        self._notifier = DesktopNotifier(app_name="Time Tracker", app_icon=None)
        self._toast = WindowsToastDispatcher() if is_wsl_host() else None
        self._checkpoint_action_handler: CheckpointActionHandler | None = None
        self._action_tasks: set[asyncio.Future[bool]] = set()

    def set_checkpoint_action_handler(
        self,
        handler: CheckpointActionHandler,
    ) -> None:
        """Bind notification buttons to the authoritative agent operation."""
        self._checkpoint_action_handler = handler

    async def send(self, reminder: Reminder | AutoStoppedNotification) -> None:
        """Deliver an active or inactive timer reminder."""
        title, message = _reminder_text(reminder)
        if self._toast is not None:
            # A WSL distribution provides no notification daemon, so the Windows
            # desktop is the target. Keep the desktop service as a fallback for a
            # user who runs their own daemon inside WSL.
            try:
                checkpoint_id = (
                    reminder.checkpoint_id if isinstance(reminder, Reminder) else None
                )
                await self._toast.send(
                    title,
                    message,
                    checkpoint_id=checkpoint_id,
                )
                return
            except (OSError, RuntimeError) as error:
                logger.warning("Windows toast delivery failed: %s", error)
                toast_error = error
            try:
                await self._send_desktop_service(
                    title,
                    message,
                    reminder=reminder,
                )
            except Exception:
                raise toast_error from None
            return
        try:
            await self._send_desktop_service(title, message, reminder=reminder)
        except Exception as native_error:
            if sys.platform != "darwin":
                raise
            logger.warning(
                "macOS native notification delivery failed; using passive fallback: %s",
                native_error,
            )
            try:
                await _send_macos_notification(title, message)
            except Exception as fallback_error:
                raise fallback_error from native_error
            if _is_active_checkpoint(reminder):
                raise native_error

    async def _send_desktop_service(
        self,
        title: str,
        message: str,
        *,
        reminder: Reminder | AutoStoppedNotification,
    ) -> None:
        """Deliver through the host's desktop notification service."""
        backend = self._notifier._backend  # noqa: SLF001
        if type(backend).__module__ == "desktop_notifier.backends.dummy":
            raise RuntimeError("native notifications are unavailable on this platform")
        if not await self._notifier.request_authorisation():
            raise RuntimeError("native notification permission was not granted")
        buttons = self._checkpoint_buttons(reminder)
        if buttons:
            capabilities = await self._notifier.get_capabilities()
            if Capability.BUTTONS not in capabilities:
                await self._dispatch_desktop_notification(title, message)
                raise RuntimeError(
                    "native notification actions are unavailable on this platform"
                )
        await self._dispatch_desktop_notification(
            title,
            message,
            buttons=buttons,
        )

    async def _dispatch_desktop_notification(
        self,
        title: str,
        message: str,
        *,
        buttons: tuple[Button, ...] = (),
    ) -> None:
        """Dispatch once and verify that the backend accepted the request."""
        dispatched = False

        def mark_dispatched() -> None:
            nonlocal dispatched
            dispatched = True

        await self._notifier.send(
            title=title,
            message=message,
            buttons=buttons,
            on_dispatched=mark_dispatched,
        )
        if not dispatched:
            raise RuntimeError("the desktop notification service rejected delivery")

    def _checkpoint_buttons(
        self,
        reminder: Reminder | AutoStoppedNotification,
    ) -> tuple[Button, ...]:
        if not _is_active_checkpoint(reminder):
            return ()
        handler = self._checkpoint_action_handler
        if handler is None:
            raise RuntimeError("native checkpoint action handling is unavailable")
        assert isinstance(reminder, Reminder)
        assert reminder.checkpoint_id is not None
        return tuple(
            Button(
                title=title,
                identifier=f"time-tracker-{action.value}",
                on_pressed=self._button_callback(action, reminder.checkpoint_id),
            )
            for title, action in (
                ("Continue", CheckpointAction.CONTINUE),
                ("Snooze", CheckpointAction.SNOOZE),
                ("Stop", CheckpointAction.STOP),
                ("Switch activity", CheckpointAction.SWITCH),
            )
        )

    def _button_callback(
        self,
        action: CheckpointAction,
        checkpoint_id: str,
    ) -> Callable[[], None]:
        def invoke() -> None:
            handler = self._checkpoint_action_handler
            if handler is None:
                logger.warning("native checkpoint action handler is unavailable")
                return
            task: asyncio.Future[bool] = asyncio.ensure_future(
                handler(action, checkpoint_id)
            )
            self._action_tasks.add(task)
            task.add_done_callback(self._checkpoint_action_finished)

        return invoke

    def _checkpoint_action_finished(self, task: asyncio.Future[bool]) -> None:
        self._action_tasks.discard(task)
        try:
            accepted = task.result()
        except Exception:
            logger.exception("native checkpoint action failed")
            return
        if not accepted:
            logger.info("ignored stale native checkpoint action")


def _reminder_text(
    reminder: Reminder | AutoStoppedNotification,
) -> tuple[str, str]:
    """Build the platform-independent reminder title and message."""
    if isinstance(reminder, AutoStoppedNotification):
        target = f"{reminder.project} / {reminder.activity}"
        stopped_at = reminder.stopped_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        return (
            f"Stopped {target}",
            f"Stopped automatically at {stopped_at} after two unanswered "
            "checkpoints. Open Review if this needs correction.",
        )
    if reminder.kind is not ReminderKind.ACTIVE:
        return ("No timer is running", "Start a timer when you begin working.")
    target = " / ".join(part for part in (reminder.project, reminder.activity) if part)
    title = f"Still tracking {target}?" if target else "Still tracking time?"
    if reminder.reason is ReminderReason.IDLE:
        threshold = _format_minutes(reminder.idle_threshold_minutes or 0)
        message = (
            f"The computer was idle for at least {threshold} minutes. "
            "Open Time Tracker to confirm, snooze, or stop."
        )
    elif reminder.reason is ReminderReason.LUNCH:
        message = "Lunch checkpoint. Continue, snooze, stop, or switch activity."
    elif reminder.reason is ReminderReason.END_OF_DAY:
        message = "End-of-day checkpoint. Continue, snooze, stop, or switch activity."
    else:
        message = "Continue, snooze, stop, or switch activity."
    return (title, message)


def _is_active_checkpoint(
    reminder: Reminder | AutoStoppedNotification,
) -> bool:
    return (
        isinstance(reminder, Reminder)
        and reminder.kind is ReminderKind.ACTIVE
        and reminder.checkpoint_id is not None
    )


def _format_minutes(value: float) -> str:
    return format(float(value), ".15g")


async def _send_macos_notification(title: str, message: str) -> None:
    """Dispatch safely through macOS's built-in AppleScript notification command."""
    process = await asyncio.create_subprocess_exec(
        *_macos_notification_command(title, message),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "macOS rejected the native notification")


def _macos_notification_command(title: str, message: str) -> tuple[str, ...]:
    """Keep user-controlled reminder text out of executable AppleScript source."""
    return (
        "/usr/bin/osascript",
        "-e",
        "on run argv",
        "-e",
        "display notification (item 2 of argv) with title (item 1 of argv)",
        "-e",
        "end run",
        "--",
        title,
        message,
    )
