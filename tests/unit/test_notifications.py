from collections.abc import Callable

import pytest

from time_tracker.application.reminders import Reminder, ReminderKind, ReminderReason
from time_tracker.infrastructure import notifications
from time_tracker.infrastructure.notifications import (
    NativeNotificationService,
    _macos_notification_command,
)


def test_macos_notification_text_is_passed_as_data_not_script() -> None:
    title = 'Timer "title"'
    message = 'Text\nwith \\ and "quotes"'

    command = _macos_notification_command(title, message)

    assert command[-3] == "--"
    assert command[-2:] == (title, message)
    assert title not in command[2:7]
    assert message not in command[2:7]


class FakeDesktopNotifier:
    def __init__(self, *, dispatch: bool) -> None:
        self._backend = object()
        self.dispatch = dispatch
        self.title = ""
        self.message = ""

    async def request_authorisation(self) -> bool:
        return True

    async def send(
        self,
        *,
        title: str,
        message: str,
        on_dispatched: Callable[[], None],
    ) -> str:
        self.title = title
        self.message = message
        if self.dispatch:
            on_dispatched()
        return f"{title}: {message}"


@pytest.mark.asyncio
async def test_desktop_delivery_failure_is_not_silently_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDesktopNotifier(dispatch=False)
    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "linux"
    )
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: fake)
    service = NativeNotificationService()

    with pytest.raises(RuntimeError, match="rejected delivery"):
        await service.send(Reminder(ReminderKind.INACTIVE))


@pytest.mark.asyncio
async def test_desktop_delivery_callback_confirms_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDesktopNotifier(dispatch=True)
    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "linux"
    )
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: fake)
    service = NativeNotificationService()

    await service.send(Reminder(ReminderKind.INACTIVE))


@pytest.mark.asyncio
async def test_idle_triggered_notification_identifies_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDesktopNotifier(dispatch=True)
    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "linux"
    )
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: fake)
    service = NativeNotificationService()

    await service.send(
        Reminder(
            ReminderKind.ACTIVE,
            project="Website",
            activity="Planning",
            reason=ReminderReason.IDLE,
            idle_threshold_minutes=15,
        )
    )

    assert fake.title == "Still tracking Website / Planning?"
    assert "idle for at least 15 minutes" in fake.message


@pytest.fixture(autouse=True)
def not_a_wsl_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep host-dependent delivery out of tests that do not select it."""
    monkeypatch.setattr(notifications, "is_wsl_host", lambda: False)


class FakeToastDispatcher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.title = ""
        self.message = ""

    async def send(self, title: str, message: str) -> None:
        self.title = title
        self.message = message
        if self.error is not None:
            raise self.error


def wsl_service(
    monkeypatch: pytest.MonkeyPatch,
    toast: FakeToastDispatcher,
    notifier: FakeDesktopNotifier,
) -> NativeNotificationService:
    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "linux"
    )
    monkeypatch.setattr(notifications, "is_wsl_host", lambda: True)
    monkeypatch.setattr(notifications, "WindowsToastDispatcher", lambda: toast)
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: notifier)
    return NativeNotificationService()


@pytest.mark.asyncio
async def test_wsl_host_delivers_the_shared_reminder_text_as_a_toast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toast = FakeToastDispatcher()
    notifier = FakeDesktopNotifier(dispatch=True)
    service = wsl_service(monkeypatch, toast, notifier)

    await service.send(
        Reminder(
            ReminderKind.ACTIVE,
            project="Website",
            activity="Planning",
            reason=ReminderReason.IDLE,
            idle_threshold_minutes=15,
        )
    )

    assert toast.title == "Still tracking Website / Planning?"
    assert "idle for at least 15 minutes" in toast.message
    assert notifier.title == ""


@pytest.mark.asyncio
async def test_wsl_toast_failure_falls_back_to_the_desktop_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toast = FakeToastDispatcher(error=RuntimeError("interpreter was not found"))
    notifier = FakeDesktopNotifier(dispatch=True)
    service = wsl_service(monkeypatch, toast, notifier)

    await service.send(Reminder(ReminderKind.INACTIVE))

    assert notifier.title == "No timer is running"


@pytest.mark.asyncio
async def test_wsl_reports_the_toast_failure_when_both_paths_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toast = FakeToastDispatcher(error=RuntimeError("Windows rejected the toast"))
    notifier = FakeDesktopNotifier(dispatch=False)
    service = wsl_service(monkeypatch, toast, notifier)

    with pytest.raises(RuntimeError, match="Windows rejected the toast"):
        await service.send(Reminder(ReminderKind.INACTIVE))
