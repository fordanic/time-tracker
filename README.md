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

The Python package scaffold and cross-platform checks are in place. The first
implementation milestone is a walking skeleton that starts the background
process, creates a project and activity, tracks and persists one entry, and
restores it after restart.
