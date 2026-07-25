from __future__ import annotations

import hashlib
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import build, release


def _minimal_repository(root: Path, version: str = "0.1.0") -> None:
    package = root / "src/time_tracker"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        f'"""Test package."""\n\n__version__ = "{version}"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        f'version = 1\n\n[[package]]\nname = "time-tracker"\nversion = "{version}"\n',
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("value", "candidate"),
    [
        ("0.1.0", None),
        ("1.2.3", None),
        ("1.2.3rc1", 1),
        ("10.20.30rc42", 42),
    ],
)
def test_parse_version_accepts_supported_versions(
    value: str,
    candidate: int | None,
) -> None:
    parsed = release.parse_version(value)

    assert parsed.value == value
    assert parsed.candidate == candidate
    assert parsed.tag == f"v{value}"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1",
        "1.2",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-rc.1",
        "1.2.3rc0",
        "1.2.3beta1",
        "v1.2.3",
    ],
)
def test_parse_version_rejects_unsupported_versions(value: str) -> None:
    with pytest.raises(release.ReleaseError, match="version must be"):
        release.parse_version(value)


def test_set_version_updates_source_and_refreshes_lockfile(
    tmp_path: Path,
) -> None:
    _minimal_repository(tmp_path)

    refreshed: list[tuple[str, Path]] = []

    def fake_uv_lock(uv: str, root: Path) -> None:
        refreshed.append((uv, root))

    updated = release.set_version(
        tmp_path,
        "0.2.0rc1",
        lock_refresher=fake_uv_lock,
    )

    assert updated.value == "0.2.0rc1"
    assert release.read_version(tmp_path) == updated
    assert refreshed == [("uv", tmp_path)]


def test_target_labels_normalize_supported_platform_names() -> None:
    assert release.target_labels("Darwin", "arm64") == ("macos", "arm64")
    assert release.target_labels("Linux", "AMD64") == ("linux", "x86_64")
    assert release.target_labels("Windows", "aarch64") == ("windows", "arm64")


def test_native_version_metadata_supports_finals_and_candidates() -> None:
    assert build.version_components("1.2.3") == (1, 2, 3, 0)
    assert build.version_components("1.2.3rc4") == (1, 2, 3, 4)

    resource = build.windows_version_resource("1.2.3rc4")
    assert "filevers=(1, 2, 3, 4)" in resource
    assert "StringStruct('ProductVersion', '1.2.3rc4')" in resource


def test_windows_build_uses_absolute_version_resource_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.build.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "scripts.build.subprocess.run",
        lambda command, check: commands.append(command),
    )

    build.main()

    version_path = tmp_path / "build/time-tracker-version.txt"
    assert version_path.is_file()
    assert commands
    version_argument = commands[0][commands[0].index("--version-file") + 1]
    assert Path(version_argument) == version_path
    assert Path(version_argument).is_absolute()


def test_linux_release_archive_and_checksum(tmp_path: Path) -> None:
    _minimal_repository(tmp_path, "1.2.3rc2")
    executable = tmp_path / "dist/time-tracker"
    executable.parent.mkdir()
    executable.write_bytes(b"native executable")

    artifact = release.package_release_artifact(
        tmp_path,
        system="Linux",
        machine="x86_64",
        version_reader=lambda _: "time-tracker 1.2.3rc2",
    )

    assert artifact.archive.name == "time-tracker-1.2.3rc2-linux-x86_64.tar.gz"
    with tarfile.open(artifact.archive, "r:gz") as archive:
        assert "time-tracker" in archive.getnames()
    digest = hashlib.sha256(artifact.archive.read_bytes()).hexdigest()
    assert artifact.checksum.read_text(encoding="utf-8") == (
        f"{digest}  {artifact.archive.name}\n"
    )
    release.validate_checksum(artifact)


def test_windows_release_archive_contains_executable(tmp_path: Path) -> None:
    _minimal_repository(tmp_path)
    executable = tmp_path / "dist/time-tracker.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"native executable")

    artifact = release.package_release_artifact(
        tmp_path,
        system="Windows",
        machine="AMD64",
        version_reader=lambda _: "time-tracker 0.1.0",
    )

    assert artifact.archive.name == "time-tracker-0.1.0-windows-x86_64.zip"
    with zipfile.ZipFile(artifact.archive) as archive:
        assert archive.namelist() == ["time-tracker.exe"]


def test_packaging_rejects_a_mismatched_frozen_version(tmp_path: Path) -> None:
    _minimal_repository(tmp_path)
    executable = tmp_path / "dist/time-tracker"
    executable.parent.mkdir()
    executable.write_bytes(b"native executable")

    with pytest.raises(release.ReleaseError, match="packaged executable reported"):
        release.package_release_artifact(
            tmp_path,
            system="Linux",
            machine="x86_64",
            version_reader=lambda _: "time-tracker 9.9.9",
        )


def test_release_kind_must_match_version() -> None:
    with pytest.raises(release.ReleaseError, match="final version"):
        release.validate_release_kind(release.parse_version("1.2.3"), "candidate")
    with pytest.raises(release.ReleaseError, match="release candidate"):
        release.validate_release_kind(release.parse_version("1.2.3rc1"), "final")


def test_release_request_matches_canonical_version_and_kind() -> None:
    release.validate_release_request(
        release.parse_version("1.2.3rc2"),
        "candidate",
        "1.2.3rc2",
    )


def test_release_request_rejects_another_expected_version() -> None:
    with pytest.raises(release.ReleaseError, match="workflow requested"):
        release.validate_release_request(
            release.parse_version("1.2.3rc2"),
            "candidate",
            "1.2.3rc3",
        )


def test_release_request_rejects_malformed_expected_version() -> None:
    with pytest.raises(release.ReleaseError, match="version must be"):
        release.validate_release_request(
            release.parse_version("1.2.3rc2"),
            "candidate",
            "v1.2.3rc2",
        )
