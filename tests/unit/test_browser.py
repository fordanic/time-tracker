import webbrowser
from collections.abc import Sequence

from time_tracker.infrastructure.browser import (
    open_default_browser,
    resolve_command_prompt,
)

URL = "http://127.0.0.1:47831"
COMMAND_PROMPT = "/mnt/c/Windows/System32/cmd.exe"


def test_wsl_opens_the_url_in_the_windows_default_browser() -> None:
    invocations: list[tuple[tuple[str, ...], float]] = []

    def run(command: Sequence[str], timeout: float) -> bool:
        invocations.append((tuple(command), timeout))
        return True

    def reject_fallback(_url: str) -> bool:
        raise AssertionError("the Linux browser fallback must not run")

    assert open_default_browser(
        URL,
        wsl_detector=lambda: True,
        command_prompt_factory=lambda: COMMAND_PROMPT,
        windows_runner=run,
        fallback=reject_fallback,
    )
    assert invocations == [
        (
            (COMMAND_PROMPT, "/d", "/c", "start", "", URL),
            10.0,
        )
    ]


def test_plain_linux_uses_the_platform_browser() -> None:
    opened: list[str] = []

    def reject_command_prompt_resolution() -> str | None:
        raise AssertionError("cmd.exe must not be resolved")

    def record_fallback(url: str) -> bool:
        opened.append(url)
        return True

    assert open_default_browser(
        URL,
        wsl_detector=lambda: False,
        command_prompt_factory=reject_command_prompt_resolution,
        fallback=record_fallback,
    )
    assert opened == [URL]


def test_wsl_windows_launch_failure_uses_the_platform_browser() -> None:
    opened: list[str] = []

    def record_fallback(url: str) -> bool:
        opened.append(url)
        return True

    assert open_default_browser(
        URL,
        wsl_detector=lambda: True,
        command_prompt_factory=lambda: COMMAND_PROMPT,
        windows_runner=lambda _command, _timeout: False,
        fallback=record_fallback,
    )
    assert opened == [URL]


def test_wsl_windows_launch_timeout_uses_the_platform_browser() -> None:
    opened: list[str] = []

    def time_out(_command: Sequence[str], _timeout: float) -> bool:
        raise TimeoutError

    def record_fallback(url: str) -> bool:
        opened.append(url)
        return True

    assert open_default_browser(
        URL,
        wsl_detector=lambda: True,
        command_prompt_factory=lambda: COMMAND_PROMPT,
        windows_runner=time_out,
        fallback=record_fallback,
    )
    assert opened == [URL]


def test_browser_errors_report_that_the_url_was_not_opened() -> None:
    def fail(_url: str) -> bool:
        raise webbrowser.Error("no browser")

    assert not open_default_browser(
        URL,
        wsl_detector=lambda: False,
        fallback=fail,
    )


def test_command_prompt_resolution_does_not_require_windows_on_path() -> None:
    translated = "/windows/c/Windows/System32/cmd.exe"

    assert (
        resolve_command_prompt(
            which=lambda _name: None,
            exists=lambda path: path == translated,
            translate=lambda _path: translated,
        )
        == translated
    )
