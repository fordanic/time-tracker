"""Async checkpoint coordination owned by the background process."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime

from time_tracker.application.idle import (
    IdleDetectionStatus,
    IdleDetector,
    IdleEpisodeMonitor,
)
from time_tracker.application.reminders import (
    AutoStoppedNotification,
    CheckpointAction,
    Reminder,
    ReminderIntervals,
    ReminderKind,
    ReminderReason,
    ReminderSchedule,
    ReminderWindow,
    ScheduledCheckpoint,
    ScheduledCheckpointSchedule,
    new_checkpoint_id,
)
from time_tracker.application.tracking import TrackingService
from time_tracker.domain.models import ActiveTimer, CompletedTimer
from time_tracker.infrastructure.notifications import NotificationService

logger = logging.getLogger(__name__)

StopActive = Callable[[int], Awaitable[CompletedTimer | None]]


class ReminderCoordinator:
    """Schedule checkpoints independently of foreground IPC connections."""

    def __init__(
        self,
        service: TrackingService,
        notifier: NotificationService,
        intervals: ReminderIntervals | None = None,
        *,
        window: ReminderWindow | None = None,
        snooze_seconds: float = 10 * 60,
        idle_enabled: bool = False,
        idle_threshold_minutes: float = 15.0,
        idle_detector: IdleDetector | None = None,
        idle_detector_factory: Callable[[], IdleDetector | None] | None = None,
        idle_poll_seconds: float = 15.0,
        safeguard_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4),
        scheduled_checkpoints: tuple[ScheduledCheckpoint, ...] = (),
        auto_stop_after_unanswered_enabled: bool = False,
        response_grace_seconds: float = 5 * 60,
        stop_active: StopActive | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] | None = None,
        utc_clock: Callable[[], datetime] | None = None,
        checkpoint_id_factory: Callable[[], str] = new_checkpoint_id,
    ) -> None:
        if response_grace_seconds <= 0:
            raise ValueError("checkpoint response grace must be positive")
        self._service = service
        self._notifier = notifier
        self._monotonic = monotonic
        self._wall_clock = wall_clock or (lambda: datetime.now().astimezone())
        self._schedule = ReminderSchedule(
            intervals,
            monotonic,
            window=window,
            wall_clock=self._wall_clock,
        )
        self._safeguards = ScheduledCheckpointSchedule(
            safeguard_weekdays,
            scheduled_checkpoints,
            monotonic,
            wall_clock=self._wall_clock,
        )
        self._snooze_seconds = snooze_seconds
        self._idle_enabled = idle_enabled
        self._idle_threshold_minutes = idle_threshold_minutes
        self._idle_monitor = IdleEpisodeMonitor(idle_threshold_minutes * 60)
        self._idle_detector_factory = idle_detector_factory
        self._idle_detector = idle_detector or _safe_create_idle_detector(
            idle_detector_factory
        )
        self._idle_poll_seconds = idle_poll_seconds
        self._auto_stop_enabled = auto_stop_after_unanswered_enabled
        self._response_grace_seconds = response_grace_seconds
        self._stop_active = stop_active or self._stop_active_directly
        self._utc_clock = utc_clock or (lambda: datetime.now(UTC))
        self._checkpoint_id_factory = checkpoint_id_factory
        self._active: ActiveTimer | None = None
        self._changed = asyncio.Event()
        self._generation = 0
        self._pending: Reminder | None = None
        self._response_deadline: float | None = None
        self._unanswered_count = 0
        self._stopping = False

    def timer_changed(self) -> None:
        """Wake the scheduler after a successfully persisted transition."""
        self._clear_checkpoint(reset_unanswered=True)
        self._generation += 1
        self._changed.set()

    def pending_reminder(self) -> Reminder | None:
        """Return the latest due reminder for a connected foreground client."""
        return self._pending

    def idle_detection_status(self) -> IdleDetectionStatus:
        """Return current platform adapter availability."""
        return IdleDetectionStatus(self._idle_detector is not None)

    def active_edited(self, active: ActiveTimer) -> None:
        """Refresh names and treat the edit as an active checkpoint response."""
        self._schedule.update_active_details(active.project, active.activity)
        self._active = active
        self._clear_checkpoint(reset_unanswered=True)
        self._changed.set()

    def reload_settings(
        self,
        intervals: ReminderIntervals,
        window: ReminderWindow | None,
        snooze_seconds: float,
        idle_enabled: bool,
        idle_threshold_minutes: float,
        safeguard_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4),
        scheduled_checkpoints: tuple[ScheduledCheckpoint, ...] = (),
        auto_stop_after_unanswered_enabled: bool = False,
    ) -> None:
        """Apply durable settings and reset checkpoint schedules."""
        self._schedule.replace_intervals(intervals)
        self._schedule.replace_window(window)
        self._safeguards = ScheduledCheckpointSchedule(
            safeguard_weekdays,
            scheduled_checkpoints,
            self._monotonic,
            wall_clock=self._wall_clock,
        )
        self._snooze_seconds = snooze_seconds
        self._idle_enabled = idle_enabled
        self._idle_threshold_minutes = idle_threshold_minutes
        self._auto_stop_enabled = auto_stop_after_unanswered_enabled
        self._idle_monitor = IdleEpisodeMonitor(idle_threshold_minutes * 60)
        self._idle_monitor.reset(establish_baseline=True)
        if self._idle_detector_factory is not None:
            self._idle_detector = _safe_create_idle_detector(
                self._idle_detector_factory
            )
        self._clear_checkpoint(reset_unanswered=True)
        self._generation += 1
        self._changed.set()

    def checkpoint_matches(self, checkpoint_id: str) -> bool:
        """Return whether an opaque identifier names the current active checkpoint."""
        pending = self._pending
        active = self._active
        return (
            pending is not None
            and pending.kind is ReminderKind.ACTIVE
            and pending.checkpoint_id == checkpoint_id
            and active is not None
            and pending.active_entry_id == active.entry_id
        )

    def confirm_active(self, checkpoint_id: str | None = None) -> bool:
        """Clear an active checkpoint and restart its interval from now."""
        if not self._accepts_active_action(checkpoint_id):
            return False
        self._clear_checkpoint(reset_unanswered=True)
        self._idle_monitor.reset(establish_baseline=True)
        self._generation += 1
        self._changed.set()
        return True

    def snooze(self, checkpoint_id: str | None = None) -> bool:
        """Clear a checkpoint and defer it without changing timer state."""
        if self._pending is None:
            return False
        if checkpoint_id is not None and not self.checkpoint_matches(checkpoint_id):
            return False
        pending = self._pending
        self._clear_checkpoint(reset_unanswered=True)
        self._schedule.snooze(
            self._snooze_seconds,
            reason=pending.reason,
            idle_threshold_minutes=pending.idle_threshold_minutes,
        )
        self._changed.set()
        return True

    def request_switch(self, checkpoint_id: str) -> bool:
        """Mark a valid checkpoint so the foreground focuses recent work."""
        if not self.checkpoint_matches(checkpoint_id):
            return False
        assert self._pending is not None
        self._pending = replace(self._pending, switch_requested=True)
        self._response_deadline = None
        self._unanswered_count = 0
        self._changed.set()
        return True

    def consume_switch_request(self) -> bool:
        """Consume one foreground switch request from the current checkpoint."""
        if self._pending is None or not self._pending.switch_requested:
            return False
        self._clear_checkpoint(reset_unanswered=True)
        return True

    async def perform_checkpoint_action(
        self,
        action: CheckpointAction,
        checkpoint_id: str,
    ) -> bool:
        """Apply one conditional foreground or native-notification action."""
        if action is CheckpointAction.CONTINUE:
            return self.confirm_active(checkpoint_id)
        if action is CheckpointAction.SNOOZE:
            return self.snooze(checkpoint_id)
        if action is CheckpointAction.SWITCH:
            return self.request_switch(checkpoint_id)
        if not self.checkpoint_matches(checkpoint_id):
            return False
        pending = self._pending
        expected_entry_id = pending.active_entry_id if pending is not None else None
        if expected_entry_id is None:
            return False
        stopped = await self._stop_active(expected_entry_id)
        if stopped is None:
            return False
        self.timer_changed()
        return True

    def stop(self) -> None:
        """Wake and stop the scheduler without modifying timer state."""
        self._stopping = True
        self._changed.set()

    async def run(self) -> None:
        """Run until stopped, resetting intervals after timer transitions."""
        await self._reset_from_storage(establish_idle_baseline=False)
        seen_generation = self._generation
        while not self._stopping:
            timeout = _minimum_timeout(
                self._schedule.seconds_until_due(),
                self._safeguards.seconds_until_due(),
                self._seconds_until_response_deadline(),
                self._idle_poll_seconds if self._should_poll_idle() else None,
            )
            self._changed.clear()
            if self._generation != seen_generation:
                await self._reset_from_storage(establish_idle_baseline=True)
                seen_generation = self._generation
                continue
            try:
                if timeout is None:
                    await self._changed.wait()
                else:
                    await asyncio.wait_for(self._changed.wait(), timeout=timeout)
            except TimeoutError:
                await self._handle_due_work()
            else:
                if not self._stopping and self._generation != seen_generation:
                    await self._reset_from_storage(establish_idle_baseline=True)
                    seen_generation = self._generation

    async def _handle_due_work(self) -> None:
        await self._expire_unanswered_checkpoint()
        await self._poll_idle()
        safeguard_reason = self._safeguards.take_due(active=self._active is not None)
        if safeguard_reason is not None and self._pending is None:
            await self._present_active_checkpoint(safeguard_reason)
        reminder = self._schedule.take_due()
        if reminder is not None and self._pending is None:
            if reminder.kind is ReminderKind.ACTIVE:
                await self._present_active_checkpoint(
                    reminder.reason,
                    idle_threshold_minutes=reminder.idle_threshold_minutes,
                )
            else:
                self._pending = reminder
                try:
                    await self._notifier.send(reminder)
                except Exception:
                    logger.exception("native reminder delivery failed")

    async def _present_active_checkpoint(
        self,
        reason: ReminderReason,
        *,
        idle_threshold_minutes: float | None = None,
    ) -> None:
        active = self._active
        if active is None:
            return
        checkpoint = Reminder(
            ReminderKind.ACTIVE,
            project=active.project,
            activity=active.activity,
            reason=reason,
            idle_threshold_minutes=idle_threshold_minutes,
            checkpoint_id=self._checkpoint_id_factory(),
            active_entry_id=active.entry_id,
        )
        self._pending = checkpoint
        delivered = False
        try:
            await self._notifier.send(checkpoint)
            delivered = True
        except Exception:
            logger.exception("native reminder delivery failed")
        self._response_deadline = (
            self._monotonic() + self._response_grace_seconds
            if delivered and self._auto_stop_enabled and self._pending == checkpoint
            else None
        )

    async def _expire_unanswered_checkpoint(self) -> None:
        if (
            self._response_deadline is None
            or self._monotonic() < self._response_deadline
        ):
            return
        pending = self._pending
        active = self._active
        self._response_deadline = None
        self._pending = None
        if (
            pending is None
            or active is None
            or pending.kind is not ReminderKind.ACTIVE
            or pending.active_entry_id != active.entry_id
        ):
            self._unanswered_count = 0
            return
        self._unanswered_count += 1
        if self._unanswered_count < 2:
            return
        try:
            stopped = await self._stop_active(active.entry_id)
        except Exception:
            logger.exception("automatic checkpoint stop failed")
            self._unanswered_count = 0
            return
        if stopped is None:
            self._unanswered_count = 0
            return
        self._active = None
        self._unanswered_count = 0
        self._idle_monitor.reset(establish_baseline=True)
        self._schedule.reset(ReminderKind.INACTIVE)
        try:
            await self._notifier.send(
                AutoStoppedNotification(
                    stopped.project,
                    stopped.activity,
                    stopped.stopped_at,
                )
            )
        except Exception:
            logger.exception("automatic-stop follow-up notification failed")

    async def _reset_from_storage(self, *, establish_idle_baseline: bool) -> None:
        active = await asyncio.to_thread(self._service.get_active)
        self._reset(active, establish_idle_baseline=establish_idle_baseline)

    def _reset(
        self,
        active: ActiveTimer | None,
        *,
        establish_idle_baseline: bool,
    ) -> None:
        self._active = active
        self._clear_checkpoint(reset_unanswered=True)
        self._idle_monitor.reset(establish_baseline=establish_idle_baseline)
        if active is None:
            self._schedule.reset(ReminderKind.INACTIVE)
        else:
            self._schedule.reset(
                ReminderKind.ACTIVE,
                project=active.project,
                activity=active.activity,
            )

    def _clear_checkpoint(self, *, reset_unanswered: bool) -> None:
        self._pending = None
        self._response_deadline = None
        if reset_unanswered:
            self._unanswered_count = 0

    def _accepts_active_action(self, checkpoint_id: str | None) -> bool:
        if self._pending is None or self._pending.kind is not ReminderKind.ACTIVE:
            return False
        return checkpoint_id is None or self.checkpoint_matches(checkpoint_id)

    def _seconds_until_response_deadline(self) -> float | None:
        if self._response_deadline is None:
            return None
        return max(0.0, self._response_deadline - self._monotonic())

    def _should_poll_idle(self) -> bool:
        return (
            self._idle_enabled
            and self._idle_detector is not None
            and self._active is not None
            and self._schedule.reason is not ReminderReason.IDLE
        )

    async def _poll_idle(self) -> None:
        if not self._should_poll_idle():
            return
        detector = self._idle_detector
        active = self._active
        if detector is None or active is None:
            return
        try:
            reported_idle = await asyncio.to_thread(detector.idle_seconds)
            active_elapsed = max(
                0.0,
                (self._utc_clock() - active.started_at).total_seconds(),
            )
            crossed = self._idle_monitor.observe(reported_idle, active_elapsed)
        except OSError, RuntimeError, TypeError, ValueError:
            logger.exception("idle-duration detection became unavailable")
            self._idle_detector = None
            return
        if not crossed:
            return
        if self._pending is not None:
            self._idle_monitor.mark_handled()
            return
        self._schedule.request_idle(self._idle_threshold_minutes)

    async def _stop_active_directly(
        self, expected_entry_id: int
    ) -> CompletedTimer | None:
        active = await asyncio.to_thread(self._service.get_active)
        if active is None or active.entry_id != expected_entry_id:
            return None
        return await asyncio.to_thread(self._service.stop)


def _minimum_timeout(*values: float | None) -> float | None:
    available = [value for value in values if value is not None]
    return min(available) if available else None


def _safe_create_idle_detector(
    factory: Callable[[], IdleDetector | None] | None,
) -> IdleDetector | None:
    if factory is None:
        return None
    try:
        return factory()
    except Exception:
        logger.exception("idle-duration detection is unavailable")
        return None
