# Time Tracker

Time Tracker is a local-first, keyboard-driven terminal application for recording
time against activities within projects. It runs on Linux, Windows, and macOS,
stores data locally, and does not require an account or internet connection.

The Textual interface talks to a persistent local background process. Closing the
TUI leaves the background process, active timer, and reminders running.

## Features

- Track one activity at a time and switch activities without overlapping entries.
- Recover an active timer after the TUI closes, the process restarts, or the
  application crashes.
- Organize activities by project and archive or restore historical targets.
- Review, correct, and manually add completed entries.
- Filter history and view daily or project/activity totals.
- Export detailed entries and summaries as comma- or pipe-delimited UTF-8 text.
- Configure desktop reminders, delivery windows, snooze, and optional local
  input-idle detection.
- Use Track, Review, Manage, and Settings workflows entirely from the keyboard.

## Requirements and architecture

The two most important documents in this repository are:

- [Top-level requirements](docs/top-level-requirements.md), the authoritative
  source for durable product behavior, quality constraints, and scope.
- [Architecture](docs/architecture.md), the authoritative source for technical
  choices and boundaries.

[Feature requirements](docs/feature-requirements/README.md) define approved
additional behavior in one file per feature. They are subordinate to both
authoritative documents. A feature requirement must not conflict with or override
the top-level requirements or architecture. If an approved change needs to alter
a top-level product rule or architectural boundary, that change requires specific
approval and the corresponding authoritative document must be updated first or
in the same change. The approval must come from a repository maintainer and be
recorded in the change review.

The [competitive assessment](docs/competitive-assessment.md) is roadmap input,
not a requirements source.

## Repository overview

```text
src/time_tracker/
  domain/          Entities and business invariants
  application/     Use cases and infrastructure-independent ports
  infrastructure/  SQLite, IPC, configuration, notifications, and OS adapters
  agent/           Persistent background process and reminder scheduler
  tui/             Textual user interface
  cli.py           Command-line entry point

tests/
  unit/            Isolated behavior tests
  integration/     SQLite, IPC, export, recovery, and migration tests
  e2e/             Textual workflow tests

docs/              Requirements, architecture, roadmap, and release guidance
scripts/           Native build, packaged smoke, notification, and release tools
```

The background process is the single SQLite writer. Business rules remain
independent of Textual, SQLite, IPC, and operating-system integrations.

## Prerequisites

- CPython 3.14 or newer
- [uv](https://docs.astral.sh/uv/)
- GNU Make for the convenience targets

Native packages are built on their target operating system; PyInstaller builds
are not cross-platform.

## Install and run

Sync the locked development environment:

```shell
uv sync --all-groups --locked
```

Start the application:

```shell
uv run time-tracker
```

Or use the Make target, which syncs first:

```shell
make run
```

Enter a project and activity, then use the primary action or `F5` to start,
switch, or restart tracking. Use `F6` to stop. `F1` through `F4` open Track,
Review, Manage, and Settings; `Ctrl+K` shows all shortcuts.

Closing the TUI does not stop the background process or an active timer. Stop
only the background process with:

```shell
uv run time-tracker --stop-agent
```

The persisted active timer will be recovered the next time the application
starts. To locate the optional TOML configuration file, run:

```shell
uv run time-tracker --config-path
```

## Build

Build a native package for the current operating system:

```shell
make build
```

Artifacts are written to `dist/`. Linux and Windows produce one-file
executables; macOS produces an ad-hoc-signed `.app` bundle.

Exercise the packaged timer lifecycle after building:

```shell
make smoke-packaged
```

On an interactive desktop, test native notification delivery with:

```shell
make smoke-notification
```

See [Release guidance](docs/releases.md) for creating version commits and using
the GitHub release workflow.

## Development

`make help` lists all supported workflows. Common targets include:

```shell
make sync
make format
make test-unit
make test-integration
make test-e2e
make check
make build
```

`make` keeps disposable uv, Python, and PyInstaller caches in ignored
repository-local directories by default.

Before committing, run the complete check set:

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

`make check` runs the same checks after the environment has been synced.

## Contributing

1. Read the [top-level requirements](docs/top-level-requirements.md) and
   [architecture](docs/architecture.md) before changing behavior or technical
   boundaries.
2. For new feature behavior, add or update its individual file in
   [feature requirements](docs/feature-requirements/README.md) before
   implementation, including observable behavior, invariants, error handling,
   and acceptance criteria.
3. Obtain explicit approval from a repository maintainer, record it in the
   change review, and update the appropriate authoritative document if the
   proposed feature would change or conflict with a top-level requirement or
   architectural boundary.
4. Keep business logic outside the TUI, preserve the background process as the
   single database writer, and persist timer transitions before reporting
   success.
5. Add tests with implementation changes and run the relevant test tier while
   iterating, followed by the complete check set.
6. Follow the [commit guidelines](docs/commits.md) and keep commits small,
   coherent, and reviewable.

Repository-specific agent instructions are in [AGENTS.md](AGENTS.md).

## Status

The initial product baseline and selected TUI roadmap features are implemented:

- durable single-timer start, switch, restart, stop, recovery, and active-detail
  editing;
- completed-entry review, correction, missed-time entry, filtering, summaries,
  and export;
- recent-work selection and active/archived project and activity management;
- preparing new projects and activities from Manage without starting a timer;
- persistent reminder, theme, and export settings with live reload;
- reminder windows, snooze, and optional content-free input-idle detection;
- native reminder delivery to the Windows desktop from WSL; and
- responsive Track, Review, Manage, and Settings views with keyboard shortcuts.

The check workflow builds and exercises the packaged lifecycle on Linux, Windows,
and macOS; all three jobs passed on July 25, 2026. A local macOS arm64 app-bundle
lifecycle and Notification Center dispatch were validated on July 19, 2026. The
macOS Core Graphics idle-duration adapter was validated interactively on July
22, 2026. A versioned, ad-hoc-signed macOS arm64 release archive, checksum, and
packaged lifecycle were validated locally on July 24, 2026. The GitHub release
workflow published final release `0.1.0` on July 25, 2026, validating Linux,
Windows, and macOS archives, checksums, native version metadata, the annotated
tag, and final-release state. Reminder delivery to the Windows desktop from WSL
was validated interactively on July 27, 2026, on Ubuntu-24.04 under Windows 11
25H2, including delivery from the background process with no TUI open.

Known outstanding validation:

- run the native-notification smoke on interactive Linux and Windows desktops;
- validate idle-duration detection on supported interactive Linux X11 and
  Windows desktop sessions;
- run the GitHub release workflow end to end for a release candidate, verifying
  its Linux, Windows, and macOS archives, checksums, native version metadata,
  annotated tag, and prerelease state; and
- record any additional unmet acceptance criteria here when identified.

This section is the source of truth for current implementation and validation
status.

## Documentation

- [Top-level requirements](docs/top-level-requirements.md)
- [Architecture](docs/architecture.md)
- [Feature requirements](docs/feature-requirements/README.md)
- [Competitive assessment and TUI roadmap](docs/competitive-assessment.md)
- [Commit guidelines](docs/commits.md)
- [Release guidance](docs/releases.md)

## License

See [LICENSE](LICENSE).
