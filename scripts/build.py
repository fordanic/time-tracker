"""Build the native Time Tracker package for the current operating system."""

from __future__ import annotations

import platform
import subprocess
import sys


def main() -> None:
    """Run PyInstaller with the platform-specific packaging shape."""
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "time-tracker",
        "--paths",
        "src",
        "--specpath",
        "build",
        "--collect-data",
        "time_tracker.infrastructure.migrations",
        "--collect-data",
        "desktop_notifier",
        "--hidden-import",
        "desktop_notifier.resources",
    ]
    if platform.system() == "Darwin":
        command.extend(
            (
                "--onedir",
                "--windowed",
                "--osx-bundle-identifier",
                "io.timetracker.app",
            )
        )
    else:
        command.append("--onefile")
    command.append("src/time_tracker/cli.py")
    subprocess.run(command, check=True)  # noqa: S603


if __name__ == "__main__":
    main()
