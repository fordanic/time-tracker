"""Typed application configuration and built-in defaults."""

from __future__ import annotations

from dataclasses import dataclass, field

from time_tracker.application.reminders import ReminderIntervals


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Configuration consumed by application and background-process services."""

    reminder_intervals: ReminderIntervals = field(default_factory=ReminderIntervals)
