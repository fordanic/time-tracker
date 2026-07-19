from pathlib import Path

from time_tracker.infrastructure.ipc import _agent_command
from time_tracker.infrastructure.paths import AgentPaths


def test_frozen_agent_command_reuses_the_packaged_executable(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)

    command = _agent_command(paths, frozen=True)

    assert command[1] == "--agent"
    assert "-m" not in command


def test_source_agent_command_launches_the_agent_module(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)

    command = _agent_command(paths, frozen=False)

    assert command[1:3] == ["-m", "time_tracker.agent"]
