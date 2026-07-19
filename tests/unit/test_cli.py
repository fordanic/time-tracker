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


def test_no_arguments_is_a_successful_scaffold_command() -> None:
    assert main([]) == 0
