# Versioned release candidates and releases

**Status:** Implemented

## Purpose

Make a reviewed build identifiable and repeatable, and allow release
candidates and final releases to be built, validated, and published consistently
by a manually dispatched GitHub Actions workflow.

## Required behavior

- Keep one canonical application version. Use `X.Y.Z` for a final version and
  `X.Y.ZrcN`, where `N` starts at one, for a release candidate.
- Derive Python project metadata and `time-tracker --version` from that canonical
  value. Use it for Windows file-version resources and macOS bundle metadata, and
  use `v<version>` as the corresponding Git tag.
- Provide one command to set and validate the canonical version and refresh the
  lockfile for the dynamic project metadata.
- Provide a manually dispatched GitHub Actions workflow that accepts the expected
  version and whether it is a release candidate or final release. Reject a
  mismatch between those inputs and the canonical version in the selected
  commit.
- On Linux, Windows, and macOS GitHub-hosted runners, run the complete checks,
  build the native package, run the packaged lifecycle smoke, verify the frozen
  executable reports the canonical version, and create a versioned archive plus
  SHA-256 checksum.
- Name release assets with the application version, operating system, and CPU
  architecture so independently built platform assets coexist in one GitHub
  release.
- After every platform job succeeds, create or verify one annotated
  `v<version>` tag for the workflow commit and create or resume its GitHub
  release using the workflow's repository token.
- Publish a candidate as a visible GitHub prerelease and a final version as a
  visible GitHub release. Generate release notes from Git history through GitHub.

## Invariants and error handling

- Reject malformed versions, a candidate publication for a final version, and a
  final publication for a candidate version before building or changing GitHub
  state.
- Refuse publication when an existing version tag points to another commit, is
  lightweight rather than annotated, when a packaged executable reports another
  version, or when any expected archive or checksum is absent or invalid.
- Grant write permission only to the publication job. Build jobs use read-only
  repository access and pass their archives to publication through workflow
  artifacts.
- Re-running the workflow for the same version commit is resumable: reuse the
  exact annotated tag and release, preserve existing release assets, and upload
  only missing asset names.
- Build each native artifact on its target operating system; do not present
  PyInstaller as a cross-compiler.
- Serialize workflow runs per version so two dispatches cannot publish the same
  version concurrently.

## Acceptance criteria

1. Project metadata, the source CLI, and the frozen executable report the same
   canonical final or release-candidate version.
2. One workflow dispatch produces all three documented platform archives and
   checksums, and every checksum verifies its exact archive bytes.
3. Publication begins only after the Linux, Windows, and macOS checks, builds,
   packaged lifecycle smokes, version checks, and packaging steps succeed.
4. Candidate publication creates or reuses `vX.Y.ZrcN` and a GitHub prerelease;
   final publication creates or reuses `vX.Y.Z` and a non-prerelease release.
5. Re-running a partially completed publication preserves existing assets and
   uploads only missing platform assets.
6. Unit tests cover version validation and replacement, platform/architecture
   naming, version verification, archive contents, checksums, and publication
   request validation.

## Documentation impact

- Top-level requirements now require consistent build identity and permit
  workflow-validated GitHub downloads. Architecture records the version source,
  native artifact format, and GitHub Actions publication boundary. No product
  data or protocol migration is required.
