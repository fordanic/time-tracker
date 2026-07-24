import pytest

from time_tracker.application.idle import IdleEpisodeMonitor


def test_idle_episode_triggers_once_and_resets_after_input() -> None:
    monitor = IdleEpisodeMonitor(60)

    assert monitor.observe(59, 100) is False
    assert monitor.observe(60, 101) is True
    assert monitor.observe(120, 161) is False

    assert monitor.observe(0, 162) is False
    assert monitor.observe(60, 222) is True


def test_idle_eligibility_is_clipped_to_active_timer_duration() -> None:
    monitor = IdleEpisodeMonitor(60)

    assert monitor.observe(600, 30) is False
    assert monitor.observe(630, 60) is True


def test_reset_baseline_excludes_idle_before_settings_or_timer_change() -> None:
    monitor = IdleEpisodeMonitor(60)
    monitor.reset(establish_baseline=True)

    assert monitor.observe(300, 600) is False
    assert monitor.observe(359, 659) is False
    assert monitor.observe(360, 660) is True


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_idle_monitor_rejects_invalid_detector_values(value: float) -> None:
    monitor = IdleEpisodeMonitor(60)

    with pytest.raises(ValueError, match="non-negative and finite"):
        monitor.observe(value, 100)
