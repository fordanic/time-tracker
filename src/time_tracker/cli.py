"""Command-line entry point for Time Tracker."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from time_tracker import __version__
from time_tracker.agent.server import serve
from time_tracker.infrastructure.ipc import (
    AgentClient,
    AgentUnavailableError,
    ensure_agent_running,
)
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.packaged_smoke import run_packaged_lifecycle
from time_tracker.tui.app import TimeTrackerApp


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the TUI or explicitly stop its persistent background process."""
    parser = argparse.ArgumentParser(prog="time-tracker")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--stop-agent",
        action="store_true",
        help="stop the background process without closing an active timer",
    )
    parser.add_argument("--agent", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--packaged-smoke", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--notification-smoke",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--database", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--address", help=argparse.SUPPRESS)
    parser.add_argument("--secret", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--lock", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--log", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--family",
        choices=("AF_UNIX", "AF_PIPE"),
        help=argparse.SUPPRESS,
    )
    arguments = parser.parse_args(argv)
    if arguments.agent:
        internal_values = (
            arguments.database,
            arguments.address,
            arguments.secret,
            arguments.lock,
            arguments.log,
            arguments.family,
        )
        if any(value is None for value in internal_values):
            parser.error("the internal agent requires all resolved paths")
        serve(
            AgentPaths(
                database=arguments.database,
                address=arguments.address,
                secret=arguments.secret,
                lock=arguments.lock,
                log=arguments.log,
                family=arguments.family,
            )
        )
        return 0
    if arguments.stop_agent:
        try:
            AgentClient(AgentPaths.defaults()).shutdown()
        except AgentUnavailableError:
            return 0
        return 0
    if arguments.packaged_smoke is not None:
        asyncio.run(run_packaged_lifecycle(arguments.packaged_smoke))
        print("packaged lifecycle smoke passed")
        return 0
    if arguments.notification_smoke is not None:
        asyncio.run(_send_notification_smoke(arguments.notification_smoke))
        print("native notification smoke dispatched")
        return 0
    launch_tui()
    return 0


def launch_tui() -> None:
    """Start or reconnect to the background process, then run Textual."""
    client = ensure_agent_running(AgentPaths.defaults())
    TimeTrackerApp(client).run()


async def _send_notification_smoke(directory: Path) -> None:
    """Ask an isolated packaged agent to notify while no TUI is open."""
    paths = AgentPaths.in_directory(directory)
    client = ensure_agent_running(paths)
    try:
        await asyncio.to_thread(client.send_test_notification)
    finally:
        client.shutdown()


def run() -> None:
    """Run the console entry point."""
    raise SystemExit(main())


if __name__ == "__main__":
    run()
