# Time Tracker

A local-first time tracker for Linux, Windows, and macOS, with Linux as the
primary development environment. The MVP uses a keyboard-driven TUI; a GUI may be
added later on the same application core.

## MVP

- Organize activities within projects.
- Track one activity at a time, with automatically derived start, stop, and
  duration.
- Preserve an active timer across restarts and crashes.
- Continue reminders after the TUI closes by using a background process.
- Store data locally in SQLite and settings in TOML.
- Export completed entries to UTF-8 CSV.

Manual entry and editing, concurrent timers, cloud features, and the GUI are not
part of the MVP.

## Architecture

The Textual TUI is a client of a single Python background process. That process
owns timer state, reminders, and SQLite access. A versioned local protocol keeps
business logic independent of the TUI and available to a future GUI.

## Documentation

- [MVP requirements](docs/mvp-requirements.md) — product behavior and scope.
- [Architecture](docs/architecture.md) — technical choices and boundaries.
- [Agent guidance](AGENTS.md) — repository working rules.
- [Commit guidelines](docs/commits.md) — commit preparation and message format.

## Status

The timer walking skeleton is in place: the Textual TUI connects to a single
authenticated background process, creates or reuses project and activity names,
starts, switches, and stops one SQLite-backed timer, and restores an active timer
after TUI closure, agent restart, or forced process termination. The background
process also owns monotonic reminder scheduling, TOML-configured reminder
intervals, and native notification delivery after the TUI closes. The TUI lists
completed entries chronologically with their local start and stop times, derived
duration, and note, and exports completed entries to UTF-8 CSV with explicit
overwrite confirmation. Projects and activities can be archived from the TUI;
archived names disappear from new-timer suggestions and remain intact in history.
When connected, the TUI also presents due reminders; confirming an active reminder
restarts its interval without changing the timer, while ignoring it leaves the
timer running and reminders repeating.

The packaged lifecycle is exercised in CI on Linux, Windows, and macOS. A local
macOS arm64 app-bundle lifecycle and Notification Center dispatch were validated
on July 19, 2026; the corresponding Linux and Windows packaged results remain
pending until the updated CI workflow runs on those hosts.

## Development

Install [uv](https://docs.astral.sh/uv/) and sync the locked development
environment:

```shell
uv sync --all-groups --locked
```

The common workflows are available through `make`:

```shell
make help
make run
make check
make build
```

`make build` creates a native package for the current operating system in
`dist/`. Linux and Windows use one-file executables. macOS uses an ad-hoc-signed
`.app` bundle and its built-in notification command. Use
`make clean` to remove repository-local build and check artifacts.
To permanently remove the current user's Time Tracker database, configuration,
IPC secret, and runtime files, first stop any work you want to preserve and run
`make clear-local CONFIRM=1`.

Run the same checks used in CI:

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Run `uv run time-tracker` to open the TUI. Enter a project and activity, then use
the buttons or `F5`/`F6` to start and stop. Existing project and activity names
are suggested as you type; press the right arrow to accept a completion. Closing
the TUI leaves the background process and any active timer running. Run
`uv run time-tracker --stop-agent` to stop only the process; the persisted timer
remains active and is recovered the next time the application starts.

Enter a destination in the CSV export path field and press its button or `F7` to
export completed entries. Relative paths are resolved from the directory where
the TUI was launched, and `~` expands to the current user's home directory. If the
destination exists, the TUI requires a second export action before overwriting it.

Enter an existing project or activity and use its archive button or `F8`/`F9`.
Archiving leaves any running timer active, removes the name from future timer
suggestions, and preserves completed history. Archived names cannot be reused.

When a reminder becomes due while the TUI is connected, it appears below the
active timer. For an active timer, press its button or `F10` to confirm that it is
still active and restart the configured interval. Taking no action leaves the
timer running; use Stop or `F6` when the timer should end.

## Configuration

Run `uv run time-tracker --config-path` to locate the optional user-edited TOML
file. When the file does not exist, both reminders use their built-in defaults.
The complete supported configuration is:

```toml
[reminders]
inactive_enabled = true
inactive_interval_minutes = 5
active_enabled = true
active_interval_minutes = 30
```

Each reminder can be disabled independently. Intervals must be positive numbers.
Restart the background process after editing the file by running
`uv run time-tracker --stop-agent`, then reopen the TUI. Invalid TOML, unknown
keys, and invalid values are reported without changing the file.

After building, run the complete isolated package lifecycle check with
`make smoke-packaged`. It opens a headless TUI, starts a timer, closes the TUI,
reopens it, verifies recovery, stops the timer, and shuts down the packaged agent.
On an interactive desktop, `make smoke-notification` dispatches one real native
notification without opening the TUI; the operating system may request permission
the first time.

The checks, native build, and packaged lifecycle smoke run on Python 3.14 across
Linux, Windows, and macOS in GitHub Actions. Native notification delivery still
requires an interactive desktop session and is therefore a manual platform smoke.
