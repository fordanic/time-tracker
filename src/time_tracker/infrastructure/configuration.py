"""Load strict, user-editable TOML application configuration."""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import cast

from time_tracker.application.configuration import ApplicationConfig, ReminderSettings

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
        reminder_settings=ReminderSettings(
            inactive_enabled=inactive_enabled,
            inactive_interval_minutes=inactive_minutes,
            active_enabled=active_enabled,
            active_interval_minutes=active_minutes,
        )
    )


class TomlConfigurationStore:
    """Atomically persist the complete supported TOML configuration."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, settings: ReminderSettings) -> None:
        """Replace the destination only after a complete file is durable."""
        payload = _toml(settings).encode("utf-8")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.replace(self._path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _toml(settings: ReminderSettings) -> str:
    return (
        "[reminders]\n"
        f"inactive_enabled = {str(settings.inactive_enabled).lower()}\n"
        "inactive_interval_minutes = "
        f"{_format_number(settings.inactive_interval_minutes)}\n"
        f"active_enabled = {str(settings.active_enabled).lower()}\n"
        "active_interval_minutes = "
        f"{_format_number(settings.active_interval_minutes)}\n"
    )


def _format_number(value: float) -> str:
    return format(float(value), ".15g")


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
