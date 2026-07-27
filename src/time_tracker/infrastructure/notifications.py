"""Native desktop notification adapter."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Protocol

from desktop_notifier import DesktopNotifier

from time_tracker.application.reminders import Reminder, ReminderKind, ReminderReason
from time_tracker.infrastructure.wsl_toast import WindowsToastDispatcher, is_wsl_host

logger = logging.getLogger(__name__)


class NotificationService(Protocol):
    """Asynchronous boundary used by the background reminder scheduler."""

    async def send(self, reminder: Reminder) -> None:
        """Deliver one reminder, or raise when the platform rejects it."""
        ...


class NativeNotificationService:
    """Deliver simple notifications through the host desktop service."""

    def __init__(self) -> None:
        self._notifier = (
            None
            if sys.platform == "darwin"
            else DesktopNotifier(app_name="Time Tracker", app_icon=None)
        )
        self._toast = WindowsToastDispatcher() if is_wsl_host() else None

    async def send(self, reminder: Reminder) -> None:
        """Deliver an active or inactive timer reminder."""
        title, message = _reminder_text(reminder)
        if sys.platform == "darwin":
            await _send_macos_notification(title, message)
            return
        if self._toast is not None:
            # A WSL distribution provides no notification daemon, so the Windows
            # desktop is the target. Keep the desktop service as a fallback for a
            # user who runs their own daemon inside WSL.
            try:
                await self._toast.send(title, message)
                return
            except (OSError, RuntimeError) as error:
                logger.warning("Windows toast delivery failed: %s", error)
                toast_error = error
            try:
                await self._send_desktop_service(title, message)
            except Exception:
                raise toast_error from None
            return
        await self._send_desktop_service(title, message)

    async def _send_desktop_service(self, title: str, message: str) -> None:
        """Deliver through the host's desktop notification service."""
        if self._notifier is None:
            raise RuntimeError("native notification service was not initialized")
        backend = self._notifier._backend  # noqa: SLF001
        if type(backend).__module__ == "desktop_notifier.backends.dummy":
            raise RuntimeError("native notifications are unavailable on this platform")
        if not await self._notifier.request_authorisation():
            raise RuntimeError("native notification permission was not granted")
        dispatched = False

        def mark_dispatched() -> None:
            nonlocal dispatched
            dispatched = True

        await self._notifier.send(
            title=title,
            message=message,
            on_dispatched=mark_dispatched,
        )
        if not dispatched:
            raise RuntimeError("the desktop notification service rejected delivery")


def _reminder_text(reminder: Reminder) -> tuple[str, str]:
    """Build the platform-independent reminder title and message."""
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
    else:
        message = "The timer is still running. Open Time Tracker to stop or switch."
    return (title, message)


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
