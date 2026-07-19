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

The first vertical walking skeleton is in place: the Textual TUI connects to a
single authenticated background process, creates a project and activity by name,
starts or stops one SQLite-backed timer, and restores an active timer when the TUI
reconnects. Broader project/activity management, reminders, history, export, and
packaging validation remain upcoming MVP work.

## Development

Install [uv](https://docs.astral.sh/uv/) and sync the locked development
environment:

```shell
uv sync --all-groups --locked
```

Run the same checks used in CI:

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Run `uv run time-tracker` to open the TUI. Enter a project and activity, then use
the buttons or `F5`/`F6` to start and stop. Closing the TUI leaves the background
process and any active timer running. Run `uv run time-tracker --stop-agent` to
stop only the process; the persisted timer remains active and is recovered the
next time the application starts.

The checks run on Python 3.14 across Linux, Windows, and macOS in GitHub Actions.
