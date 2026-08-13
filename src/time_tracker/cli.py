"""Command-line entry point for Time Tracker."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from time_tracker import __version__
from time_tracker.agent.server import serve
from time_tracker.infrastructure.configuration import ConfigurationError, load_config
from time_tracker.infrastructure.instance_lock import (
    ForegroundAlreadyRunningError,
    foreground_lock,
)
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
    parser.add_argument(
        "--web",
        action="store_true",
        help="run the optional same-machine web interface",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=47831,
        help="loopback port for --web (default: 47831)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="with --web, print the URL instead of opening a browser",
    )
    parser.add_argument(
        "--config-path",
        action="store_true",
        help="print the user configuration file path and exit",
    )
    parser.add_argument("--agent", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--packaged-smoke", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--notification-smoke",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--database", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, help=argparse.SUPPRESS)
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
    if not arguments.web and (arguments.port != 47831 or arguments.no_open):
        parser.error("--port and --no-open require --web")
    if arguments.web and (
        arguments.stop_agent
        or arguments.config_path
        or arguments.packaged_smoke is not None
        or arguments.notification_smoke is not None
        or arguments.agent
    ):
        parser.error("--web cannot be combined with another launch mode")
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if arguments.agent:
        internal_values = (
            arguments.database,
            arguments.config,
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
                config=arguments.config,
                address=arguments.address,
                secret=arguments.secret,
                lock=arguments.lock,
                log=arguments.log,
                family=arguments.family,
            )
        )
        return 0
    if arguments.config_path:
        print(AgentPaths.defaults().config)
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
    try:
        if arguments.web:
            launch_web(arguments.port, open_browser=not arguments.no_open)
        else:
            launch_tui()
    except (ConfigurationError, ForegroundAlreadyRunningError) as error:
        parser.error(str(error))
    return 0


def launch_tui() -> None:
    """Start or reconnect to the background process, then run Textual."""
    paths = AgentPaths.defaults()
    load_config(paths.config)
    with foreground_lock(paths.foreground_lock):
        client = ensure_agent_running(paths)
        TimeTrackerApp(client).run()


def launch_web(port: int, *, open_browser: bool) -> None:
    """Start the optional loopback-only web interface."""
    from time_tracker.web.server import run_web_server

    paths = AgentPaths.defaults()
    load_config(paths.config)
    with foreground_lock(paths.foreground_lock):
        client = ensure_agent_running(paths)
        run_web_server(client, port=port, open_browser=open_browser)


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
