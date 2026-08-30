from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from time_tracker.tui.app import (
    _format_editor_datetime,
    _parse_editor_datetime,
    _parse_local_datetime,
)


def test_local_editor_timestamp_omits_offset_and_resolves_normal_time() -> None:
    stockholm = ZoneInfo("Europe/Stockholm")
    parsed = _parse_local_datetime(
        "2026-07-20 10:15:30",
        "start",
        stockholm,
    )

    assert parsed == datetime(2026, 7, 20, 10, 15, 30, tzinfo=stockholm)
    assert parsed.astimezone(UTC) == datetime(2026, 7, 20, 8, 15, 30, tzinfo=UTC)
    assert "+" not in _format_editor_datetime(parsed)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("2026-03-29 02:30:00", "nonexistent local time"),
        ("2026-10-25 02:30:00", "ambiguous local time"),
        ("2026-07-20T10:15:30+02:00", "must not include a UTC offset"),
    ],
)
def test_local_editor_timestamp_rejects_unsafe_time(
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _parse_local_datetime(value, "start", ZoneInfo("Europe/Stockholm"))


def test_unchanged_editor_value_preserves_stored_subsecond_instant() -> None:
    stored = datetime(2026, 7, 20, 8, 15, 30, 123456, tzinfo=UTC)

    assert _parse_editor_datetime(_format_editor_datetime(stored), "start", stored) == (
        stored
    )
