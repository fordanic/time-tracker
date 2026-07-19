"""Command-line entry point for Time Tracker."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from time_tracker import __version__
from time_tracker.infrastructure.ipc import (
    AgentClient,
    AgentUnavailableError,
    ensure_agent_running,
)
from time_tracker.infrastructure.paths import AgentPaths
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
    arguments = parser.parse_args(argv)
    if arguments.stop_agent:
        try:
            AgentClient(AgentPaths.defaults()).shutdown()
        except AgentUnavailableError:
            return 0
        return 0
    launch_tui()
    return 0


def launch_tui() -> None:
    """Start or reconnect to the background process, then run Textual."""
    client = ensure_agent_running(AgentPaths.defaults())
    TimeTrackerApp(client).run()


def run() -> None:
    """Run the console entry point."""
    raise SystemExit(main())


if __name__ == "__main__":
    run()
