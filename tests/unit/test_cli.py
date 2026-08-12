from pathlib import Path

import pytest

from time_tracker import __version__
from time_tracker.cli import main
from time_tracker.infrastructure.configuration import ConfigurationError
from time_tracker.infrastructure.paths import AgentPaths


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


def test_web_flag_launches_loopback_server_with_default_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: tuple[int, bool] | None = None

    def fake_launch(port: int, *, open_browser: bool) -> None:
        nonlocal received
        received = (port, open_browser)

    monkeypatch.setattr("time_tracker.cli.launch_web", fake_launch)

    assert main(["--web"]) == 0
    assert received == (47831, True)


def test_web_launch_accepts_explicit_port_and_no_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: tuple[int, bool] | None = None

    def fake_launch(port: int, *, open_browser: bool) -> None:
        nonlocal received
        received = (port, open_browser)

    monkeypatch.setattr("time_tracker.cli.launch_web", fake_launch)

    assert main(["--web", "--port", "48123", "--no-open"]) == 0
    assert received == (48123, False)


@pytest.mark.parametrize("arguments", [["--no-open"], ["--port", "48123"]])
def test_web_only_options_require_web(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(arguments)

    assert exit_info.value.code == 2


def test_config_path_flag_reports_platform_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--config-path"]) == 0

    assert capsys.readouterr().out == f"{AgentPaths.defaults().config}\n"


def test_invalid_configuration_is_reported_without_launching(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_config() -> None:
        raise ConfigurationError("invalid configuration at config.toml")

    monkeypatch.setattr("time_tracker.cli.launch_tui", reject_config)

    with pytest.raises(SystemExit) as exit_info:
        main([])

    assert exit_info.value.code == 2
    assert "invalid configuration at config.toml" in capsys.readouterr().err


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
