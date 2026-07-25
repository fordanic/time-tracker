from datetime import UTC, datetime, time

import pytest

from time_tracker.application.reminders import (
    Reminder,
    ReminderIntervals,
    ReminderKind,
    ReminderReason,
    ReminderSchedule,
    ReminderWindow,
)


class ControlledMonotonicClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_idle_reminder_requires_active_kind_and_positive_threshold() -> None:
    with pytest.raises(ValueError, match="active timer"):
        Reminder(
            ReminderKind.INACTIVE,
            reason=ReminderReason.IDLE,
            idle_threshold_minutes=15,
        )
    with pytest.raises(ValueError, match="positive finite"):
        Reminder(ReminderKind.ACTIVE, reason=ReminderReason.IDLE)


def test_inactive_and_active_reminders_use_independent_intervals() -> None:
    clock = ControlledMonotonicClock()
    schedule = ReminderSchedule(
        ReminderIntervals(inactive=300, active=1800),
        clock,
    )

    schedule.reset(ReminderKind.INACTIVE)
    clock.value = 299
    assert schedule.take_due() is None
    clock.value = 300
    assert schedule.take_due() is not None

    schedule.reset(
        ReminderKind.ACTIVE,
        project="Website",
        activity="Implementation",
    )
    clock.value = 2099
    assert schedule.take_due() is None
    clock.value = 2100
    reminder = schedule.take_due()

    assert reminder is not None
    assert reminder.kind is ReminderKind.ACTIVE
    assert reminder.project == "Website"
    assert reminder.activity == "Implementation"


def test_each_reminder_interval_can_be_disabled() -> None:
    schedule = ReminderSchedule(ReminderIntervals(inactive=None, active=None))

    schedule.reset(ReminderKind.INACTIVE)
    assert schedule.seconds_until_due() is None
    assert schedule.take_due() is None

    schedule.reset(ReminderKind.ACTIVE, project="One", activity="Two")
    assert schedule.seconds_until_due() is None
    assert schedule.take_due() is None


def test_active_detail_update_changes_names_without_resetting_deadline() -> None:
    clock = ControlledMonotonicClock()
    schedule = ReminderSchedule(ReminderIntervals(active=100), clock)
    schedule.reset(ReminderKind.ACTIVE, project="Old", activity="Work")
    clock.value = 60

    schedule.update_active_details("New", "Details")

    assert schedule.seconds_until_due() == 40
    clock.value = 100
    reminder = schedule.take_due()
    assert reminder is not None
    assert reminder.project == "New"
    assert reminder.activity == "Details"


def test_due_reminder_waits_for_same_day_window_opening() -> None:
    monotonic = ControlledMonotonicClock()
    wall_now = [datetime(2026, 7, 20, 8, 0, tzinfo=UTC)]  # Monday
    schedule = ReminderSchedule(
        ReminderIntervals(inactive=60),
        monotonic,
        window=ReminderWindow((0,), time(9), time(17)),
        wall_clock=lambda: wall_now[0],
    )
    schedule.reset(ReminderKind.INACTIVE)
    monotonic.value = 60

    assert schedule.take_due() is None
    assert schedule.seconds_until_due() == 3600


def test_overnight_window_includes_following_morning() -> None:
    window = ReminderWindow((0,), time(22), time(6))

    assert window.contains(datetime(2026, 7, 20, 23, tzinfo=UTC))
    assert window.contains(datetime(2026, 7, 21, 5, tzinfo=UTC))
    assert not window.contains(datetime(2026, 7, 21, 7, tzinfo=UTC))


def test_snooze_replaces_monotonic_deadline() -> None:
    clock = ControlledMonotonicClock()
    schedule = ReminderSchedule(ReminderIntervals(active=100), clock)
    schedule.reset(ReminderKind.ACTIVE, project="One", activity="Two")
    clock.value = 100
    assert schedule.take_due() is not None

    schedule.snooze(30)

    clock.value = 129
    assert schedule.take_due() is None
    clock.value = 130
    assert schedule.take_due() is not None


def test_idle_request_works_when_periodic_active_reminders_are_disabled() -> None:
    clock = ControlledMonotonicClock()
    schedule = ReminderSchedule(ReminderIntervals(active=None), clock)
    schedule.reset(ReminderKind.ACTIVE, project="One", activity="Two")

    schedule.request_idle(15)
    reminder = schedule.take_due()

    assert reminder == Reminder(
        ReminderKind.ACTIVE,
        project="One",
        activity="Two",
        reason=ReminderReason.IDLE,
        idle_threshold_minutes=15,
    )
    assert schedule.seconds_until_due() is None


def test_snoozing_preserves_idle_reminder_reason() -> None:
    clock = ControlledMonotonicClock()
    schedule = ReminderSchedule(ReminderIntervals(active=100), clock)
    schedule.reset(ReminderKind.ACTIVE, project="One", activity="Two")
    schedule.snooze(
        30,
        reason=ReminderReason.IDLE,
        idle_threshold_minutes=15,
    )

    clock.value = 30
    reminder = schedule.take_due()

    assert reminder is not None
    assert reminder.reason is ReminderReason.IDLE
    assert reminder.idle_threshold_minutes == 15


def test_idle_request_waits_for_reminder_window_without_losing_reason() -> None:
    monotonic = ControlledMonotonicClock()
    wall_now = [datetime(2026, 7, 20, 8, 0, tzinfo=UTC)]  # Monday
    schedule = ReminderSchedule(
        ReminderIntervals(active=None),
        monotonic,
        window=ReminderWindow((0,), time(9), time(17)),
        wall_clock=lambda: wall_now[0],
    )
    schedule.reset(ReminderKind.ACTIVE, project="One", activity="Two")
    schedule.request_idle(15)

    assert schedule.take_due() is None
    assert schedule.reason is ReminderReason.IDLE
    assert schedule.seconds_until_due() == 3600

    monotonic.value = 3600
    wall_now[0] = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
    reminder = schedule.take_due()
    assert reminder is not None
    assert reminder.reason is ReminderReason.IDLE
