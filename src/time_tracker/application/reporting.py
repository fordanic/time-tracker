"""Application-level projections for completed time entries."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from enum import StrEnum

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
class RangeSummary:
    """Total selected time for one project and activity."""

    project: str
    activity: str
    duration: timedelta


class DatePreset(StrEnum):
    """Supported local calendar-date shortcuts in Review."""

    ALL_TIME = "all_time"
    TODAY = "today"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ReviewFilter:
    """Validated application filter shared by Review and export."""

    start_date: date | None = None
    end_date: date | None = None
    project: str | None = None
    activity: str | None = None

    def __post_init__(self) -> None:
        start_date = self.start_date
        end_date = self.end_date
        if (start_date is None) != (end_date is None):
            raise ValueError("both filter start date and end date are required")
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("filter start date must not be after end date")
        object.__setattr__(self, "project", _normalize_filter_name(self.project))
        object.__setattr__(self, "activity", _normalize_filter_name(self.activity))


def review_filter_for_preset(
    preset: DatePreset,
    *,
    today: date,
    custom_start: date | None = None,
    custom_end: date | None = None,
    project: str | None = None,
    activity: str | None = None,
) -> ReviewFilter:
    """Resolve one date preset and target selection into a validated filter."""
    if preset is DatePreset.ALL_TIME:
        return ReviewFilter(project=project, activity=activity)
    if preset is DatePreset.TODAY:
        start_date = end_date = today
    elif preset is DatePreset.THIS_WEEK:
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif preset is DatePreset.THIS_MONTH:
        start_date = today.replace(day=1)
        end_date = today.replace(day=monthrange(today.year, today.month)[1])
    else:
        if custom_start is None or custom_end is None:
            raise ValueError("custom filter start date and end date are required")
        start_date = custom_start
        end_date = custom_end
    return ReviewFilter(start_date, end_date, project, activity)


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
    review_filter: ReviewFilter | None = None,
) -> list[DailyReviewGroup]:
    """Group completed time by local day, splitting entries at midnight."""
    selected_filter = review_filter or ReviewFilter()
    segments_by_day: dict[date, list[DailyEntrySegment]] = {}
    for entry in sorted(
        entries,
        key=lambda item: (item.started_at, item.stopped_at, item.entry_id),
    ):
        if entry.started_at == entry.stopped_at:
            day = _local_day(entry.started_at, local_timezone)
            segment = _segment(entry, day, entry.started_at, entry.stopped_at)
            if _segment_matches(segment, selected_filter):
                segments_by_day.setdefault(day, []).append(segment)
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
            segment = _segment(entry, day, cursor, segment_end)
            if _segment_matches(segment, selected_filter):
                segments_by_day.setdefault(day, []).append(segment)
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
    review_filter: ReviewFilter | None = None,
) -> list[DailySummary]:
    """Aggregate completed entries by local day, splitting at local midnight."""
    totals: dict[tuple[date, str, str], timedelta] = {}
    for group in build_daily_review(entries, local_timezone, review_filter):
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


def build_range_summaries(
    entries: list[CompletedTimer],
    local_timezone: tzinfo | None = None,
    review_filter: ReviewFilter | None = None,
) -> list[RangeSummary]:
    """Aggregate selected completed time by project and activity."""
    totals: dict[tuple[str, str], timedelta] = {}
    for group in build_daily_review(entries, local_timezone, review_filter):
        for segment in group.segments:
            key = (segment.project, segment.activity)
            totals[key] = totals.get(key, timedelta()) + segment.duration
    return [
        RangeSummary(project=project, activity=activity, duration=duration)
        for (project, activity), duration in sorted(
            totals.items(),
            key=lambda item: (
                item[0][0].casefold(),
                item[0][1].casefold(),
                item[0][0],
                item[0][1],
            ),
        )
    ]


def filter_completed_entries(
    entries: list[CompletedTimer],
    local_timezone: tzinfo | None = None,
    review_filter: ReviewFilter | None = None,
) -> list[CompletedTimer]:
    """Return selected entries, clipped to inclusive local-date boundaries."""
    source_by_id = {entry.entry_id: entry for entry in entries}
    bounds_by_id: dict[int, tuple[datetime, datetime]] = {}
    for group in build_daily_review(entries, local_timezone, review_filter):
        for segment in group.segments:
            current = bounds_by_id.get(segment.entry_id)
            if current is None:
                bounds_by_id[segment.entry_id] = (
                    segment.started_at,
                    segment.stopped_at,
                )
            else:
                bounds_by_id[segment.entry_id] = (
                    min(current[0], segment.started_at),
                    max(current[1], segment.stopped_at),
                )

    selected = []
    for entry_id, (started_at, stopped_at) in bounds_by_id.items():
        source = source_by_id[entry_id]
        selected.append(
            CompletedTimer(
                entry_id=source.entry_id,
                project=source.project,
                activity=source.activity,
                started_at=started_at,
                stopped_at=stopped_at,
                note=source.note,
            )
        )
    return sorted(
        selected,
        key=lambda item: (item.started_at, item.stopped_at, item.entry_id),
    )


def review_filter_projects(entries: list[CompletedTimer]) -> list[str]:
    """Return canonical historical project names for Review suggestions."""
    return _canonical_names(entry.project for entry in entries)


def review_filter_activities(
    entries: list[CompletedTimer],
    project: str | None = None,
) -> list[str]:
    """Return canonical historical activity names, optionally for one project."""
    normalized_project = _normalize_filter_name(project)
    return _canonical_names(
        entry.activity
        for entry in entries
        if normalized_project is None
        or entry.project.casefold() == normalized_project.casefold()
    )


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


def _segment_matches(segment: DailyEntrySegment, review_filter: ReviewFilter) -> bool:
    if review_filter.start_date is not None and segment.day < review_filter.start_date:
        return False
    if review_filter.end_date is not None and segment.day > review_filter.end_date:
        return False
    if (
        review_filter.project is not None
        and segment.project.casefold() != review_filter.project.casefold()
    ):
        return False
    return not (
        review_filter.activity is not None
        and segment.activity.casefold() != review_filter.activity.casefold()
    )


def _normalize_filter_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _canonical_names(values: Iterable[str]) -> list[str]:
    names = set(values)
    return sorted(names, key=lambda value: (value.casefold(), value))


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
