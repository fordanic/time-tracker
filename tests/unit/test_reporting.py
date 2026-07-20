from datetime import UTC, datetime, timedelta, tzinfo

from time_tracker.application.reporting import (
    DailySummary,
    build_daily_review,
    build_daily_summaries,
)
from time_tracker.domain.models import CompletedTimer


class _AutumnOffsetChangeTimezone(tzinfo):
    """Deterministic UTC+2 to UTC+1 transition without system zone data."""

    _transition_utc = datetime(2026, 10, 25, 1)
    _repeated_hour_start = datetime(2026, 10, 25, 2)
    _repeated_hour_end = datetime(2026, 10, 25, 3)
    _standard_offset = timedelta(hours=1)
    _daylight_offset = timedelta(hours=2)

    def utcoffset(self, value: datetime | None) -> timedelta:
        if value is None:
            return self._standard_offset
        local = value.replace(tzinfo=None)
        if local < self._repeated_hour_start:
            return self._daylight_offset
        if local < self._repeated_hour_end:
            return self._standard_offset if value.fold else self._daylight_offset
        return self._standard_offset

    def dst(self, value: datetime | None) -> timedelta:
        return self.utcoffset(value) - self._standard_offset

    def tzname(self, value: datetime | None) -> str:
        return "TEST-DST" if self.dst(value) else "TEST-STD"

    def fromutc(self, value: datetime) -> datetime:
        if value.tzinfo is not self:
            raise ValueError("fromutc requires this timezone")
        utc = value.replace(tzinfo=None)
        after_transition = utc >= self._transition_utc
        offset = self._standard_offset if after_transition else self._daylight_offset
        repeated_hour = (
            self._transition_utc <= utc < (self._transition_utc + timedelta(hours=1))
        )
        return (value + offset).replace(fold=int(repeated_hour))


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
    local_timezone = _AutumnOffsetChangeTimezone()
    entry = CompletedTimer(
        entry_id=1,
        project="Client",
        activity="Release",
        started_at=datetime(2026, 10, 24, 21, 30, tzinfo=UTC),
        stopped_at=datetime(2026, 10, 25, 2, 30, tzinfo=UTC),
    )

    groups = build_daily_review([entry], local_timezone)

    assert [group.day.isoformat() for group in groups] == [
        "2026-10-24",
        "2026-10-25",
    ]
    assert groups[0].duration == timedelta(minutes=30)
    assert groups[1].duration == timedelta(hours=4, minutes=30)
    assert (
        groups[0].segments[0].stopped_at.astimezone(local_timezone).strftime("%H:%M%z")
        == "00:00+0200"
    )
    assert (
        groups[1].segments[0].stopped_at.astimezone(local_timezone).strftime("%H:%M%z")
        == "03:30+0100"
    )
