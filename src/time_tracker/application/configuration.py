"""Typed application configuration, validation, and persistence boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import time
from typing import Protocol

from time_tracker.application.reminders import ReminderIntervals, ReminderWindow


@dataclass(frozen=True, slots=True)
class ReminderSettings:
    """Human-editable reminder values with independent enabled state."""

    inactive_enabled: bool = True
    inactive_interval_minutes: float = 5.0
    active_enabled: bool = True
    active_interval_minutes: float = 30.0
    window_enabled: bool = False
    window_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    window_start: str = "09:00"
    window_end: str = "17:00"
    snooze_minutes: float = 10.0
    idle_enabled: bool = False
    idle_threshold_minutes: float = 15.0

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (
                self.inactive_enabled,
                self.active_enabled,
                self.window_enabled,
                self.idle_enabled,
            )
        ):
            raise ValueError("reminder enabled values must be booleans")
        for interval in (
            self.inactive_interval_minutes,
            self.active_interval_minutes,
            self.snooze_minutes,
            self.idle_threshold_minutes,
        ):
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not math.isfinite(interval)
                or interval <= 0
            ):
                raise ValueError("reminder intervals must be positive finite numbers")
        if (
            not isinstance(self.window_weekdays, tuple)
            or not self.window_weekdays
            or any(
                isinstance(day, bool) or not isinstance(day, int)
                for day in self.window_weekdays
            )
        ):
            raise ValueError(
                "reminder window weekdays must be a non-empty integer tuple"
            )
        ReminderWindow(
            self.window_weekdays,
            _parse_clock(self.window_start),
            _parse_clock(self.window_end),
        )

    @property
    def intervals(self) -> ReminderIntervals:
        """Return enabled scheduler intervals in seconds."""
        return ReminderIntervals(
            inactive=(
                float(self.inactive_interval_minutes) * 60
                if self.inactive_enabled
                else None
            ),
            active=(
                float(self.active_interval_minutes) * 60
                if self.active_enabled
                else None
            ),
        )

    @property
    def window(self) -> ReminderWindow | None:
        """Return the enabled local weekly delivery window."""
        if not self.window_enabled:
            return None
        return ReminderWindow(
            self.window_weekdays,
            _parse_clock(self.window_start),
            _parse_clock(self.window_end),
        )

    @property
    def snooze_seconds(self) -> float:
        """Return the configured in-memory snooze duration in seconds."""
        return float(self.snooze_minutes) * 60

    @property
    def idle_threshold_seconds(self) -> float:
        """Return the configured content-free idle threshold in seconds."""
        return float(self.idle_threshold_minutes) * 60

    @classmethod
    def from_intervals(cls, intervals: ReminderIntervals) -> ReminderSettings:
        """Create settings for an injected scheduler configuration."""
        return cls(
            inactive_enabled=intervals.inactive is not None,
            inactive_interval_minutes=(
                intervals.inactive / 60 if intervals.inactive is not None else 5.0
            ),
            active_enabled=intervals.active is not None,
            active_interval_minutes=(
                intervals.active / 60 if intervals.active is not None else 30.0
            ),
        )


class ConfigurationStore(Protocol):
    """Port for durable human-readable application configuration."""

    def save(self, settings: ReminderSettings) -> None:
        """Atomically persist validated reminder settings."""
        ...


class ConfigurationService:
    """Own current settings and publish them only after durable persistence."""

    def __init__(
        self,
        store: ConfigurationStore,
        settings: ReminderSettings | None = None,
    ) -> None:
        self._store = store
        self._settings = settings or ReminderSettings()

    def get(self) -> ReminderSettings:
        """Return the settings currently used by the running agent."""
        return self._settings

    def save(self, settings: ReminderSettings) -> ReminderSettings:
        """Persist first, then publish the replacement settings."""
        self._store.save(settings)
        self._settings = settings
        return settings


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Configuration consumed by application and background-process services."""

    reminder_settings: ReminderSettings = field(default_factory=ReminderSettings)

    @property
    def reminder_intervals(self) -> ReminderIntervals:
        """Return the scheduler representation of configured reminders."""
        return self.reminder_settings.intervals


def _parse_clock(value: str) -> time:
    if not isinstance(value, str):
        raise ValueError("reminder window times must be HH:MM strings")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise ValueError("reminder window times must use HH:MM") from error
    if (
        len(value) != 5
        or parsed.second
        or parsed.microsecond
        or parsed.tzinfo is not None
    ):
        raise ValueError("reminder window times must use HH:MM")
    return parsed
