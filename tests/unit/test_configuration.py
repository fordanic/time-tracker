from pathlib import Path

import pytest

from time_tracker.application.configuration import (
    ApplicationConfig,
    ConfigurationService,
    ExportSettings,
    ReminderSettings,
    UiSettings,
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
        "[reminders]\nidle_enabled = 1",
        "[reminders]\nidle_threshold_minutes = 0",
        "[reminders]\nactve_enabled = false",
        "[ui]\ntheme = 1",
        "[ui]\nunknown = true",
        '[export]\ndelimiter = ";"',
        "[export]\nunknown = true",
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
        window_enabled=True,
        window_weekdays=(0, 2, 4),
        window_start="08:30",
        window_end="18:15",
        snooze_minutes=7.5,
        idle_enabled=True,
        idle_threshold_minutes=22.5,
    )

    config = ApplicationConfig(
        reminder_settings=settings,
        ui_settings=UiSettings(theme="nord"),
        export_settings=ExportSettings(delimiter="|"),
    )
    TomlConfigurationStore(path).save(config)

    assert load_config(path) == config
    assert path.read_text(encoding="utf-8") == (
        "[reminders]\n"
        "inactive_enabled = false\n"
        "inactive_interval_minutes = 2.5\n"
        "active_enabled = true\n"
        "active_interval_minutes = 12\n"
        "window_enabled = true\n"
        "window_weekdays = [0, 2, 4]\n"
        'window_start = "08:30"\n'
        'window_end = "18:15"\n'
        "snooze_minutes = 7.5\n"
        "idle_enabled = true\n"
        "idle_threshold_minutes = 22.5\n"
        "\n[ui]\n"
        'theme = "nord"\n'
        "\n[export]\n"
        'delimiter = "|"\n'
    )
    assert list(tmp_path.glob(".config.toml.*.tmp")) == []


def test_failed_persistence_does_not_publish_new_settings() -> None:
    original = ReminderSettings()
    original_config = ApplicationConfig(reminder_settings=original)

    class FailingStore:
        def save(self, config: ApplicationConfig) -> None:
            raise OSError("simulated write failure")

    service = ConfigurationService(FailingStore(), original_config)

    with pytest.raises(OSError, match="simulated write failure"):
        service.save(ReminderSettings(active_interval_minutes=10))

    assert service.get() == original
    assert service.get_theme() == "textual-dark"
    assert service.get_export_delimiter() == ","


def test_saving_one_configuration_section_preserves_the_other(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    service = ConfigurationService(TomlConfigurationStore(path))
    reminders = ReminderSettings(active_interval_minutes=12)

    assert service.save_theme("nord") == "nord"
    assert service.save_export_delimiter("|") == "|"
    assert service.save(reminders) == reminders
    assert load_config(path) == ApplicationConfig(
        reminder_settings=reminders,
        ui_settings=UiSettings(theme="nord"),
        export_settings=ExportSettings(delimiter="|"),
    )


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_reminder_settings_reject_non_positive_or_non_finite_values(
    value: float,
) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        ReminderSettings(active_interval_minutes=value)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"window_weekdays": ()}, "weekdays"),
        ({"window_weekdays": (0, 0)}, "unique"),
        ({"window_weekdays": (7,)}, "between"),
        ({"window_start": "9:00"}, "HH:MM"),
        ({"window_end": "09:00", "window_start": "09:00"}, "differ"),
        ({"snooze_minutes": 0}, "positive finite"),
        ({"idle_threshold_minutes": 0}, "positive finite"),
    ],
)
def test_reminder_settings_reject_invalid_window_or_snooze(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ReminderSettings(**changes)  # type: ignore[arg-type]
