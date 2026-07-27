import pytest

from time_tracker.infrastructure import idle_detection


def test_linux_without_x11_display_reports_idle_detection_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "time_tracker.infrastructure.idle_detection.sys.platform", "linux"
    )
    monkeypatch.delenv("DISPLAY", raising=False)

    assert idle_detection.create_idle_detector() is None


def test_display_without_screen_saver_extension_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnsupportedDetector:
        def __init__(self) -> None:
            raise OSError("XScreenSaverQueryInfo failed")

    monkeypatch.setattr(
        "time_tracker.infrastructure.idle_detection.sys.platform", "linux"
    )
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(idle_detection, "X11IdleDetector", UnsupportedDetector)

    assert idle_detection.create_idle_detector() is None
