# Time Tracker

Time Tracker is a local-first, keyboard-driven application for recording time
against activities within projects. It provides a default terminal interface and
an optional same-machine web interface. It runs on Linux, Windows, and macOS,
stores data locally, and does not require an account or internet connection.

Both interfaces talk to a persistent local background process. Closing the TUI
or web server leaves the background process, active timer, and reminders running.

## Features

- Track one activity at a time and switch activities without overlapping entries.
- Select one of five recent project/activity pairs with `1`–`5`, review the
  pending action and optional note, and confirm it with `Enter`.
- Recover an active timer after the TUI closes, the process restarts, or the
  application crashes.
- Organize activities by project and archive or restore historical targets.
- Review, correct, permanently delete, and manually add completed entries.
- Filter history and view daily or project/activity totals.
- Export detailed entries and summaries as comma- or pipe-delimited UTF-8 text.
- Configure desktop reminders, delivery windows, snooze, and optional local
  input-idle detection.
- Choose a color palette in Settings that is applied immediately and restored on
  the next launch.
- Use Track, Review, Manage, and Settings workflows entirely from the keyboard.
- Use the same workflows in a responsive local web UI from phone-sized to desktop
  browser widths, without LAN access or hosted services.

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
  web/             Secure loopback HTTP adapter and compiled browser assets
  cli.py           Command-line entry point

web/               Preact/TypeScript source, tests, and build configuration

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
- Node.js 22 or newer for frontend development and native package builds
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

Start the optional web interface on the fixed same-machine origin
`http://127.0.0.1:47831`:

```shell
uv run time-tracker --web
```

The page opens after the server is ready. Use `--no-open` to print the URL for
manual opening, or `--port PORT` to choose a different loopback port. The server
cannot listen on LAN interfaces. The TUI remains the default, and Time Tracker
rejects launching the TUI and web interface simultaneously.

Select recent work with `1` through `5`, optionally enter its quick-switch note,
and press `Enter` to confirm Start or Switch. A selected current pair remains a
no-op. For work outside the deck, use Manual entry's project, activity, and
separate note fields, then press `F5` or its Start action. Stop and Update current
timer controls follow that action. `F1` through `F4` open Track, Review, Manage,
and Settings; `Ctrl+K` shows all shortcuts.

In the web interface, `1` through `5` select and focus recent work, `Tab` moves
from that selection to its optional note, and `Enter` confirms from either place.
Use the browser-safe `T`, `R`, `M`, and `S` keys to change views while focus is
outside an editable field. While editing outside a dialog, press `Escape` and
then `T`, `R`, `M`, or `S` within 1.5 seconds to change views. On Track, `G`
starts or switches, `U` updates the active entry, and `X` stops it. The same
actions work from editable fields with `Ctrl`/`Command`+`Enter`,
`Ctrl`/`Command`+`Shift`+`Enter`, and
`Ctrl`/`Command`+`Alt`/`Option`+`Enter`, respectively. `?` toggles the visible
shortcut guide. Review filters refresh automatically as they change.

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

## Logs

The background process writes one log file, `agent.log`. It records operational
failures that do not interrupt tracking, such as a native reminder the desktop
rejected or an idle-duration adapter that became unavailable. Tracked time,
project and activity names, notes, and input details are never written to it.

Its location follows the platform's per-user log convention:

| Platform | Location |
| --- | --- |
| Linux | `~/.local/state/time-tracker/log/agent.log` |
| macOS | `~/Library/Logs/time-tracker/agent.log` |
| Windows | `%LOCALAPPDATA%\Time Tracker\time-tracker\Logs\agent.log` |

A WSL distribution uses the Linux location inside that distribution.

An isolated instance writes `agent.log` into its own directory instead of the
per-user location, so the end-to-end tests, `make smoke-packaged`, and
`make smoke-notification` never touch the per-user log.

The TUI reports failures it can act on directly in its message area; the log is
where to look when a reminder never reached the desktop while no TUI was open.

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
make test-web
make web-build
make check
make build
```

`make` keeps disposable uv, Python, and PyInstaller caches in ignored
repository-local directories by default.

To stop the background agent and permanently delete only the local tracking
database while preserving configuration, credentials, and logs, explicitly
confirm the destructive operation:

```shell
make clear-database CONFIRM=1
```

To populate that empty database with a fixed manual-testing data set covering
the most recent 45 complete local calendar days, run:

```shell
make seed-test-data CONFIRM=1
```

The seed contains multiple projects and activities, varied completed entries,
and notes. Every weekday has entries and weekends have none. The command stops
the agent before writing and refuses to mix simulated entries into a non-empty
database.

Before committing, sync both locked environments and run the complete check set:

```shell
make sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
cd web && npm run format:check
cd web && npm run lint
cd web && npm run typecheck
cd web && npm run test
cd web && npm run test:e2e
cd web && npm run build
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

The initial product baseline, selected TUI roadmap features, and local web GUI
are implemented:

- durable single-timer start, switch, restart, stop, recovery, and active-detail
  editing;
- completed-entry review, correction, confirmed deletion, missed-time entry,
  filtering, summaries, and export;
- recent-work selection and active/archived project and activity management;
- preparing new projects and activities from Manage without starting a timer;
- persistent reminder, color-palette, and export settings with live reload;
- reminder windows, snooze, and optional content-free input-idle detection;
- native reminder delivery to the Windows desktop from WSL;
- responsive Track, Review, Manage, and Settings views with keyboard shortcuts;
  and
- a five-item quick-switch deck with deliberate selection, optional-note, and
  Enter-confirmation behavior; and
- a loopback-only responsive Preact web interface with Track, Review, Manage, and
  Settings parity, browser-local appearance, strict same-origin launch security,
  and serialized IPC through the existing single-writer agent.

On August 12, 2026, the web UI passed Python adapter integration tests, frontend
format/lint/type/unit/build checks, a real-agent Chromium end-to-end workflow,
and interactive in-app-browser inspection at 320, 720, and desktop widths. The
compiled browser payload is approximately 39 KB JavaScript and 9 KB CSS before
compression, with no third-party runtime requests. The extended frozen macOS
arm64 TUI-and-web lifecycle also passed; the resulting app bundle is 27 MB and
contains the 56 KB compiled web shell without a Node runtime.

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
- validate the local web UI interactively in Safari, Firefox, and WSL;
- run the extended packaged TUI-and-web lifecycle on Linux and Windows release
  artifacts;
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
