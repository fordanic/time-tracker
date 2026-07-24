"""Build and publish versioned native Time Tracker releases locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

VERSION_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:rc(?P<candidate>[1-9]\d*))?$"
)
VERSION_ASSIGNMENT_PATTERN = re.compile(r'(?m)^__version__ = "(?P<version>[^"]+)"$')
PublishKind = Literal["candidate", "final"]
PackagedVersionReader = Callable[[Path], str]
LockRefresher = Callable[[str, Path], None]


class ReleaseError(RuntimeError):
    """Report a release precondition or operation failure."""


@dataclass(frozen=True)
class AppVersion:
    """A supported application version."""

    value: str
    candidate: int | None

    @property
    def is_candidate(self) -> bool:
        """Return whether this is a release-candidate version."""
        return self.candidate is not None

    @property
    def tag(self) -> str:
        """Return the Git tag corresponding to this version."""
        return f"v{self.value}"


@dataclass(frozen=True)
class Artifact:
    """Paths and labels for one target-platform release artifact."""

    source: Path
    archive: Path
    checksum: Path
    operating_system: str
    architecture: str


@dataclass(frozen=True)
class TagReference:
    """A resolved Git tag and whether it is an annotated tag object."""

    commit: str
    annotated: bool


def parse_version(value: str) -> AppVersion:
    """Validate and parse a supported final or release-candidate version."""
    match = VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ReleaseError(
            "version must be X.Y.Z or X.Y.ZrcN with no leading zeroes "
            "and a candidate number of at least 1"
        )
    candidate_text = match.group("candidate")
    return AppVersion(
        value=value,
        candidate=int(candidate_text) if candidate_text is not None else None,
    )


def repository_root() -> Path:
    """Return the repository root containing this script."""
    return Path(__file__).resolve().parents[1]


def version_file(root: Path) -> Path:
    """Return the canonical application-version file."""
    return root / "src/time_tracker/__init__.py"


def read_version(root: Path) -> AppVersion:
    """Read the canonical application version."""
    path = version_file(root)
    match = VERSION_ASSIGNMENT_PATTERN.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ReleaseError(f"canonical version assignment not found in {path}")
    return parse_version(match.group("version"))


def replace_version(root: Path, version: AppVersion) -> str:
    """Replace the canonical version and return the previous file contents."""
    path = version_file(root)
    original = path.read_text(encoding="utf-8")
    updated, replacements = VERSION_ASSIGNMENT_PATTERN.subn(
        f'__version__ = "{version.value}"',
        original,
    )
    if replacements != 1:
        raise ReleaseError(
            f"expected one canonical version assignment in {path}, found {replacements}"
        )
    path.write_text(updated, encoding="utf-8")
    return original


def refresh_lock(uv: str, root: Path) -> None:
    """Refresh the uv lockfile after project metadata changes."""
    subprocess.run(
        [uv, "lock"],
        cwd=root,
        check=True,
    )


def set_version(
    root: Path,
    value: str,
    uv: str = "uv",
    *,
    lock_refresher: LockRefresher = refresh_lock,
) -> AppVersion:
    """Set the canonical version and refresh the lockfile."""
    version = parse_version(value)
    source_path = version_file(root)
    lock_path = root / "uv.lock"
    original_source = source_path.read_text(encoding="utf-8")
    original_lock = lock_path.read_text(encoding="utf-8")
    replace_version(root, version)
    try:
        lock_refresher(uv, root)
    except OSError, subprocess.CalledProcessError:
        source_path.write_text(original_source, encoding="utf-8")
        lock_path.write_text(original_lock, encoding="utf-8")
        raise
    return version


def target_labels(system: str, machine: str) -> tuple[str, str]:
    """Normalize operating-system and machine labels for asset names."""
    operating_systems = {
        "Darwin": "macos",
        "Linux": "linux",
        "Windows": "windows",
    }
    try:
        operating_system = operating_systems[system]
    except KeyError as error:
        raise ReleaseError(f"unsupported release operating system: {system}") from error

    normalized_machine = machine.strip().lower()
    architecture_aliases = {
        "aarch64": "arm64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "i386": "x86",
        "i686": "x86",
        "x64": "x86_64",
        "x86": "x86",
        "x86_64": "x86_64",
    }
    architecture = architecture_aliases.get(normalized_machine)
    if architecture is None:
        architecture = re.sub(r"[^a-z0-9_]+", "-", normalized_machine).strip("-")
    if not architecture:
        raise ReleaseError("could not determine the release CPU architecture")
    return operating_system, architecture


def artifact_for(
    root: Path,
    version: AppVersion,
    *,
    system: str | None = None,
    machine: str | None = None,
) -> Artifact:
    """Resolve source and destination paths for one native artifact."""
    actual_system = system or platform.system()
    operating_system, architecture = target_labels(
        actual_system,
        machine or platform.machine(),
    )
    if actual_system == "Darwin":
        source = root / "dist/time-tracker.app"
        extension = ".zip"
    elif actual_system == "Windows":
        source = root / "dist/time-tracker.exe"
        extension = ".zip"
    else:
        source = root / "dist/time-tracker"
        extension = ".tar.gz"
    archive = (
        root
        / "dist/release"
        / f"time-tracker-{version.value}-{operating_system}-{architecture}{extension}"
    )
    return Artifact(
        source=source,
        archive=archive,
        checksum=archive.with_name(f"{archive.name}.sha256"),
        operating_system=operating_system,
        architecture=architecture,
    )


def packaged_executable(artifact: Artifact) -> Path:
    """Return the executable inside a raw PyInstaller artifact."""
    if artifact.operating_system == "macos":
        return artifact.source / "Contents/MacOS/time-tracker"
    return artifact.source


def read_packaged_version(executable: Path) -> str:
    """Run a packaged executable and return its reported application version."""
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ReleaseError(
            f"could not run packaged executable: {executable}"
        ) from error
    return result.stdout.strip()


def verify_packaged_version(
    executable: Path,
    version: AppVersion,
    *,
    reader: PackagedVersionReader = read_packaged_version,
) -> None:
    """Fail unless a packaged executable reports the canonical version."""
    actual = reader(executable)
    expected = f"time-tracker {version.value}"
    if actual != expected:
        raise ReleaseError(
            f"packaged executable reported {actual!r}, expected {expected!r}"
        )


def package_release_artifact(
    root: Path,
    *,
    system: str | None = None,
    machine: str | None = None,
    version_reader: PackagedVersionReader = read_packaged_version,
) -> Artifact:
    """Verify and archive the current target-platform PyInstaller build."""
    version = read_version(root)
    artifact = artifact_for(root, version, system=system, machine=machine)
    if not artifact.source.exists():
        raise ReleaseError(f"native package not found: {artifact.source}")
    executable = packaged_executable(artifact)
    if not executable.is_file():
        raise ReleaseError(f"packaged executable not found: {executable}")
    verify_packaged_version(executable, version, reader=version_reader)

    artifact.archive.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = artifact.archive.with_name(f".{artifact.archive.name}.tmp")
    temporary_checksum = artifact.checksum.with_name(f".{artifact.checksum.name}.tmp")
    temporary_archive.unlink(missing_ok=True)
    temporary_checksum.unlink(missing_ok=True)
    try:
        if artifact.archive.name.endswith(".tar.gz"):
            with tarfile.open(temporary_archive, "w:gz") as archive:
                archive.add(artifact.source, arcname=artifact.source.name)
        elif artifact.operating_system == "macos":
            subprocess.run(
                [
                    "ditto",
                    "-c",
                    "-k",
                    "--sequesterRsrc",
                    "--keepParent",
                    str(artifact.source),
                    str(temporary_archive),
                ],
                check=True,
            )
        else:
            with zipfile.ZipFile(
                temporary_archive,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                archive.write(artifact.source, arcname=artifact.source.name)
        os.replace(temporary_archive, artifact.archive)
        digest = sha256(artifact.archive)
        temporary_checksum.write_text(
            f"{digest}  {artifact.archive.name}\n",
            encoding="utf-8",
        )
        os.replace(temporary_checksum, artifact.checksum)
    finally:
        temporary_archive.unlink(missing_ok=True)
        temporary_checksum.unlink(missing_ok=True)
    return artifact


def sha256(path: Path) -> str:
    """Return the hexadecimal SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_checksum(artifact: Artifact) -> None:
    """Fail unless an artifact checksum names and matches the archive."""
    if not artifact.archive.is_file():
        raise ReleaseError(f"release archive not found: {artifact.archive}")
    if not artifact.checksum.is_file():
        raise ReleaseError(f"release checksum not found: {artifact.checksum}")
    expected = f"{sha256(artifact.archive)}  {artifact.archive.name}"
    actual = artifact.checksum.read_text(encoding="utf-8").strip()
    if actual != expected:
        raise ReleaseError(f"release checksum does not match {artifact.archive}")


def validate_publish_kind(version: AppVersion, kind: PublishKind) -> None:
    """Ensure a version has the kind requested by the publication command."""
    if kind == "candidate" and not version.is_candidate:
        raise ReleaseError(
            f"{version.value} is a final version; use the final publication command"
        )
    if kind == "final" and version.is_candidate:
        raise ReleaseError(
            f"{version.value} is a release candidate; "
            "use the candidate publication command"
        )


def require_clean_status(status: str) -> None:
    """Fail when Git reports tracked or untracked checkout changes."""
    if status.strip():
        raise ReleaseError("release publication requires a clean Git checkout")


def require_matching_tag(
    tag: str,
    *,
    head_commit: str,
    tag_commit: str | None,
) -> None:
    """Fail when an existing local release tag identifies another commit."""
    if tag_commit is not None and tag_commit != head_commit:
        raise ReleaseError(
            f"existing tag {tag} points to {tag_commit}, "
            f"not current commit {head_commit}"
        )


def require_annotated_tag(tag: str, *, annotated: bool) -> None:
    """Fail when an existing release tag is lightweight."""
    if not annotated:
        raise ReleaseError(f"existing tag {tag} is not an annotated tag")


def _run(
    command: Sequence[str],
    *,
    root: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )


def _git_output(root: Path, *arguments: str) -> str:
    return _run(["git", *arguments], root=root).stdout.strip()


def _existing_tag_commit(root: Path, tag: str) -> str | None:
    result = _run(
        ["git", "rev-list", "-n", "1", tag],
        root=root,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def remote_tag_reference_from_ls_remote(
    output: str,
    tag: str,
) -> TagReference | None:
    """Resolve a remote lightweight or annotated tag listing."""
    direct_commit: str | None = None
    peeled_commit: str | None = None
    direct_reference = f"refs/tags/{tag}"
    peeled_reference = f"{direct_reference}^{{}}"
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        commit, reference = fields
        if reference == direct_reference:
            direct_commit = commit
        elif reference == peeled_reference:
            peeled_commit = commit
    if peeled_commit is not None:
        return TagReference(commit=peeled_commit, annotated=True)
    if direct_commit is not None:
        return TagReference(commit=direct_commit, annotated=False)
    return None


def _remote_tag_reference(
    root: Path,
    remote: str,
    tag: str,
) -> TagReference | None:
    result = _run(
        [
            "git",
            "ls-remote",
            "--tags",
            remote,
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        ],
        root=root,
    )
    return remote_tag_reference_from_ls_remote(result.stdout, tag)


def _existing_release(root: Path, tag: str) -> dict[str, object] | None:
    result = _run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--json",
            "isDraft,isPrerelease,tagName",
        ],
        root=root,
        check=False,
    )
    if result.returncode == 0:
        loaded = json.loads(result.stdout)
        if not isinstance(loaded, dict):
            raise ReleaseError(f"unexpected GitHub release metadata for {tag}")
        return loaded
    error_message = f"{result.stdout}\n{result.stderr}".lower()
    if "release not found" in error_message or "not found" in error_message:
        return None
    raise ReleaseError(
        result.stderr.strip() or f"could not inspect GitHub release {tag}"
    )


def publish_release(
    root: Path,
    kind: PublishKind,
    *,
    remote: str = "origin",
) -> None:
    """Create or extend a GitHub release with the local platform artifact."""
    version = read_version(root)
    validate_publish_kind(version, kind)
    artifact = artifact_for(root, version)
    validate_checksum(artifact)
    verify_packaged_version(packaged_executable(artifact), version)

    status = _git_output(root, "status", "--porcelain=v1")
    require_clean_status(status)
    head_commit = _git_output(root, "rev-parse", "HEAD")
    tag_commit = _existing_tag_commit(root, version.tag)
    require_matching_tag(
        version.tag,
        head_commit=head_commit,
        tag_commit=tag_commit,
    )
    if tag_commit is not None:
        local_tag_type = _git_output(
            root,
            "cat-file",
            "-t",
            f"refs/tags/{version.tag}",
        )
        require_annotated_tag(version.tag, annotated=local_tag_type == "tag")

    _run(["gh", "auth", "status", "--hostname", "github.com"], root=root)
    remote_tag = _remote_tag_reference(root, remote, version.tag)
    if remote_tag is not None:
        require_matching_tag(
            version.tag,
            head_commit=head_commit,
            tag_commit=remote_tag.commit,
        )
        require_annotated_tag(version.tag, annotated=remote_tag.annotated)
    else:
        if tag_commit is None:
            _run(
                [
                    "git",
                    "tag",
                    "--annotate",
                    version.tag,
                    "--message",
                    f"Time Tracker {version.value}",
                ],
                root=root,
            )
        _run(["git", "push", remote, f"refs/tags/{version.tag}"], root=root)

    existing_release = _existing_release(root, version.tag)
    expected_prerelease = kind == "candidate"
    if existing_release is None:
        command = [
            "gh",
            "release",
            "create",
            version.tag,
            str(artifact.archive),
            str(artifact.checksum),
            "--verify-tag",
            "--title",
            f"Time Tracker {version.value}",
            "--generate-notes",
        ]
        if expected_prerelease:
            command.append("--prerelease")
        result = _run(command, root=root)
        if result.stdout:
            print(result.stdout.strip())
        return

    if existing_release.get("tagName") != version.tag:
        raise ReleaseError(f"GitHub returned another tag for {version.tag}")
    if bool(existing_release.get("isDraft")):
        raise ReleaseError(
            f"GitHub release {version.tag} is a draft; publish it before uploading"
        )
    if bool(existing_release.get("isPrerelease")) != expected_prerelease:
        raise ReleaseError(
            f"GitHub release {version.tag} has the wrong prerelease state"
        )
    _run(
        [
            "gh",
            "release",
            "upload",
            version.tag,
            str(artifact.archive),
            str(artifact.checksum),
        ],
        root=root,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and publish native Time Tracker releases locally."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version", help="print the canonical application version")

    set_version_parser = subparsers.add_parser(
        "set-version",
        help="set the canonical version and refresh uv.lock",
    )
    set_version_parser.add_argument("value")
    set_version_parser.add_argument(
        "--uv",
        default=os.environ.get("UV", "uv"),
        help="uv executable to use (default: UV or uv)",
    )

    subparsers.add_parser(
        "package",
        help="archive and checksum the current native package",
    )
    publish_parser = subparsers.add_parser(
        "publish",
        help="create or extend a GitHub release",
    )
    publish_parser.add_argument("kind", choices=("candidate", "final"))
    publish_parser.add_argument("--remote", default="origin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local release command."""
    arguments = _parser().parse_args(argv)
    root = repository_root()
    try:
        if arguments.command == "version":
            print(read_version(root).value)
        elif arguments.command == "set-version":
            version = set_version(root, arguments.value, arguments.uv)
            print(f"set Time Tracker version to {version.value}")
        elif arguments.command == "package":
            artifact = package_release_artifact(root)
            print(artifact.archive)
            print(artifact.checksum)
        elif arguments.command == "publish":
            publish_release(root, arguments.kind, remote=arguments.remote)
        else:
            raise AssertionError(f"unknown command: {arguments.command}")
    except (OSError, ReleaseError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        print(f"release error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
