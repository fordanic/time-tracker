"""Application-level projections for completed time entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from time_tracker.domain.models import CompletedTimer

_ONE_MICROSECOND = timedelta(microseconds=1)


@dataclass(frozen=True, slots=True)
class DailySummary:
    """Total completed time for one local day, project, and activity."""

    day: date
    project: str
    activity: str
    duration: timedelta


@dataclass(frozen=True, slots=True)
class DailyEntrySegment:
    """The portion of one completed entry assigned to one local day."""

    day: date
    entry_id: int
    project: str
    activity: str
    started_at: datetime
    stopped_at: datetime
    note: str | None

    @property
    def duration(self) -> timedelta:
        """Return the segment duration derived from its stored instants."""
        return self.stopped_at - self.started_at


@dataclass(frozen=True, slots=True)
class DailyReviewGroup:
    """Chronological completed-entry segments and total for one local day."""

    day: date
    segments: tuple[DailyEntrySegment, ...]
    duration: timedelta


def build_daily_review(
    entries: list[CompletedTimer],
    local_timezone: tzinfo | None = None,
) -> list[DailyReviewGroup]:
    """Group completed time by local day, splitting entries at midnight."""
    segments_by_day: dict[date, list[DailyEntrySegment]] = {}
    for entry in sorted(
        entries,
        key=lambda item: (item.started_at, item.stopped_at, item.entry_id),
    ):
        if entry.started_at == entry.stopped_at:
            day = _local_day(entry.started_at, local_timezone)
            segments_by_day.setdefault(day, []).append(
                _segment(entry, day, entry.started_at, entry.stopped_at)
            )
            continue

        cursor = entry.started_at
        while cursor < entry.stopped_at:
            day = _local_day(cursor, local_timezone)
            segment_end = _end_of_local_day_segment(
                cursor,
                entry.stopped_at,
                day,
                local_timezone,
            )
            segments_by_day.setdefault(day, []).append(
                _segment(entry, day, cursor, segment_end)
            )
            cursor = segment_end

    return [
        DailyReviewGroup(
            day=day,
            segments=tuple(segments),
            duration=sum(
                (segment.duration for segment in segments),
                start=timedelta(),
            ),
        )
        for day, segments in sorted(segments_by_day.items())
    ]


def build_daily_summaries(
    entries: list[CompletedTimer],
    local_timezone: tzinfo | None = None,
) -> list[DailySummary]:
    """Aggregate completed entries by local day, splitting at local midnight."""
    totals: dict[tuple[date, str, str], timedelta] = {}
    for group in build_daily_review(entries, local_timezone):
        for segment in group.segments:
            key = (group.day, segment.project, segment.activity)
            totals[key] = totals.get(key, timedelta()) + segment.duration

    return [
        DailySummary(day=day, project=project, activity=activity, duration=duration)
        for (day, project, activity), duration in sorted(
            totals.items(),
            key=lambda item: (
                item[0][0],
                item[0][1].casefold(),
                item[0][2].casefold(),
                item[0][1],
                item[0][2],
            ),
        )
    ]


def _segment(
    entry: CompletedTimer,
    day: date,
    started_at: datetime,
    stopped_at: datetime,
) -> DailyEntrySegment:
    return DailyEntrySegment(
        day=day,
        entry_id=entry.entry_id,
        project=entry.project,
        activity=entry.activity,
        started_at=started_at,
        stopped_at=stopped_at,
        note=entry.note,
    )


def _local_day(instant: datetime, local_timezone: tzinfo | None) -> date:
    return instant.astimezone(local_timezone).date()


def _end_of_local_day_segment(
    started_at: datetime,
    stopped_at: datetime,
    day: date,
    local_timezone: tzinfo | None,
) -> datetime:
    """Find the first stored instant that belongs to a later local date."""
    if _local_day(stopped_at, local_timezone) == day:
        return stopped_at

    same_day = started_at
    later_day = stopped_at
    while later_day - same_day > _ONE_MICROSECOND:
        midpoint = same_day + (later_day - same_day) / 2
        if _local_day(midpoint, local_timezone) == day:
            same_day = midpoint
        else:
            later_day = midpoint
    return later_day
