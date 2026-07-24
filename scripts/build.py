"""Build the native Time Tracker package for the current operating system."""

from __future__ import annotations

import platform
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from time_tracker import __version__

VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:rc(?P<candidate>[1-9]\d*))?$"
)


def version_components(version: str = __version__) -> tuple[int, int, int, int]:
    """Return the four integer fields used by Windows version resources."""
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise RuntimeError(f"unsupported application version: {version}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        int(match.group("candidate") or 0),
    )


def windows_version_resource(version: str = __version__) -> str:
    """Return the PyInstaller version resource for the Windows executable."""
    numeric_version = version_components(version)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric_version!r},
    prodvers={numeric_version!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('FileDescription', 'Time Tracker'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'time-tracker'),
          StringStruct('OriginalFilename', 'time-tracker.exe'),
          StringStruct('ProductName', 'Time Tracker'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def apply_macos_bundle_version(bundle: Path) -> None:
    """Set macOS bundle versions and restore its ad-hoc signature."""
    info_path = bundle / "Contents/Info.plist"
    with info_path.open("rb") as source:
        info = plistlib.load(source)
    info["CFBundleShortVersionString"] = __version__
    info["CFBundleVersion"] = ".".join(
        str(component) for component in version_components()[:3]
    )
    with info_path.open("wb") as destination:
        plistlib.dump(info, destination)
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(bundle)],
        check=True,
    )


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
        "--hidden-import",
        "textual.widgets._tab",
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
    elif platform.system() == "Windows":
        version_path = Path("build/time-tracker-version.txt")
        version_path.parent.mkdir(parents=True, exist_ok=True)
        version_path.write_text(windows_version_resource(), encoding="utf-8")
        command.extend(("--onefile", "--version-file", str(version_path)))
    else:
        command.append("--onefile")
    command.append("src/time_tracker/cli.py")
    subprocess.run(command, check=True)  # noqa: S603
    if platform.system() == "Darwin":
        apply_macos_bundle_version(Path("dist/time-tracker.app"))


if __name__ == "__main__":
    main()
