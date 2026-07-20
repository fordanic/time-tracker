from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from time_tracker.application.reporting import (
    DailySummary,
    build_daily_review,
    build_daily_summaries,
)
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


def test_daily_review_groups_chronologically_and_splits_overnight_entries() -> None:
    entries = [
        CompletedTimer(
            entry_id=2,
            project="Client",
            activity="Writing",
            started_at=datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
            stopped_at=datetime(2026, 7, 20, 8, 45, tzinfo=UTC),
            note="Draft",
        ),
        CompletedTimer(
            entry_id=1,
            project="Client",
            activity="Research",
            started_at=datetime(2026, 7, 19, 23, 30, tzinfo=UTC),
            stopped_at=datetime(2026, 7, 20, 0, 30, tzinfo=UTC),
        ),
    ]

    groups = build_daily_review(entries, UTC)

    assert [group.day.isoformat() for group in groups] == [
        "2026-07-19",
        "2026-07-20",
    ]
    assert [segment.entry_id for segment in groups[0].segments] == [1]
    assert groups[0].segments[0].started_at == datetime(2026, 7, 19, 23, 30, tzinfo=UTC)
    assert groups[0].segments[0].stopped_at == datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
    assert groups[0].duration == timedelta(minutes=30)
    assert [segment.entry_id for segment in groups[1].segments] == [1, 2]
    assert groups[1].segments[0].duration == timedelta(minutes=30)
    assert groups[1].segments[1].note == "Draft"
    assert groups[1].duration == timedelta(minutes=75)


def test_daily_review_uses_instant_durations_across_a_local_offset_change() -> None:
    stockholm = ZoneInfo("Europe/Stockholm")
    entry = CompletedTimer(
        entry_id=1,
        project="Client",
        activity="Release",
        started_at=datetime(2026, 10, 24, 21, 30, tzinfo=UTC),
        stopped_at=datetime(2026, 10, 25, 2, 30, tzinfo=UTC),
    )

    groups = build_daily_review([entry], stockholm)

    assert [group.day.isoformat() for group in groups] == [
        "2026-10-24",
        "2026-10-25",
    ]
    assert groups[0].duration == timedelta(minutes=30)
    assert groups[1].duration == timedelta(hours=4, minutes=30)
    assert (
        groups[0].segments[0].stopped_at.astimezone(stockholm).strftime("%H:%M%z")
        == "00:00+0200"
    )
    assert (
        groups[1].segments[0].stopped_at.astimezone(stockholm).strftime("%H:%M%z")
        == "03:30+0100"
    )
