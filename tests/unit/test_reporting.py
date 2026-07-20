from datetime import UTC, date, datetime, timedelta, tzinfo

import pytest

from time_tracker.application.reporting import (
    DailySummary,
    DatePreset,
    RangeSummary,
    ReviewFilter,
    build_daily_review,
    build_daily_summaries,
    build_range_summaries,
    filter_completed_entries,
    review_filter_activities,
    review_filter_for_preset,
    review_filter_projects,
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


def test_review_filter_presets_use_inclusive_local_calendar_boundaries() -> None:
    today = date(2026, 7, 20)

    assert review_filter_for_preset(DatePreset.TODAY, today=today) == ReviewFilter(
        today,
        today,
    )
    assert review_filter_for_preset(
        DatePreset.THIS_WEEK,
        today=today,
    ) == ReviewFilter(date(2026, 7, 20), date(2026, 7, 26))
    assert review_filter_for_preset(
        DatePreset.THIS_MONTH,
        today=today,
    ) == ReviewFilter(date(2026, 7, 1), date(2026, 7, 31))
    assert review_filter_for_preset(
        DatePreset.CUSTOM,
        today=today,
        custom_start=date(2026, 7, 2),
        custom_end=date(2026, 7, 4),
        project=" Client ",
    ) == ReviewFilter(date(2026, 7, 2), date(2026, 7, 4), "Client")

    with pytest.raises(ValueError, match="both filter start date and end date"):
        ReviewFilter(start_date=today)
    with pytest.raises(ValueError, match="must not be after"):
        ReviewFilter(date(2026, 7, 21), date(2026, 7, 20))
    with pytest.raises(ValueError, match="custom filter start date"):
        review_filter_for_preset(DatePreset.CUSTOM, today=today)


def test_shared_filter_clips_entries_and_builds_range_totals() -> None:
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
            started_at=datetime(2026, 7, 20, 9, tzinfo=UTC),
            stopped_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
        ),
        CompletedTimer(
            entry_id=3,
            project="Internal",
            activity="Research",
            started_at=datetime(2026, 7, 20, 11, tzinfo=UTC),
            stopped_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
        ),
    ]
    selected = ReviewFilter(
        date(2026, 7, 20),
        date(2026, 7, 20),
        project="client",
        activity="research",
    )

    clipped = filter_completed_entries(entries, UTC, selected)

    assert [
        (entry.entry_id, entry.started_at, entry.stopped_at) for entry in clipped
    ] == [
        (
            1,
            datetime(2026, 7, 20, 0, tzinfo=UTC),
            datetime(2026, 7, 20, 0, 30, tzinfo=UTC),
        ),
        (
            2,
            datetime(2026, 7, 20, 9, tzinfo=UTC),
            datetime(2026, 7, 20, 10, tzinfo=UTC),
        ),
    ]
    assert build_range_summaries(entries, UTC, selected) == [
        RangeSummary("Client", "Research", timedelta(minutes=90))
    ]


def test_review_filters_include_historical_names_and_dst_selected_duration() -> None:
    local_timezone = _AutumnOffsetChangeTimezone()
    entries = [
        CompletedTimer(
            entry_id=1,
            project="Archived Client",
            activity="Release",
            started_at=datetime(2026, 10, 24, 21, 30, tzinfo=UTC),
            stopped_at=datetime(2026, 10, 25, 2, 30, tzinfo=UTC),
        ),
        CompletedTimer(
            entry_id=2,
            project="Internal",
            activity="Release",
            started_at=datetime(2026, 10, 26, 9, tzinfo=UTC),
            stopped_at=datetime(2026, 10, 26, 10, tzinfo=UTC),
        ),
    ]

    groups = build_daily_review(
        entries,
        local_timezone,
        ReviewFilter(date(2026, 10, 25), date(2026, 10, 25)),
    )

    assert [group.duration for group in groups] == [timedelta(hours=4, minutes=30)]
    assert review_filter_projects(entries) == ["Archived Client", "Internal"]
    assert review_filter_activities(entries, "archived client") == ["Release"]
