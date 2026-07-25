# Releases

Time Tracker release candidates and final releases are built and published from
development machines. The process does not use GitHub Actions, so it remains
available when hosted Actions minutes are exhausted.

## Version policy

`src/time_tracker/__init__.py` contains the one canonical application version.
Project metadata, `time-tracker --version`, the frozen executable, release asset
names, and the Git tag all derive from it.

- Final release: `X.Y.Z`, for example `0.2.0`
- Release candidate: `X.Y.ZrcN`, for example `0.2.0rc1`
- Git tag: `v<version>`, for example `v0.2.0rc1`

Increment `N` for another candidate of the same intended final release. A final
release is a new version commit without the `rcN` suffix; it is rebuilt rather
than relabeling candidate binaries.

## Prerequisites

- Install `uv`, GNU Make, Git, and GitHub CLI (`gh`).
- Authenticate GitHub CLI with an account allowed to publish this repository:

  ```shell
  gh auth login
  gh auth status
  ```

- Build on the target operating system. PyInstaller does not cross-compile.
- Start from a clean checkout of the same version commit on every target machine.

The current native formats are:

| Target | Raw package | Release archive |
| --- | --- | --- |
| Linux | one-file executable | `.tar.gz` |
| Windows | one-file `.exe` | `.zip` |
| macOS | ad-hoc-signed `.app` bundle | `.zip` |

Asset names contain the version, operating system, and normalized architecture,
for example `time-tracker-0.2.0rc1-macos-arm64.zip`. Every archive has an adjacent
`.sha256` file containing its digest and filename.

## Prepare a version

Set the candidate or final version:

```shell
make set-version VERSION=0.2.0rc1
```

This validates the value, updates the canonical source, and refreshes `uv.lock`
for the dynamic project metadata. Review and commit any changed files before
publication. Do not move or reuse an existing version tag.

To build without publishing:

```shell
make release-artifact
```

That command synchronizes the locked environment, runs all formatting, lint,
type, unit, integration, and end-to-end checks, builds the native package, runs
the packaged lifecycle smoke, verifies its `--version` output, and writes the
archive and checksum under `dist/release/`.

## Publish a release candidate

On the first target machine at the clean version commit, run:

```shell
make publish-release-candidate
```

The command repeats the complete local validation, creates annotated tag
`v<version>` when needed, pushes it, and publishes a visible GitHub prerelease
with generated notes and the local target's archive and checksum.

On each other target operating system, check out the exact same tagged commit and
run the same command. It verifies the existing tag and prerelease before
uploading that platform's differently named assets. Existing asset names are not
overwritten.

## Publish a final release

Set and commit the final version, then run on each target platform:

```shell
make set-version VERSION=0.2.0
make publish-release
```

The first publication creates the annotated final tag and visible non-prerelease
GitHub release. Later target machines add their validated assets to it.

Publication stops before changing Git or GitHub when the version kind is wrong,
the checkout is dirty, an existing tag identifies another commit, the frozen
version differs, or an archive/checksum is invalid. GitHub CLI authentication is
checked before a local tag is created. If publication is interrupted after the
correct tag or release exists, rerun the same command at the same commit to
continue.

The hosted check workflow is limited to branch and pull-request events; version
tag pushes do not dispatch it. Hosted CI remains useful when capacity is
available, but it is not a release prerequisite.
