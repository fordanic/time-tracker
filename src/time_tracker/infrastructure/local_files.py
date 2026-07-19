"""Explicit cleanup of Time Tracker's platform-local runtime and data files."""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from pathlib import Path

from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths


def local_files(paths: AgentPaths) -> tuple[Path, ...]:
    """Return the exact files owned by the current walking skeleton."""
    files = [
        paths.database,
        Path(f"{paths.database}-journal"),
        Path(f"{paths.database}-shm"),
        Path(f"{paths.database}-wal"),
        paths.config,
        paths.secret,
        paths.lock,
        paths.log,
    ]
    if paths.family == "AF_UNIX":
        files.append(Path(paths.address))
    return tuple(files)


def clear_local_files(paths: AgentPaths) -> list[Path]:
    """Delete only existing files explicitly owned by Time Tracker."""
    removed: list[Path] = []
    for path in local_files(paths):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(path)
    return removed


def stop_agent(paths: AgentPaths, *, timeout_seconds: float = 2.0) -> None:
    """Stop the agent and wait until it no longer accepts connections."""
    client = AgentClient(paths)
    try:
        client.shutdown()
    except AgentUnavailableError:
        return

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            client.ping()
        except AgentUnavailableError:
            return
        time.sleep(0.01)
    raise RuntimeError("the Time Tracker agent did not stop; local data was preserved")


def main(argv: Sequence[str] | None = None) -> int:
    """Guard and perform deletion of the current user's local app files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm permanent deletion of all local Time Tracker data",
    )
    arguments = parser.parse_args(argv)
    if not arguments.yes:
        parser.error("deletion requires confirmation: make clear-local CONFIRM=1")

    paths = AgentPaths.defaults()
    stop_agent(paths)
    removed = clear_local_files(paths)
    if removed:
        for path in removed:
            print(f"removed {path}")
    else:
        print("no local Time Tracker files found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
