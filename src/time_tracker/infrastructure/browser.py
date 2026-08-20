"""Open the host's default browser without changing the web binding."""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from collections.abc import Callable, Sequence

from time_tracker.infrastructure.wsl_toast import (
    is_wsl_host,
    translate_windows_path,
)

_COMMAND_PROMPT_NAME = "cmd.exe"
_COMMAND_PROMPT_UNIX_PATH = "/mnt/c/Windows/System32/cmd.exe"
_COMMAND_PROMPT_WINDOWS_PATH = r"C:\Windows\System32\cmd.exe"
_OPEN_TIMEOUT_SECONDS = 10.0

WindowsBrowserRunner = Callable[[Sequence[str], float], bool]


def open_default_browser(
    url: str,
    *,
    wsl_detector: Callable[[], bool] | None = None,
    command_prompt_factory: Callable[[], str | None] | None = None,
    windows_runner: WindowsBrowserRunner | None = None,
    fallback: Callable[[str], bool] | None = None,
) -> bool:
    """Open ``url`` in Windows from WSL, or use the platform fallback."""
    detect_wsl = wsl_detector or is_wsl_host
    if detect_wsl():
        try:
            command_prompt = (command_prompt_factory or resolve_command_prompt)()
        except OSError, subprocess.SubprocessError, TimeoutError:
            command_prompt = None
        if command_prompt is not None:
            command = (
                command_prompt,
                "/d",
                "/c",
                "start",
                "",
                url,
            )
            try:
                if (windows_runner or _run_windows_browser)(
                    command, _OPEN_TIMEOUT_SECONDS
                ):
                    return True
            except OSError, subprocess.SubprocessError, TimeoutError:
                pass
    try:
        return (fallback or webbrowser.open)(url)
    except OSError, webbrowser.Error:
        return False


def resolve_command_prompt(
    *,
    which: Callable[[str], str | None] = shutil.which,
    exists: Callable[[str], bool] = os.path.exists,
    translate: Callable[[str], str | None] | None = None,
) -> str | None:
    """Locate ``cmd.exe`` even when Windows paths are absent from ``PATH``."""
    located = which(_COMMAND_PROMPT_NAME)
    if located is not None:
        return located
    if exists(_COMMAND_PROMPT_UNIX_PATH):
        return _COMMAND_PROMPT_UNIX_PATH
    translated = (translate or translate_windows_path)(_COMMAND_PROMPT_WINDOWS_PATH)
    if translated is not None and exists(translated):
        return translated
    return None


def _run_windows_browser(command: Sequence[str], timeout_seconds: float) -> bool:
    """Ask Windows to open a URL with its registered default handler."""
    completed = subprocess.run(  # noqa: S603
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout_seconds,
        check=False,
    )
    return completed.returncode == 0
