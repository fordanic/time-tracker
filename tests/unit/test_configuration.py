from pathlib import Path

import pytest

from time_tracker.application.configuration import ApplicationConfig
from time_tracker.application.reminders import ReminderIntervals
from time_tracker.infrastructure.configuration import ConfigurationError, load_config


def test_missing_configuration_uses_built_in_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    assert load_config(path) == ApplicationConfig(
        reminder_intervals=ReminderIntervals(inactive=300, active=1800)
    )
    assert not path.exists()


def test_reminder_intervals_are_loaded_and_independently_disabled(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[reminders]
inactive_enabled = false
inactive_interval_minutes = 2.5
active_enabled = true
active_interval_minutes = 12
""".strip(),
        encoding="utf-8",
    )

    assert load_config(path).reminder_intervals == ReminderIntervals(
        inactive=None,
        active=720,
    )


@pytest.mark.parametrize(
    "contents",
    [
        "[reminders",
        "unknown = true",
        "[reminders]\nactive_enabled = 1",
        "[reminders]\ninactive_interval_minutes = 0",
        "[reminders]\nactive_interval_minutes = true",
        "[reminders]\nactve_enabled = false",
    ],
)
def test_invalid_configuration_is_rejected_without_rewriting(
    tmp_path: Path,
    contents: str,
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(contents, encoding="utf-8")
    original = path.read_bytes()

    with pytest.raises(ConfigurationError, match="invalid configuration"):
        load_config(path)

    assert path.read_bytes() == original
