from pathlib import Path

import pytest

from time_tracker.application.configuration import (
    ApplicationConfig,
    ConfigurationService,
    ReminderSettings,
)
from time_tracker.application.reminders import ReminderIntervals
from time_tracker.infrastructure.configuration import (
    ConfigurationError,
    TomlConfigurationStore,
    load_config,
)


def test_missing_configuration_uses_built_in_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    assert load_config(path) == ApplicationConfig()
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
    assert load_config(path).reminder_settings == ReminderSettings(
        inactive_enabled=False,
        inactive_interval_minutes=2.5,
        active_enabled=True,
        active_interval_minutes=12,
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


def test_configuration_store_atomically_replaces_complete_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("old contents", encoding="utf-8")
    settings = ReminderSettings(
        inactive_enabled=False,
        inactive_interval_minutes=2.5,
        active_enabled=True,
        active_interval_minutes=12,
    )

    TomlConfigurationStore(path).save(settings)

    assert load_config(path).reminder_settings == settings
    assert path.read_text(encoding="utf-8") == (
        "[reminders]\n"
        "inactive_enabled = false\n"
        "inactive_interval_minutes = 2.5\n"
        "active_enabled = true\n"
        "active_interval_minutes = 12\n"
    )
    assert list(tmp_path.glob(".config.toml.*.tmp")) == []


def test_failed_persistence_does_not_publish_new_settings() -> None:
    original = ReminderSettings()

    class FailingStore:
        def save(self, settings: ReminderSettings) -> None:
            raise OSError("simulated write failure")

    service = ConfigurationService(FailingStore(), original)

    with pytest.raises(OSError, match="simulated write failure"):
        service.save(ReminderSettings(active_interval_minutes=10))

    assert service.get() == original


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_reminder_settings_reject_non_positive_or_non_finite_values(
    value: float,
) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        ReminderSettings(active_interval_minutes=value)
