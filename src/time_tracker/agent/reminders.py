"""Async reminder coordination owned by the background process."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from time_tracker.application.idle import (
    IdleDetectionStatus,
    IdleDetector,
    IdleEpisodeMonitor,
)
from time_tracker.application.reminders import (
    Reminder,
    ReminderIntervals,
    ReminderKind,
    ReminderReason,
    ReminderSchedule,
    ReminderWindow,
)
from time_tracker.application.tracking import TrackingService
from time_tracker.domain.models import ActiveTimer
from time_tracker.infrastructure.notifications import NotificationService

logger = logging.getLogger(__name__)


class ReminderCoordinator:
    """Schedule notifications independently of foreground IPC connections."""

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
        utc_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._notifier = notifier
        self._schedule = ReminderSchedule(intervals, window=window)
        self._snooze_seconds = snooze_seconds
        self._idle_enabled = idle_enabled
        self._idle_threshold_minutes = idle_threshold_minutes
        self._idle_monitor = IdleEpisodeMonitor(idle_threshold_minutes * 60)
        self._idle_detector_factory = idle_detector_factory
        self._idle_detector = idle_detector or _safe_create_idle_detector(
            idle_detector_factory
        )
        self._idle_poll_seconds = idle_poll_seconds
        self._utc_clock = utc_clock or (lambda: datetime.now(UTC))
        self._active: ActiveTimer | None = None
        self._changed = asyncio.Event()
        self._generation = 0
        self._pending: Reminder | None = None
        self._stopping = False

    def timer_changed(self) -> None:
        """Wake the scheduler after a successfully persisted transition."""
        self._pending = None
        self._generation += 1
        self._changed.set()

    def pending_reminder(self) -> Reminder | None:
        """Return the latest due reminder for a connected foreground client."""
        return self._pending

    def idle_detection_status(self) -> IdleDetectionStatus:
        """Return current platform adapter availability."""
        return IdleDetectionStatus(self._idle_detector is not None)

    def active_edited(self, active: ActiveTimer) -> None:
        """Refresh active reminder names without restarting its interval."""
        self._schedule.update_active_details(active.project, active.activity)
        if self._pending is not None and self._pending.kind is ReminderKind.ACTIVE:
            self._pending = Reminder(
                ReminderKind.ACTIVE,
                project=active.project,
                activity=active.activity,
                reason=self._pending.reason,
                idle_threshold_minutes=self._pending.idle_threshold_minutes,
            )
        self._active = active

    def reload_settings(
        self,
        intervals: ReminderIntervals,
        window: ReminderWindow | None,
        snooze_seconds: float,
        idle_enabled: bool,
        idle_threshold_minutes: float,
    ) -> None:
        """Apply durable settings and reset the current state's deadline."""
        self._schedule.replace_intervals(intervals)
        self._schedule.replace_window(window)
        self._snooze_seconds = snooze_seconds
        self._idle_enabled = idle_enabled
        self._idle_threshold_minutes = idle_threshold_minutes
        self._idle_monitor = IdleEpisodeMonitor(idle_threshold_minutes * 60)
        self._idle_monitor.reset(establish_baseline=True)
        if self._idle_detector_factory is not None:
            self._idle_detector = _safe_create_idle_detector(
                self._idle_detector_factory
            )
        self._pending = None
        self._generation += 1
        self._changed.set()

    def confirm_active(self) -> bool:
        """Clear an active prompt and restart its interval from now."""
        if self._pending is None or self._pending.kind is not ReminderKind.ACTIVE:
            return False
        self._pending = None
        self._idle_monitor.reset(establish_baseline=True)
        self._generation += 1
        self._changed.set()
        return True

    def snooze(self) -> bool:
        """Clear any pending prompt and defer it without changing timer state."""
        if self._pending is None:
            return False
        pending = self._pending
        self._pending = None
        self._schedule.snooze(
            self._snooze_seconds,
            reason=pending.reason,
            idle_threshold_minutes=pending.idle_threshold_minutes,
        )
        self._changed.set()
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
            pending_idle = (
                self._pending is not None
                and self._pending.reason is ReminderReason.IDLE
            )
            schedule_timeout = (
                None if pending_idle else self._schedule.seconds_until_due()
            )
            idle_timeout = self._idle_poll_seconds if self._should_poll_idle() else None
            timeout = _minimum_timeout(schedule_timeout, idle_timeout)
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
                await self._poll_idle()
                if (
                    self._pending is not None
                    and self._pending.reason is ReminderReason.IDLE
                ):
                    continue
                reminder = self._schedule.take_due()
                if reminder is not None:
                    self._pending = reminder
                    try:
                        await self._notifier.send(reminder)
                    except Exception:
                        logger.exception("native reminder delivery failed")
            else:
                if not self._stopping and self._generation != seen_generation:
                    await self._reset_from_storage(establish_idle_baseline=True)
                    seen_generation = self._generation

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
        self._idle_monitor.reset(establish_baseline=establish_idle_baseline)
        if active is None:
            self._schedule.reset(ReminderKind.INACTIVE)
        else:
            self._schedule.reset(
                ReminderKind.ACTIVE,
                project=active.project,
                activity=active.activity,
            )

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
