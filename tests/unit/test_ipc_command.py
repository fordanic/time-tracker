import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from time_tracker.infrastructure.ipc import (
    PROTOCOL_VERSION,
    AgentClient,
    AgentRequestError,
    _agent_command,
)
from time_tracker.infrastructure.paths import AgentPaths


def test_client_serializes_requests_from_concurrent_workers(tmp_path: Path) -> None:
    class RecordingClient(AgentClient):
        def __init__(self, paths: AgentPaths) -> None:
            super().__init__(paths)
            self.guard = threading.Lock()
            self.active_requests = 0
            self.maximum_active_requests = 0

        def _request_serialized(
            self,
            method: str,
            params: dict[str, object],
            *,
            version: int,
        ) -> object:
            with self.guard:
                self.active_requests += 1
                self.maximum_active_requests = max(
                    self.maximum_active_requests,
                    self.active_requests,
                )
            time.sleep(0.01)
            with self.guard:
                self.active_requests -= 1
            return None

    client = RecordingClient(AgentPaths.in_directory(tmp_path))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: client.ping(), range(8)))

    assert client.maximum_active_requests == 1


def test_frozen_agent_command_reuses_the_packaged_executable(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)

    command = _agent_command(paths, frozen=True)

    assert command[1] == "--agent"
    assert "-m" not in command
    assert command[command.index("--config") + 1] == str(paths.config)


def test_source_agent_command_launches_the_agent_module(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)

    command = _agent_command(paths, frozen=False)

    assert command[1:3] == ["-m", "time_tracker.agent"]
    assert command[command.index("--config") + 1] == str(paths.config)


def test_shutdown_retries_the_previous_protocol_for_an_upgraded_agent(
    tmp_path: Path,
) -> None:
    class RecordingClient(AgentClient):
        def __init__(self, paths: AgentPaths) -> None:
            super().__init__(paths)
            self.versions: list[int] = []

        def _request(
            self,
            method: str,
            params: dict[str, object],
            *,
            version: int = PROTOCOL_VERSION,
        ) -> object:
            self.versions.append(version)
            if version == PROTOCOL_VERSION:
                raise AgentRequestError("unsupported protocol version")
            return None

    client = RecordingClient(AgentPaths.in_directory(tmp_path))

    client.shutdown()

    assert client.versions == [PROTOCOL_VERSION, PROTOCOL_VERSION - 1]
