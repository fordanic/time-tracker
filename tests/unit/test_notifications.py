import asyncio
from collections.abc import Callable, Sequence

import pytest
from desktop_notifier import Button, Capability

from time_tracker.application.reminders import (
    CheckpointAction,
    Reminder,
    ReminderKind,
    ReminderReason,
)
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
    def __init__(
        self,
        *,
        dispatch: bool,
        capabilities: frozenset[Capability] = frozenset({Capability.BUTTONS}),
    ) -> None:
        self._backend = object()
        self.dispatch = dispatch
        self.capabilities = capabilities
        self.title = ""
        self.message = ""
        self.buttons: tuple[Button, ...] = ()
        self.dispatch_count = 0

    async def request_authorisation(self) -> bool:
        return True

    async def get_capabilities(self) -> frozenset[Capability]:
        return self.capabilities

    async def send(
        self,
        *,
        title: str,
        message: str,
        buttons: Sequence[Button] = (),
        on_dispatched: Callable[[], None],
    ) -> str:
        self.title = title
        self.message = message
        self.buttons = tuple(buttons)
        self.dispatch_count += 1
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


@pytest.mark.asyncio
async def test_active_checkpoint_exposes_all_native_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDesktopNotifier(dispatch=True)
    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "linux"
    )
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: fake)
    service = NativeNotificationService()
    actions: list[tuple[CheckpointAction, str]] = []

    async def handle(action: CheckpointAction, checkpoint_id: str) -> bool:
        actions.append((action, checkpoint_id))
        return True

    service.set_checkpoint_action_handler(handle)
    await service.send(
        Reminder(
            ReminderKind.ACTIVE,
            project="Website",
            activity="Planning",
            checkpoint_id="opaque-token",
            active_entry_id=42,
        )
    )

    assert [button.title for button in fake.buttons] == [
        "Continue",
        "Snooze",
        "Stop",
        "Switch activity",
    ]
    for button in fake.buttons:
        assert button.on_pressed is not None
        button.on_pressed()
    await asyncio.sleep(0)

    assert actions == [
        (CheckpointAction.CONTINUE, "opaque-token"),
        (CheckpointAction.SNOOZE, "opaque-token"),
        (CheckpointAction.STOP, "opaque-token"),
        (CheckpointAction.SWITCH, "opaque-token"),
    ]


@pytest.mark.asyncio
async def test_checkpoint_delivery_without_native_actions_is_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDesktopNotifier(dispatch=True, capabilities=frozenset())
    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "linux"
    )
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: fake)
    service = NativeNotificationService()

    async def handle(_action: CheckpointAction, _checkpoint_id: str) -> bool:
        return True

    service.set_checkpoint_action_handler(handle)

    with pytest.raises(RuntimeError, match="actions are unavailable"):
        await service.send(
            Reminder(
                ReminderKind.ACTIVE,
                checkpoint_id="opaque-token",
                active_entry_id=42,
            )
        )

    assert fake.dispatch_count == 1
    assert fake.buttons == ()


@pytest.mark.asyncio
async def test_macos_passive_fallback_does_not_accept_an_actionless_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDesktopNotifier(dispatch=False)
    fallback: list[tuple[str, str]] = []

    async def send_fallback(title: str, message: str) -> None:
        fallback.append((title, message))

    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "darwin"
    )
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: fake)
    monkeypatch.setattr(notifications, "_send_macos_notification", send_fallback)
    service = NativeNotificationService()

    async def handle(_action: CheckpointAction, _checkpoint_id: str) -> bool:
        return True

    service.set_checkpoint_action_handler(handle)

    with pytest.raises(RuntimeError, match="rejected delivery"):
        await service.send(
            Reminder(
                ReminderKind.ACTIVE,
                checkpoint_id="opaque-token",
                active_entry_id=42,
            )
        )

    assert fallback == [
        (
            "Still tracking time?",
            "Continue, snooze, stop, or switch activity.",
        )
    ]


@pytest.mark.asyncio
async def test_macos_passive_fallback_accepts_an_inactive_reminder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeDesktopNotifier(dispatch=False)
    fallback: list[tuple[str, str]] = []

    async def send_fallback(title: str, message: str) -> None:
        fallback.append((title, message))

    monkeypatch.setattr(
        "time_tracker.infrastructure.notifications.sys.platform", "darwin"
    )
    monkeypatch.setattr(notifications, "DesktopNotifier", lambda **_: fake)
    monkeypatch.setattr(notifications, "_send_macos_notification", send_fallback)
    service = NativeNotificationService()

    await service.send(Reminder(ReminderKind.INACTIVE))

    assert fallback == [
        ("No timer is running", "Start a timer when you begin working.")
    ]


@pytest.fixture(autouse=True)
def not_a_wsl_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep host-dependent delivery out of tests that do not select it."""
    monkeypatch.setattr(notifications, "is_wsl_host", lambda: False)


class FakeToastDispatcher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.title = ""
        self.message = ""
        self.checkpoint_id: str | None = None

    async def send(
        self,
        title: str,
        message: str,
        *,
        checkpoint_id: str | None = None,
    ) -> None:
        self.title = title
        self.message = message
        self.checkpoint_id = checkpoint_id
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
async def test_wsl_active_checkpoint_passes_opaque_action_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toast = FakeToastDispatcher()
    service = wsl_service(
        monkeypatch,
        toast,
        FakeDesktopNotifier(dispatch=True),
    )

    await service.send(
        Reminder(
            ReminderKind.ACTIVE,
            project="Website",
            activity="Planning",
            checkpoint_id="opaque-token",
            active_entry_id=42,
        )
    )

    assert toast.checkpoint_id == "opaque-token"


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
