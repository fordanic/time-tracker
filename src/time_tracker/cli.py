"""Command-line entry point for Time Tracker."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from time_tracker import __version__


def main(argv: Sequence[str] | None = None) -> int:
    """Parse command-line arguments for the application scaffold."""
    parser = argparse.ArgumentParser(prog="time-tracker")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)
    return 0


def run() -> None:
    """Run the console entry point."""
    raise SystemExit(main())


if __name__ == "__main__":
    run()
