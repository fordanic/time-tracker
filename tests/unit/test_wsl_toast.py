import base64
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from time_tracker.infrastructure import wsl_toast
from time_tracker.infrastructure.wsl_toast import (
    APPLICATION_DISPLAY_NAME,
    APPLICATION_ID,
    MESSAGE_VARIABLE,
    TITLE_VARIABLE,
    WindowsToastDispatcher,
    interpreter_command,
    is_wsl_host,
    resolve_interpreter,
    toast_environment,
)

INTERPRETER = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


class FakeRunner:
    """Record invocations instead of starting a Windows process."""

    def __init__(
        self,
        results: list[tuple[int, str, str]] | None = None,
        *,
        timeout: bool = False,
    ) -> None:
        self.results = results or []
        self.timeout = timeout
        self.commands: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str]] = []
        self.timeouts: list[float] = []

    async def __call__(
        self,
        command: Sequence[str],
        environment: Mapping[str, str],
        timeout_seconds: float,
    ) -> tuple[int, str, str]:
        self.commands.append(tuple(command))
        self.environments.append(dict(environment))
        self.timeouts.append(timeout_seconds)
        if self.timeout:
            raise TimeoutError
        if self.results:
            return self.results.pop(0)
        return (0, "", "")

    def scripts(self) -> list[str]:
        return [
            base64.b64decode(command[4]).decode("utf-16-le")
            for command in self.commands
        ]


def dispatcher(runner: FakeRunner) -> WindowsToastDispatcher:
    return WindowsToastDispatcher(
        runner=runner,
        interpreter_factory=lambda: INTERPRETER,
    )


def write_kernel_release(directory: Path, release: str) -> Path:
    path = directory / "osrelease"
    path.write_text(release, encoding="utf-8")
    return path


def test_wsl_host_requires_microsoft_kernel_and_interop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time_tracker.infrastructure.wsl_toast.sys.platform", "linux")
    release = write_kernel_release(tmp_path, "6.18.33.2-microsoft-standard-WSL2\n")
    marker = tmp_path / "WSLInterop"
    marker.write_text("enabled", encoding="utf-8")

    assert is_wsl_host(kernel_release=release, interop_markers=(marker,))


def test_plain_linux_kernel_is_not_a_wsl_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time_tracker.infrastructure.wsl_toast.sys.platform", "linux")
    release = write_kernel_release(tmp_path, "6.11.0-19-generic\n")
    marker = tmp_path / "WSLInterop"
    marker.write_text("enabled", encoding="utf-8")

    assert not is_wsl_host(kernel_release=release, interop_markers=(marker,))


def test_wsl_kernel_without_interop_is_not_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time_tracker.infrastructure.wsl_toast.sys.platform", "linux")
    release = write_kernel_release(tmp_path, "6.18.33.2-microsoft-standard-WSL2\n")

    assert not is_wsl_host(
        kernel_release=release,
        interop_markers=(tmp_path / "missing",),
    )


def test_missing_kernel_release_is_not_a_wsl_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time_tracker.infrastructure.wsl_toast.sys.platform", "linux")

    assert not is_wsl_host(kernel_release=tmp_path / "missing")


def test_non_linux_platform_is_not_a_wsl_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time_tracker.infrastructure.wsl_toast.sys.platform", "win32")

    assert not is_wsl_host()


def test_interpreter_is_resolved_without_windows_paths_on_path() -> None:
    resolved = resolve_interpreter(
        which=lambda _: None,
        exists=lambda path: path == INTERPRETER,
    )

    assert resolved == INTERPRETER


def test_interpreter_falls_back_to_path_translation() -> None:
    translated = "/windows/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

    resolved = resolve_interpreter(
        which=lambda _: None,
        exists=lambda path: path == translated,
        translate=lambda _: translated,
    )

    assert resolved == translated


def test_unavailable_interpreter_resolves_to_none() -> None:
    assert (
        resolve_interpreter(
            which=lambda _: None,
            exists=lambda _: False,
            translate=lambda _: None,
        )
        is None
    )


def test_command_carries_a_constant_encoded_script() -> None:
    command = interpreter_command(INTERPRETER, "Write-Output 'ok'")

    assert command[:4] == (
        INTERPRETER,
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
    )
    assert base64.b64decode(command[4]).decode("utf-16-le") == "Write-Output 'ok'"


def test_environment_shares_text_and_preserves_inherited_wslenv() -> None:
    environment = toast_environment(
        "title",
        "message",
        base={"WSLENV": "WT_SESSION:WT_PROFILE_ID"},
    )

    assert environment[TITLE_VARIABLE] == "title"
    assert environment[MESSAGE_VARIABLE] == "message"
    assert environment["WSLENV"].split(":") == [
        "WT_SESSION",
        "WT_PROFILE_ID",
        TITLE_VARIABLE,
        MESSAGE_VARIABLE,
    ]


def test_environment_does_not_duplicate_shared_names() -> None:
    environment = toast_environment(
        "title",
        "message",
        base={"WSLENV": f"{TITLE_VARIABLE}:{MESSAGE_VARIABLE}"},
    )

    assert environment["WSLENV"].split(":") == [TITLE_VARIABLE, MESSAGE_VARIABLE]


@pytest.mark.asyncio
async def test_reminder_text_is_passed_as_data_not_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSLENV", "")
    title = 'Still tracking "Admin" / $(whoami)?'
    message = "Text with `backticks`, $vars, \\ and\nnewlines — café"
    runner = FakeRunner([(0, "existing", "")])

    await dispatcher(runner).send(title, message)

    toast = runner.environments[-1]
    assert toast[TITLE_VARIABLE] == title
    assert toast[MESSAGE_VARIABLE] == message
    for script in runner.scripts():
        assert title not in script
        assert message not in script
    for command in runner.commands:
        assert title not in command
        assert message not in command


@pytest.mark.asyncio
async def test_first_time_registration_sends_one_warm_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSLENV", "")
    runner = FakeRunner([(0, "created", "")])
    service = dispatcher(runner)

    await service.send("Still tracking time?", "The timer is still running.")
    await service.send("No timer is running", "Start a timer when you begin working.")

    warm_up = runner.environments[1]
    assert warm_up[TITLE_VARIABLE] == APPLICATION_DISPLAY_NAME
    assert warm_up[MESSAGE_VARIABLE] == "Desktop reminders are enabled."
    assert [environment[TITLE_VARIABLE] for environment in runner.environments] == [
        "",
        APPLICATION_DISPLAY_NAME,
        "Still tracking time?",
        "No timer is running",
    ]
    toasts = [script for script in runner.scripts() if "CreateToastNotifier" in script]
    assert len(toasts) == 3
    assert all(APPLICATION_ID in script for script in toasts)


@pytest.mark.asyncio
async def test_existing_identity_sends_no_warm_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSLENV", "")
    runner = FakeRunner([(0, "existing", "")])
    service = dispatcher(runner)

    await service.send("Still tracking time?", "The timer is still running.")
    await service.send("No timer is running", "Start a timer when you begin working.")

    assert [environment[TITLE_VARIABLE] for environment in runner.environments] == [
        "",
        "Still tracking time?",
        "No timer is running",
    ]


@pytest.mark.asyncio
async def test_identity_is_registered_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSLENV", "")
    runner = FakeRunner([(0, "existing", "")])
    service = dispatcher(runner)

    await service.send("first", "first")
    await service.send("second", "second")

    identity_scripts = [
        script for script in runner.scripts() if "Set-ItemProperty" in script
    ]
    assert len(identity_scripts) == 1
    assert APPLICATION_DISPLAY_NAME in identity_scripts[0]


@pytest.mark.asyncio
async def test_failed_registration_still_attempts_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSLENV", "")
    runner = FakeRunner([(1, "", "registry denied"), (0, "", "")])

    await dispatcher(runner).send("Still tracking time?", "running")

    assert runner.environments[-1][TITLE_VARIABLE] == "Still tracking time?"


@pytest.mark.asyncio
async def test_informational_error_output_is_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSLENV", "")
    runner = FakeRunner([(0, "existing", ""), (0, "", "#< CLIXML\n<Objs>...</Objs>")])

    await dispatcher(runner).send("title", "message")


@pytest.mark.asyncio
async def test_non_zero_exit_status_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WSLENV", "")
    runner = FakeRunner([(0, "existing", ""), (1, "", "no notifier")])

    with pytest.raises(RuntimeError, match="no notifier"):
        await dispatcher(runner).send("title", "message")


@pytest.mark.asyncio
async def test_timeout_raises_without_stalling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WSLENV", "")
    runner = FakeRunner(timeout=True)

    with pytest.raises(RuntimeError, match="did not finish in time"):
        await dispatcher(runner).send("title", "message")


@pytest.mark.asyncio
async def test_missing_interpreter_raises() -> None:
    service = WindowsToastDispatcher(
        runner=FakeRunner(),
        interpreter_factory=lambda: None,
    )

    with pytest.raises(RuntimeError, match="interpreter was not found"):
        await service.send("title", "message")


def test_default_dispatcher_uses_the_real_runner() -> None:
    service = WindowsToastDispatcher()

    assert service._runner is wsl_toast._run_interpreter  # noqa: SLF001
