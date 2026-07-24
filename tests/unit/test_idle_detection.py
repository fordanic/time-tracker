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
