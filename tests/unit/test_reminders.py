from time_tracker.application.reminders import (
    ReminderIntervals,
    ReminderKind,
    ReminderSchedule,
)


class ControlledMonotonicClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


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
