# Releases

Time Tracker release candidates and final releases are built, validated, and
published by the manually dispatched GitHub Actions release workflow. Development
machines prepare and review the version change; they do not build or upload the
official release artifacts.

## Version policy

`src/time_tracker/__init__.py` contains the one canonical application version.
Project metadata, `time-tracker --version`, the frozen executable, release asset
names, and the Git tag all derive from it.

- Final release: `X.Y.Z`, for example `0.2.0`
- Release candidate: `X.Y.ZrcN`, for example `0.2.0rc1`
- Git tag: `v<version>`, for example `v0.2.0rc1`

Increment `N` for another candidate of the same intended final release. A final
release is a new version commit without the `rcN` suffix; candidate binaries are
never relabeled.

## Prepare a version

From a branch based on current `main`, set the candidate or final version:

```shell
make set-version VERSION=0.2.0rc1
```

This validates the value, updates the canonical source, and refreshes `uv.lock`
for the dynamic project metadata. Review the changes, run `make check`, commit
them, and merge them through the normal review process. Do not create, move, or
reuse the version tag manually.

The release workflow must run against the reviewed version commit on `main`.

## Run the GitHub release workflow

1. Open the repository's **Actions** page and choose **Release**.
2. Select **Run workflow** and use `main` at the reviewed version commit.
3. Enter the exact canonical version, such as `0.2.0rc1`.
4. Choose **candidate** for an `rc` version or **final** for a version without an
   `rc` suffix.
5. Start the workflow and review every job before treating the release as
   published.

The same operation can be dispatched with GitHub CLI:

```shell
gh workflow run release.yml \
  --ref main \
  -f version=0.2.0rc1 \
  -f release_kind=candidate
```

The workflow rejects an expected version that differs from the canonical version
in the selected commit and rejects a candidate/final choice that does not match
the version form.

## Build and publication behavior

The workflow runs the complete formatting, lint, type, unit, integration, and
end-to-end checks on Linux, Windows, and macOS. Each platform then:

1. builds its native PyInstaller package;
2. exercises the complete packaged timer lifecycle;
3. verifies the frozen executable reports the canonical version; and
4. creates a versioned archive and SHA-256 checksum.

Only after all three platform jobs succeed does the publication job receive
write access. It verifies every checksum, creates an annotated `v<version>` tag
at the workflow commit, and publishes all platform assets in one GitHub release.
A candidate becomes a visible prerelease; a final version becomes a visible
non-prerelease release. GitHub generates the release notes from repository
history.

The current native formats are:

| Target | Raw package | Release archive |
| --- | --- | --- |
| Linux | one-file executable | `.tar.gz` |
| Windows | one-file `.exe` | `.zip` |
| macOS | ad-hoc-signed `.app` bundle | `.zip` |

Asset names contain the version, operating system, and normalized architecture,
for example `time-tracker-0.2.0rc1-macos-arm64.zip`. Every archive has an adjacent
`.sha256` file containing its digest and filename.

## Failure and rerun behavior

No tag or release is created when a validation, test, build, smoke, version, or
packaging step fails.

The workflow stops publication when an existing tag points to another commit, is
not annotated, or the existing release has the wrong candidate/final state.
Runs for the same version are serialized. Re-running a partially completed
publication at the same commit reuses the correct tag and release, preserves
existing assets, and uploads only missing asset names.

For local troubleshooting, `make release-artifact` runs the same checks, native
build, packaged smoke, archive, and checksum steps for the current operating
system. Its output is diagnostic only; official assets are always produced by
the GitHub release workflow.
