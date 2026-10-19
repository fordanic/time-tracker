from datetime import UTC, datetime, timedelta

import pytest

from time_tracker.agent.reminders import ReminderCoordinator
from time_tracker.application.reminders import (
    AutoStoppedNotification,
    CheckpointAction,
    Reminder,
    ReminderIntervals,
    ReminderReason,
)
from time_tracker.domain.models import ActiveTimer, CompletedTimer


class ControlledClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class UnusedTrackingService:
    def get_active(self) -> None:
        return None


class RecordingNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.notifications: list[Reminder | AutoStoppedNotification] = []

    async def send(self, value: Reminder | AutoStoppedNotification) -> None:
        if self.fail:
            raise RuntimeError("delivery failed")
        self.notifications.append(value)


def active_timer() -> ActiveTimer:
    return ActiveTimer(7, "Client", "Review", datetime(2026, 7, 20, tzinfo=UTC))


@pytest.mark.asyncio
async def test_two_delivered_unanswered_checkpoints_stop_matching_timer() -> None:
    clock = ControlledClock()
    notifier = RecordingNotifier()
    active = active_timer()
    stopped = active.stop(active.started_at + timedelta(hours=1))
    stop_calls: list[int] = []

    async def stop_matching(entry_id: int) -> CompletedTimer | None:
        stop_calls.append(entry_id)
        return stopped

    coordinator = ReminderCoordinator(
        UnusedTrackingService(),  # type: ignore[arg-type]
        notifier,
        ReminderIntervals(inactive=None, active=None),
        auto_stop_after_unanswered_enabled=True,
        response_grace_seconds=10,
        stop_active=stop_matching,
        monotonic=clock,
        checkpoint_id_factory=iter(("first", "second")).__next__,
    )
    coordinator._active = active  # noqa: SLF001

    await coordinator._present_active_checkpoint(ReminderReason.SCHEDULED)  # noqa: SLF001
    first = coordinator.pending_reminder()
    assert first is not None
    assert first.checkpoint_id == "first"
    clock.value = 10
    await coordinator._expire_unanswered_checkpoint()  # noqa: SLF001
    assert stop_calls == []

    await coordinator._present_active_checkpoint(ReminderReason.END_OF_DAY)  # noqa: SLF001
    clock.value = 20
    await coordinator._expire_unanswered_checkpoint()  # noqa: SLF001

    assert stop_calls == [7]
    assert coordinator.pending_reminder() is None
    assert notifier.notifications[-1] == AutoStoppedNotification(
        "Client", "Review", stopped.stopped_at
    )


@pytest.mark.asyncio
async def test_failed_notification_delivery_does_not_arm_auto_stop() -> None:
    clock = ControlledClock()
    stop_calls: list[int] = []

    async def stop_matching(entry_id: int) -> CompletedTimer | None:
        stop_calls.append(entry_id)
        return None

    coordinator = ReminderCoordinator(
        UnusedTrackingService(),  # type: ignore[arg-type]
        RecordingNotifier(fail=True),
        ReminderIntervals(inactive=None, active=None),
        auto_stop_after_unanswered_enabled=True,
        response_grace_seconds=10,
        stop_active=stop_matching,
        monotonic=clock,
    )
    coordinator._active = active_timer()  # noqa: SLF001

    await coordinator._present_active_checkpoint(ReminderReason.SCHEDULED)  # noqa: SLF001
    clock.value = 100
    await coordinator._expire_unanswered_checkpoint()  # noqa: SLF001

    assert stop_calls == []


@pytest.mark.asyncio
async def test_failed_automatic_stop_leaves_timer_active_without_success_notice() -> (
    None
):
    clock = ControlledClock()
    notifier = RecordingNotifier()

    async def fail_stop(_entry_id: int) -> CompletedTimer | None:
        raise OSError("disk unavailable")

    coordinator = ReminderCoordinator(
        UnusedTrackingService(),  # type: ignore[arg-type]
        notifier,
        ReminderIntervals(inactive=None, active=None),
        auto_stop_after_unanswered_enabled=True,
        response_grace_seconds=10,
        stop_active=fail_stop,
        monotonic=clock,
    )
    coordinator._active = active_timer()  # noqa: SLF001

    await coordinator._present_active_checkpoint(ReminderReason.SCHEDULED)  # noqa: SLF001
    clock.value = 10
    await coordinator._expire_unanswered_checkpoint()  # noqa: SLF001
    await coordinator._present_active_checkpoint(ReminderReason.SCHEDULED)  # noqa: SLF001
    clock.value = 20
    await coordinator._expire_unanswered_checkpoint()  # noqa: SLF001

    assert coordinator._active == active_timer()  # noqa: SLF001
    assert not any(
        isinstance(item, AutoStoppedNotification) for item in notifier.notifications
    )


@pytest.mark.asyncio
async def test_checkpoint_actions_are_bound_to_current_entry_and_identifier() -> None:
    coordinator = ReminderCoordinator(
        UnusedTrackingService(),  # type: ignore[arg-type]
        RecordingNotifier(),
        ReminderIntervals(inactive=None, active=None),
        checkpoint_id_factory=lambda: "current",
    )
    coordinator._active = active_timer()  # noqa: SLF001
    await coordinator._present_active_checkpoint(ReminderReason.LUNCH)  # noqa: SLF001

    assert coordinator.confirm_active("stale") is False
    assert coordinator.request_switch("current") is True
    pending = coordinator.pending_reminder()
    assert pending is not None and pending.switch_requested is True
    assert coordinator.consume_switch_request() is True
    assert coordinator.pending_reminder() is None


@pytest.mark.asyncio
async def test_shared_checkpoint_action_stops_only_the_matching_timer() -> None:
    active = active_timer()
    stopped = active.stop(active.started_at + timedelta(minutes=30))
    stop_calls: list[int] = []

    async def stop_matching(entry_id: int) -> CompletedTimer | None:
        stop_calls.append(entry_id)
        return stopped

    coordinator = ReminderCoordinator(
        UnusedTrackingService(),  # type: ignore[arg-type]
        RecordingNotifier(),
        ReminderIntervals(inactive=None, active=None),
        stop_active=stop_matching,
        checkpoint_id_factory=lambda: "current",
    )
    coordinator._active = active  # noqa: SLF001
    await coordinator._present_active_checkpoint(ReminderReason.LUNCH)  # noqa: SLF001

    assert not await coordinator.perform_checkpoint_action(
        CheckpointAction.STOP,
        "stale",
    )
    assert await coordinator.perform_checkpoint_action(
        CheckpointAction.STOP,
        "current",
    )

    assert stop_calls == [active.entry_id]
    assert coordinator.pending_reminder() is None
    assert not await coordinator.perform_checkpoint_action(
        CheckpointAction.STOP,
        "current",
    )
