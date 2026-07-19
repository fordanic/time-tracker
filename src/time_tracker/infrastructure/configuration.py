"""Load strict, user-editable TOML application configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

from time_tracker.application.configuration import ApplicationConfig
from time_tracker.application.reminders import ReminderIntervals

_REMINDER_KEYS = {
    "inactive_enabled",
    "inactive_interval_minutes",
    "active_enabled",
    "active_interval_minutes",
}


class ConfigurationError(ValueError):
    """A configuration file exists but cannot be used safely."""


def load_config(path: Path) -> ApplicationConfig:
    """Load one TOML file, or return built-in defaults when it is absent."""
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return ApplicationConfig()

    try:
        decoded = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"invalid configuration at {path}: {error}") from error

    unknown_sections = set(decoded) - {"reminders"}
    if unknown_sections:
        names = ", ".join(sorted(unknown_sections))
        raise ConfigurationError(
            f"invalid configuration at {path}: unknown top-level key(s): {names}"
        )

    reminders_value = decoded.get("reminders", {})
    if not isinstance(reminders_value, dict):
        raise ConfigurationError(
            f"invalid configuration at {path}: reminders must be a table"
        )
    reminders = cast(dict[str, object], reminders_value)
    unknown_reminders = set(reminders) - _REMINDER_KEYS
    if unknown_reminders:
        names = ", ".join(sorted(unknown_reminders))
        raise ConfigurationError(
            f"invalid configuration at {path}: unknown reminders key(s): {names}"
        )

    inactive_enabled = _boolean(reminders, "inactive_enabled", True, path)
    active_enabled = _boolean(reminders, "active_enabled", True, path)
    inactive_minutes = _positive_number(
        reminders,
        "inactive_interval_minutes",
        5.0,
        path,
    )
    active_minutes = _positive_number(
        reminders,
        "active_interval_minutes",
        30.0,
        path,
    )
    return ApplicationConfig(
        reminder_intervals=ReminderIntervals(
            inactive=inactive_minutes * 60 if inactive_enabled else None,
            active=active_minutes * 60 if active_enabled else None,
        )
    )


def _boolean(
    values: dict[str, object],
    name: str,
    default: bool,
    path: Path,
) -> bool:
    value = values.get(name, default)
    if not isinstance(value, bool):
        raise ConfigurationError(
            f"invalid configuration at {path}: reminders.{name} must be a boolean"
        )
    return value


def _positive_number(
    values: dict[str, object],
    name: str,
    default: float,
    path: Path,
) -> float:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigurationError(
            f"invalid configuration at {path}: "
            f"reminders.{name} must be a positive number"
        )
    return float(value)
