"""Dispatch one native notification from an isolated packaged agent."""

from __future__ import annotations

import subprocess
import tempfile

from run_packaged_smoke import packaged_executable


def main() -> None:
    """Fail unless the package's background agent dispatches successfully."""
    executable = packaged_executable()
    if not executable.is_file():
        raise SystemExit(f"packaged executable not found: {executable}")
    with tempfile.TemporaryDirectory(prefix="time-tracker-notification-") as directory:
        subprocess.run(  # noqa: S603
            [str(executable), "--notification-smoke", directory],
            check=True,
        )


if __name__ == "__main__":
    main()
