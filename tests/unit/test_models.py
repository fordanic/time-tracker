from datetime import UTC, datetime, timedelta

import pytest

from time_tracker.domain.models import ActiveTimer


def test_duration_is_derived_and_a_stop_cannot_precede_start() -> None:
    started_at = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
    timer = ActiveTimer(1, "Website", "Implementation", started_at)

    completed = timer.stop(started_at + timedelta(minutes=25))

    assert completed.duration == timedelta(minutes=25)
    with pytest.raises(ValueError, match="cannot stop before"):
        timer.stop(started_at - timedelta(microseconds=1))
