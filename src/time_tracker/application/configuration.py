"""Typed application configuration, validation, and persistence boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import time
from typing import Protocol

from time_tracker.application.reminders import (
    ReminderIntervals,
    ReminderReason,
    ReminderWindow,
    ScheduledCheckpoint,
)


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
    safeguard_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    lunch_checkpoint_enabled: bool = False
    lunch_checkpoint_time: str = "12:00"
    end_of_day_checkpoint_enabled: bool = False
    end_of_day_checkpoint_time: str = "17:00"
    auto_stop_after_unanswered_enabled: bool = False

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (
                self.inactive_enabled,
                self.active_enabled,
                self.window_enabled,
                self.idle_enabled,
                self.lunch_checkpoint_enabled,
                self.end_of_day_checkpoint_enabled,
                self.auto_stop_after_unanswered_enabled,
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
        _validate_weekdays(self.safeguard_weekdays, "checkpoint")
        _parse_clock(self.lunch_checkpoint_time)
        _parse_clock(self.end_of_day_checkpoint_time)
        if (
            self.lunch_checkpoint_enabled
            and self.end_of_day_checkpoint_enabled
            and self.lunch_checkpoint_time == self.end_of_day_checkpoint_time
        ):
            raise ValueError("lunch and end-of-day checkpoint times must differ")

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

    @property
    def scheduled_checkpoints(self) -> tuple[ScheduledCheckpoint, ...]:
        """Return enabled local-time lunch and end-of-day safeguards."""
        checkpoints: list[ScheduledCheckpoint] = []
        if self.lunch_checkpoint_enabled:
            checkpoints.append(
                ScheduledCheckpoint(
                    ReminderReason.LUNCH,
                    _parse_clock(self.lunch_checkpoint_time),
                )
            )
        if self.end_of_day_checkpoint_enabled:
            checkpoints.append(
                ScheduledCheckpoint(
                    ReminderReason.END_OF_DAY,
                    _parse_clock(self.end_of_day_checkpoint_time),
                )
            )
        return tuple(checkpoints)

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


@dataclass(frozen=True, slots=True)
class UiSettings:
    """Durable user-interface preferences."""

    theme: str = "textual-dark"

    def __post_init__(self) -> None:
        if not isinstance(self.theme, str) or not self.theme.strip():
            raise ValueError("UI theme must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ExportSettings:
    """Durable export-format preferences."""

    delimiter: str = ","

    def __post_init__(self) -> None:
        if self.delimiter not in {",", "|"}:
            raise ValueError("export delimiter must be comma or pipe")


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Configuration consumed by application and background-process services."""

    reminder_settings: ReminderSettings = field(default_factory=ReminderSettings)
    ui_settings: UiSettings = field(default_factory=UiSettings)
    export_settings: ExportSettings = field(default_factory=ExportSettings)

    @property
    def reminder_intervals(self) -> ReminderIntervals:
        """Return the scheduler representation of configured reminders."""
        return self.reminder_settings.intervals


class ConfigurationStore(Protocol):
    """Port for durable human-readable application configuration."""

    def save(self, config: ApplicationConfig) -> None:
        """Atomically persist the complete validated configuration."""
        ...


class ConfigurationService:
    """Own current settings and publish them only after durable persistence."""

    def __init__(
        self,
        store: ConfigurationStore,
        config: ApplicationConfig | None = None,
    ) -> None:
        self._store = store
        self._config = config or ApplicationConfig()

    def get(self) -> ReminderSettings:
        """Return the settings currently used by the running agent."""
        return self._config.reminder_settings

    def save(self, settings: ReminderSettings) -> ReminderSettings:
        """Persist first, then publish the replacement settings."""
        config = replace(self._config, reminder_settings=settings)
        self._store.save(config)
        self._config = config
        return settings

    def get_theme(self) -> str:
        """Return the currently configured Textual theme name."""
        return self._config.ui_settings.theme

    def save_theme(self, theme: str) -> str:
        """Persist first, then publish a replacement theme preference."""
        config = replace(self._config, ui_settings=UiSettings(theme))
        self._store.save(config)
        self._config = config
        return theme

    def get_export_delimiter(self) -> str:
        """Return the currently configured export delimiter."""
        return self._config.export_settings.delimiter

    def save_export_delimiter(self, delimiter: str) -> str:
        """Persist first, then publish a replacement export delimiter."""
        config = replace(
            self._config,
            export_settings=ExportSettings(delimiter),
        )
        self._store.save(config)
        self._config = config
        return delimiter


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


def _validate_weekdays(value: tuple[int, ...], label: str) -> None:
    if (
        not isinstance(value, tuple)
        or not value
        or len(set(value)) != len(value)
        or any(isinstance(day, bool) or not isinstance(day, int) for day in value)
        or any(day < 0 or day > 6 for day in value)
    ):
        raise ValueError(f"{label} weekdays must be unique integers from 0 through 6")
