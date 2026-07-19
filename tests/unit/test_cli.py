from pathlib import Path

import pytest

from time_tracker import __version__
from time_tracker.cli import main


def test_version_flag_reports_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == f"time-tracker {__version__}\n"


def test_no_arguments_launches_the_tui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched = False

    def fake_launch() -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr("time_tracker.cli.launch_tui", fake_launch)

    assert main([]) == 0
    assert launched


def test_packaged_smoke_flag_runs_the_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    received: Path | None = None

    async def fake_smoke(directory: Path) -> None:
        nonlocal received
        received = directory

    monkeypatch.setattr("time_tracker.cli.run_packaged_lifecycle", fake_smoke)

    assert main(["--packaged-smoke", str(tmp_path)]) == 0
    assert received == tmp_path
