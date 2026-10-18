"""Narrow adapter that delivers Windows toasts from a WSL host."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

APPLICATION_ID = "TimeTracker.Reminders"
APPLICATION_DISPLAY_NAME = "Time Tracker"
PROTOCOL_SCHEME = "time-tracker"
TITLE_VARIABLE = "TIME_TRACKER_TOAST_TITLE"
MESSAGE_VARIABLE = "TIME_TRACKER_TOAST_MESSAGE"
CHECKPOINT_VARIABLE = "TIME_TRACKER_CHECKPOINT_ID"
PROTOCOL_COMMAND_VARIABLE = "TIME_TRACKER_PROTOCOL_COMMAND"

_KERNEL_RELEASE = Path("/proc/sys/kernel/osrelease")
_INTEROP_MARKERS = (
    Path("/proc/sys/fs/binfmt_misc/WSLInterop"),
    Path("/proc/sys/fs/binfmt_misc/WSLInterop-late"),
)
_INTERPRETER_NAME = "powershell.exe"
_INTERPRETER_UNIX_PATH = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
_INTERPRETER_WINDOWS_PATH = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
_IDENTITY_KEY = rf"HKCU:\Software\Classes\AppUserModelId\{APPLICATION_ID}"
_PROTOCOL_KEY = rf"HKCU:\Software\Classes\{PROTOCOL_SCHEME}"
_TIMEOUT_SECONDS = 10.0
_WARM_UP_MESSAGE = "Desktop reminders are enabled."
_ACTION_COMMAND_SOURCE_VARIABLE = "TIME_TRACKER_ACTION_COMMAND"

# Reminder text is read from the process environment so that user-controlled
# content never becomes part of executable script source or a command line.
_TOAST_SCRIPT = (
    "$ErrorActionPreference = 'Stop'\n"
    "[Windows.UI.Notifications.ToastNotificationManager,"
    " Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null\n"
    "[Windows.Data.Xml.Dom.XmlDocument,"
    " Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null\n"
    "$template = [Windows.Data.Xml.Dom.XmlDocument]::new()\n"
    "$template.LoadXml(\"<toast><visual><binding template='ToastGeneric'>"
    '<text/><text/></binding></visual></toast>")\n'
    "$texts = $template.GetElementsByTagName('text')\n"
    f"$texts.Item(0).AppendChild($template.CreateTextNode($env:{TITLE_VARIABLE}))"
    " | Out-Null\n"
    f"$texts.Item(1).AppendChild($template.CreateTextNode($env:{MESSAGE_VARIABLE}))"
    " | Out-Null\n"
    f"if ($env:{CHECKPOINT_VARIABLE} -and $env:{PROTOCOL_COMMAND_VARIABLE}) {{\n"
    "  $actions = $template.CreateElement('actions')\n"
    "  foreach ($item in @(@('Continue','continue'), @('Snooze','snooze'), "
    "@('Stop','stop'), @('Switch activity','switch'))) {\n"
    "    $action = $template.CreateElement('action')\n"
    "    $action.SetAttribute('content', $item[0])\n"
    "    $uri = 'time-tracker://checkpoint/' + $item[1] + '/' + "
    f"$env:{CHECKPOINT_VARIABLE}\n"
    "    $action.SetAttribute('arguments', $uri)\n"
    "    $action.SetAttribute('activationType', 'protocol')\n"
    "    $actions.AppendChild($action) | Out-Null\n"
    "  }\n"
    "  $template.DocumentElement.AppendChild($actions) | Out-Null\n"
    "}\n"
    "$toast = [Windows.UI.Notifications.ToastNotification]::new($template)\n"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    f"'{APPLICATION_ID}').Show($toast)\n"
)

# Reports "created" only when this user had no identity yet, which is when
# Windows consumes the first toast sent from it.
_IDENTITY_SCRIPT = (
    "$ErrorActionPreference = 'Stop'\n"
    f"$key = '{_IDENTITY_KEY}'\n"
    "if (Test-Path -Path $key) { Write-Output 'existing' }\n"
    "else { New-Item -Path $key -Force | Out-Null; Write-Output 'created' }\n"
    "Set-ItemProperty -Path $key -Name DisplayName"
    f" -Value '{APPLICATION_DISPLAY_NAME}'\n"
    f"if ($env:{PROTOCOL_COMMAND_VARIABLE}) {{\n"
    f"  $protocol = '{_PROTOCOL_KEY}'\n"
    "  New-Item -Path $protocol -Force | Out-Null\n"
    "  Set-Item -Path $protocol -Value 'URL:Time Tracker checkpoint action'\n"
    "  New-ItemProperty -Path $protocol -Name 'URL Protocol' -Value '' -Force"
    " | Out-Null\n"
    "  $command = Join-Path $protocol 'shell\\open\\command'\n"
    "  New-Item -Path $command -Force | Out-Null\n"
    f"  Set-Item -Path $command -Value $env:{PROTOCOL_COMMAND_VARIABLE}\n"
    "}\n"
)

ToastRunner = Callable[
    [Sequence[str], Mapping[str, str], float],
    Awaitable[tuple[int, str, str]],
]


def protocol_handler_command(
    action_command: Sequence[str],
    *,
    distro_name: str | None,
) -> str | None:
    """Build the fixed Windows protocol command for the originating WSL app."""
    if not action_command or not distro_name:
        return None
    command = [
        r"C:\Windows\System32\wsl.exe",
        "--distribution",
        distro_name,
        "--exec",
        *action_command,
        "--notification-action",
    ]
    return f'{subprocess.list2cmdline(command)} "%1"'


def _action_command_from_environment(
    environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    values = os.environ if environment is None else environment
    raw = values.get(_ACTION_COMMAND_SOURCE_VARIABLE)
    if raw is None:
        return ()
    try:
        decoded: object = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if (
        not isinstance(decoded, list)
        or not decoded
        or not all(isinstance(item, str) and item for item in decoded)
    ):
        return ()
    return tuple(decoded)


def is_wsl_host(
    *,
    kernel_release: Path = _KERNEL_RELEASE,
    interop_markers: Sequence[Path] = _INTEROP_MARKERS,
) -> bool:
    """Report whether this Linux session runs under WSL with Windows interop."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        release = kernel_release.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if "microsoft" not in release.casefold():
        return False
    return any(marker.exists() for marker in interop_markers)


def resolve_interpreter(
    *,
    which: Callable[[str], str | None] = shutil.which,
    exists: Callable[[str], bool] = os.path.exists,
    translate: Callable[[str], str | None] | None = None,
) -> str | None:
    """Locate the Windows PowerShell interpreter without trusting ``PATH``."""
    located = which(_INTERPRETER_NAME)
    if located is not None:
        return located
    if exists(_INTERPRETER_UNIX_PATH):
        return _INTERPRETER_UNIX_PATH
    translated = (translate or translate_windows_path)(_INTERPRETER_WINDOWS_PATH)
    if translated is not None and exists(translated):
        return translated
    return None


def interpreter_command(interpreter: str, script: str) -> tuple[str, ...]:
    """Build an invocation that carries a constant script, never reminder text."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return (interpreter, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded)


def toast_environment(
    title: str,
    message: str,
    *,
    checkpoint_id: str | None = None,
    protocol_command: str | None = None,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Share reminder text with Windows as data through the environment."""
    environment = dict(os.environ if base is None else base)
    environment[TITLE_VARIABLE] = title
    environment[MESSAGE_VARIABLE] = message
    environment[CHECKPOINT_VARIABLE] = checkpoint_id or ""
    environment[PROTOCOL_COMMAND_VARIABLE] = protocol_command or ""
    shared = [name for name in environment.get("WSLENV", "").split(":") if name]
    for name in (
        TITLE_VARIABLE,
        MESSAGE_VARIABLE,
        CHECKPOINT_VARIABLE,
        PROTOCOL_COMMAND_VARIABLE,
    ):
        if name not in shared:
            shared.append(name)
    environment["WSLENV"] = ":".join(shared)
    return environment


class WindowsToastDispatcher:
    """Deliver one toast per reminder through the Windows notification platform."""

    def __init__(
        self,
        *,
        runner: ToastRunner | None = None,
        interpreter_factory: Callable[[], str | None] | None = None,
        timeout_seconds: float = _TIMEOUT_SECONDS,
        action_command: Sequence[str] | None = None,
        distro_name: str | None = None,
    ) -> None:
        self._runner = runner or _run_interpreter
        self._interpreter_factory = interpreter_factory or resolve_interpreter
        self._timeout_seconds = timeout_seconds
        self._protocol_command = protocol_handler_command(
            action_command or _action_command_from_environment(),
            distro_name=distro_name or os.environ.get("WSL_DISTRO_NAME"),
        )
        self._interpreter: str | None = None
        self._identity_prepared = False
        self._protocol_registered = False
        self._lock = asyncio.Lock()

    async def send(
        self,
        title: str,
        message: str,
        *,
        checkpoint_id: str | None = None,
    ) -> None:
        """Show a toast, or raise when Windows delivery is unavailable."""
        interpreter = await self._resolved_interpreter()
        await self._prepare_identity(interpreter)
        await self._dispatch(
            interpreter,
            _TOAST_SCRIPT,
            title,
            message,
            checkpoint_id=checkpoint_id,
        )

    async def _resolved_interpreter(self) -> str:
        if self._interpreter is None:
            self._interpreter = await asyncio.to_thread(self._interpreter_factory)
        if self._interpreter is None:
            raise RuntimeError("the Windows PowerShell interpreter was not found")
        return self._interpreter

    async def _prepare_identity(self, interpreter: str) -> None:
        async with self._lock:
            if self._identity_prepared:
                return
            # Attempt registration once per process: a failure here still leaves
            # delivery worth attempting under an identity Windows may know.
            self._identity_prepared = True
            try:
                returncode, stdout, stderr = await self._run(
                    interpreter, _IDENTITY_SCRIPT, {}
                )
                if returncode != 0:
                    raise RuntimeError(
                        stderr.strip()
                        or f"identity registration exited with status {returncode}"
                    )
            except OSError, RuntimeError, TimeoutError:
                logger.exception("registering the Windows notification identity failed")
                return
            self._protocol_registered = self._protocol_command is not None
            if stdout.strip() != "created":
                return
            try:
                await self._dispatch(
                    interpreter,
                    _TOAST_SCRIPT,
                    APPLICATION_DISPLAY_NAME,
                    _WARM_UP_MESSAGE,
                )
            except OSError, RuntimeError, TimeoutError:
                logger.exception("the Windows notification warm-up failed")

    async def _dispatch(
        self,
        interpreter: str,
        script: str,
        title: str,
        message: str,
        *,
        checkpoint_id: str | None = None,
    ) -> None:
        returncode, _, stderr = await self._run(
            interpreter,
            script,
            {
                TITLE_VARIABLE: title,
                MESSAGE_VARIABLE: message,
                CHECKPOINT_VARIABLE: checkpoint_id or "",
            },
            share_protocol_command=self._protocol_registered,
        )
        # Windows PowerShell writes an informational progress record to the error
        # stream on first module use, so only the exit status decides delivery.
        if returncode != 0:
            detail = stderr.strip() or f"exit status {returncode}"
            raise RuntimeError(f"Windows rejected the toast notification: {detail}")

    async def _run(
        self,
        interpreter: str,
        script: str,
        text: Mapping[str, str],
        *,
        share_protocol_command: bool = True,
    ) -> tuple[int, str, str]:
        environment = toast_environment(
            text.get(TITLE_VARIABLE, ""),
            text.get(MESSAGE_VARIABLE, ""),
            checkpoint_id=text.get(CHECKPOINT_VARIABLE) or None,
            protocol_command=(
                self._protocol_command if share_protocol_command else None
            ),
        )
        try:
            return await self._runner(
                interpreter_command(interpreter, script),
                environment,
                self._timeout_seconds,
            )
        except TimeoutError:
            raise RuntimeError(
                "the Windows notification interpreter did not finish in time"
            ) from None


async def _run_interpreter(
    command: Sequence[str],
    environment: Mapping[str, str],
    timeout_seconds: float,
) -> tuple[int, str, str]:
    """Run the interpreter under a timeout so the agent loop cannot stall."""
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=dict(environment),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def translate_windows_path(path: str) -> str | None:
    """Translate a Windows path for a distribution with a custom mount root."""
    wslpath = shutil.which("wslpath")
    if wslpath is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603
            [wslpath, "-u", path],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None
