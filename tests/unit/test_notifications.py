from collections.abc import Callable

import pytest

from time_tracker.application.reminders import Reminder, ReminderKind
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

    async def request_authorisation(self) -> bool:
        return True

    async def send(
        self,
        *,
        title: str,
        message: str,
        on_dispatched: Callable[[], None],
    ) -> str:
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
