"""Typed application configuration, validation, and persistence boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from time_tracker.application.reminders import ReminderIntervals


@dataclass(frozen=True, slots=True)
class ReminderSettings:
    """Human-editable reminder values with independent enabled state."""

    inactive_enabled: bool = True
    inactive_interval_minutes: float = 5.0
    active_enabled: bool = True
    active_interval_minutes: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.inactive_enabled, bool) or not isinstance(
            self.active_enabled, bool
        ):
            raise ValueError("reminder enabled values must be booleans")
        for interval in (
            self.inactive_interval_minutes,
            self.active_interval_minutes,
        ):
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not math.isfinite(interval)
                or interval <= 0
            ):
                raise ValueError("reminder intervals must be positive finite numbers")

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
