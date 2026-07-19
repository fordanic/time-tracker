"""Run the frozen lifecycle check using an isolated temporary data directory."""

from __future__ import annotations

import platform
import subprocess
import tempfile
from pathlib import Path


def packaged_executable() -> Path:
    """Resolve the platform-specific output created by ``make build``."""
    root = Path(__file__).resolve().parents[1]
    if platform.system() == "Darwin":
        return root / "dist/time-tracker.app/Contents/MacOS/time-tracker"
    suffix = ".exe" if platform.system() == "Windows" else ""
    return root / f"dist/time-tracker{suffix}"


def main() -> None:
    """Fail unless the packaged binary completes the full timer lifecycle."""
    executable = packaged_executable()
    if not executable.is_file():
        raise SystemExit(f"packaged executable not found: {executable}")
    with tempfile.TemporaryDirectory(prefix="time-tracker-smoke-") as directory:
        subprocess.run(  # noqa: S603
            [str(executable), "--packaged-smoke", directory],
            check=True,
        )


if __name__ == "__main__":
    main()
