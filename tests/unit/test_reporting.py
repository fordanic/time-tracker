from datetime import UTC, datetime, timedelta

from time_tracker.application.reporting import DailySummary, build_daily_summaries
from time_tracker.domain.models import CompletedTimer


def test_daily_summaries_group_project_activity_and_split_at_midnight() -> None:
    entries = [
        CompletedTimer(
            entry_id=1,
            project="Client",
            activity="Research",
            started_at=datetime(2026, 7, 19, 23, 30, tzinfo=UTC),
            stopped_at=datetime(2026, 7, 20, 0, 30, tzinfo=UTC),
        ),
        CompletedTimer(
            entry_id=2,
            project="Client",
            activity="Research",
            started_at=datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
            stopped_at=datetime(2026, 7, 20, 8, 45, tzinfo=UTC),
        ),
        CompletedTimer(
            entry_id=3,
            project="Client",
            activity="Writing",
            started_at=datetime(2026, 7, 20, 9, 0, tzinfo=UTC),
            stopped_at=datetime(2026, 7, 20, 9, 15, tzinfo=UTC),
        ),
    ]

    assert build_daily_summaries(entries, UTC) == [
        DailySummary(
            day=datetime(2026, 7, 19, tzinfo=UTC).date(),
            project="Client",
            activity="Research",
            duration=timedelta(minutes=30),
        ),
        DailySummary(
            day=datetime(2026, 7, 20, tzinfo=UTC).date(),
            project="Client",
            activity="Research",
            duration=timedelta(minutes=75),
        ),
        DailySummary(
            day=datetime(2026, 7, 20, tzinfo=UTC).date(),
            project="Client",
            activity="Writing",
            duration=timedelta(minutes=15),
        ),
    ]
