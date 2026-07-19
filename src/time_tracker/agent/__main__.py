"""Launch the Time Tracker background process."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from time_tracker.agent.server import serve
from time_tracker.infrastructure.paths import AgentPaths


def main(argv: Sequence[str] | None = None) -> int:
    """Parse resolved endpoint paths and run the agent server."""
    parser = argparse.ArgumentParser(prog="time-tracker-agent")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--address", required=True)
    parser.add_argument("--secret", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--family", required=True, choices=("AF_UNIX", "AF_PIPE"))
    arguments = parser.parse_args(argv)
    serve(
        AgentPaths(
            database=arguments.database,
            address=arguments.address,
            secret=arguments.secret,
            lock=arguments.lock,
            family=arguments.family,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
