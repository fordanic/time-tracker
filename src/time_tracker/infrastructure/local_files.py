"""Explicit cleanup of Time Tracker's platform-local runtime and data files."""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from pathlib import Path

from time_tracker.infrastructure.ipc import AgentClient, AgentUnavailableError
from time_tracker.infrastructure.paths import AgentPaths


def database_files(paths: AgentPaths) -> tuple[Path, ...]:
    """Return the SQLite database and its possible sidecar files."""
    return (
        paths.database,
        Path(f"{paths.database}-journal"),
        Path(f"{paths.database}-shm"),
        Path(f"{paths.database}-wal"),
    )


def local_files(paths: AgentPaths) -> tuple[Path, ...]:
    """Return the exact files owned by the current walking skeleton."""
    files = [
        *database_files(paths),
        paths.config,
        paths.secret,
        paths.lock,
        paths.log,
    ]
    if paths.family == "AF_UNIX":
        files.append(Path(paths.address))
    return tuple(files)


def _clear_files(files: Sequence[Path]) -> list[Path]:
    """Delete the selected existing files and report what was removed."""
    removed: list[Path] = []
    for path in files:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(path)
    return removed


def clear_database_files(paths: AgentPaths) -> list[Path]:
    """Delete only the SQLite database and its possible sidecar files."""
    return _clear_files(database_files(paths))


def clear_local_files(paths: AgentPaths) -> list[Path]:
    """Delete only existing files explicitly owned by Time Tracker."""
    return _clear_files(local_files(paths))


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
    parser.add_argument(
        "--database-only",
        action="store_true",
        help="delete only the SQLite database and its sidecar files",
    )
    arguments = parser.parse_args(argv)
    if not arguments.yes:
        target = "clear-database" if arguments.database_only else "clear-local"
        parser.error(f"deletion requires confirmation: make {target} CONFIRM=1")

    paths = AgentPaths.defaults()
    stop_agent(paths)
    removed = (
        clear_database_files(paths)
        if arguments.database_only
        else clear_local_files(paths)
    )
    if removed:
        for path in removed:
            print(f"removed {path}")
    else:
        kind = "database files" if arguments.database_only else "files"
        print(f"no local Time Tracker {kind} found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
