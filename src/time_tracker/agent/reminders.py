"""Async reminder coordination owned by the background process."""

from __future__ import annotations

import asyncio
import logging

from time_tracker.application.reminders import (
    ReminderIntervals,
    ReminderKind,
    ReminderSchedule,
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
    ) -> None:
        self._service = service
        self._notifier = notifier
        self._schedule = ReminderSchedule(intervals)
        self._changed = asyncio.Event()
        self._generation = 0
        self._stopping = False

    def timer_changed(self) -> None:
        """Wake the scheduler after a successfully persisted transition."""
        self._generation += 1
        self._changed.set()

    def stop(self) -> None:
        """Wake and stop the scheduler without modifying timer state."""
        self._stopping = True
        self._changed.set()

    async def run(self) -> None:
        """Run until stopped, resetting intervals after timer transitions."""
        await self._reset_from_storage()
        seen_generation = self._generation
        while not self._stopping:
            timeout = self._schedule.seconds_until_due()
            self._changed.clear()
            if self._generation != seen_generation:
                await self._reset_from_storage()
                seen_generation = self._generation
                continue
            try:
                if timeout is None:
                    await self._changed.wait()
                else:
                    await asyncio.wait_for(self._changed.wait(), timeout=timeout)
            except TimeoutError:
                reminder = self._schedule.take_due()
                if reminder is not None:
                    try:
                        await self._notifier.send(reminder)
                    except Exception:
                        logger.exception("native reminder delivery failed")
            else:
                if not self._stopping:
                    await self._reset_from_storage()
                    seen_generation = self._generation

    async def _reset_from_storage(self) -> None:
        active = await asyncio.to_thread(self._service.get_active)
        self._reset(active)

    def _reset(self, active: ActiveTimer | None) -> None:
        if active is None:
            self._schedule.reset(ReminderKind.INACTIVE)
        else:
            self._schedule.reset(
                ReminderKind.ACTIVE,
                project=active.project,
                activity=active.activity,
            )
