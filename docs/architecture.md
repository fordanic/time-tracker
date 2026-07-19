# Architecture

This document is the technical source of truth for the MVP. Product behavior and
scope belong in [MVP Requirements](mvp-requirements.md).

## Overview

```text
+-------------+       local IPC       +--------------------+
| Textual TUI | <-------------------> | Background process |
+-------------+                       +---------+----------+
                                                |
                                      +---------+----------+
                                      |                    |
                                  +---v----+         +-----v------+
                                  | SQLite |         | OS notifier |
                                  +--------+         +------------+
```

The TUI is a client. One long-lived background process owns timer state,
reminders, and all database writes. Closing the TUI does not stop that process.
The same boundary will allow a future GUI to reuse the application core.

## Technology choices

| Concern | Choice |
| --- | --- |
| Runtime | CPython 3.14 |
| Project management | `uv`, `pyproject.toml`, and a `src/` layout |
| TUI | Textual |
| Background work | `asyncio` |
| Local IPC | `multiprocessing.connection` |
| Persistence | Standard-library `sqlite3` and numbered SQL migrations |
| Configuration | TOML via `tomllib` |
| Platform paths | `platformdirs` |
| Notifications | Narrow native adapter: `desktop-notifier` on Linux/Windows, `osascript` on macOS |
| Local binaries | PyInstaller, run separately on each target OS |
| Quality tools | pytest, pytest-asyncio, Ruff, and mypy |

An ORM, dependency-injection framework, network service, and external migration
framework are intentionally unnecessary for the MVP.

## Process and IPC

- Starting the TUI starts the background process if needed; an explicit lifecycle
  command stops it. Starting at login is deferred.
- Prevent a second background process with an instance lock.
- Use `AF_UNIX` sockets on Linux and macOS and `AF_PIPE` named pipes on Windows.
- Authenticate connections with a per-user secret.
- Send versioned UTF-8 JSON using `send_bytes` and `recv_bytes`; never use the
  pickle-based `send` or `recv` methods.
- A request has a protocol version, request ID, method, and parameters. A response
  has the request ID and either a result or structured error.
- The MVP supports one foreground client. Multiple concurrent clients are not a
  protocol guarantee.

The agent runs reminder scheduling on its asyncio loop and moves blocking IPC and
SQLite calls to worker threads. Requests are still handled serially, so the agent
remains the single database writer while notification deadlines are not stalled.

## Code boundaries

```text
src/time_tracker/
  domain/             # Entities and invariants; no framework dependencies
  application/        # Use cases and ports
  infrastructure/     # SQLite, IPC, config, notifications, platform adapters
  agent/              # Background process and reminder scheduler
  tui/                # Textual interface
  cli.py               # TUI launch and process lifecycle

tests/
  unit/
  integration/
  e2e/
```

- Domain and application code must not depend on Textual, SQLite, IPC, or a
  notification library.
- Interfaces call application use cases; they do not implement timer rules.
- Clocks, repositories, and notification services are injected for deterministic
  testing. No dependency-injection framework is used.
- A future GUI uses the same background process and protocol and never accesses
  SQLite or TUI code directly.

## Persistence and time

The minimal SQLite model is:

```text
Project(id, name, archived_at?, created_at)
Activity(id, project_id, name, archived_at?, created_at)
TimeEntry(id, activity_id, started_at_utc, stopped_at_utc?, note?, created_at)
```

- Enable foreign keys for every connection.
- Track applied numbered SQL migrations in `schema_migrations`.
- Use transactions for timer transitions. Switching stops the current entry and
  starts the next with one captured timestamp.
- Archive projects and activities through agent-owned application use cases.
  Selection queries exclude archived rows, while archived names remain reserved;
  an archive transition does not mutate the active timer or historical entries.
- Enforce at most one entry with no stop time using a partial unique index.
- Store UTC instants as integer microseconds since the Unix epoch. Convert them to
  local, offset-aware ISO 8601 values at presentation and export boundaries.
- Derive duration from timestamps; do not store an independently mutable duration.
- Use a monotonic clock for in-process scheduling and persisted UTC instants for
  recovery.
- CSV export is an agent application use case: it reads completed entries through
  the repository port and writes through a CSV output port. The TUI resolves the
  destination path and sends an explicit overwrite-confirmation flag over IPC;
  active entries are excluded by the completed-entry query.

SQLite and the background process remain authoritative even when notification
delivery fails or the TUI disconnects.

## Configuration, notifications, and packaging

- Read user-edited TOML with `tomllib`; defaults live in typed application
  configuration. Invalid input is reported without rewriting the file.
- The optional TOML file has one `[reminders]` table with independent
  `inactive_enabled`/`active_enabled` booleans and positive
  `inactive_interval_minutes`/`active_interval_minutes` numbers. Configuration
  is loaded when the background process starts; restart it to apply edits.
- Use `platformdirs` for per-user configuration, data, state, runtime, and log
  locations.
- Use simple native notifications. Interactive notification actions are deferred;
  users act through the TUI.
- `desktop-notifier` uses desktop services on Linux and WinRT on Windows. macOS
  uses its built-in `osascript` notification command: on the current macOS 26
  validation host, `UNUserNotificationCenter` rejected an otherwise valid
  ad-hoc-signed local bundle. Reminder text is passed as command arguments rather
  than interpolated into AppleScript source. Delivery failures do not affect
  authoritative timer state and are written to the platform-appropriate agent
  log. Surfacing those failures in the TUI belongs with the remaining reminder UI
  work.
- Reminder deadlines use a monotonic schedule. A persisted start, switch, or stop
  resets the relevant deadline; closing the TUI does not affect it. The default
  schedule is five minutes without a timer and 30 minutes with one.
- Build with PyInstaller on the target OS; it is not used for cross-compilation.
- Linux and Windows builds are one-file executables. macOS builds are ad-hoc-signed
  `.app` bundles, with the TUI executable inside the bundle.

## Testing and first validation

Use unit tests for domain behavior, integration tests for SQLite, IPC, recovery,
and migrations, and Textual tests for critical keyboard workflows. CI runs the
canonical checks on Linux, Windows, and macOS.

Before broad feature work, validate a minimal packaged application on all three
platforms:

1. Start the background process from the TUI and leave it running after the TUI
   closes.
2. Exchange authenticated JSON over `AF_UNIX` and `AF_PIPE`.
3. Deliver a native notification with no TUI open, including local signing on
   macOS.
4. Reconnect the TUI and stop the process cleanly.

If an IPC or notification choice fails, replace that adapter without changing the
domain or application boundary.

The automated packaged smoke runs two real Textual app sessions from the frozen
artifact using an isolated data directory: start a timer, close the first TUI,
confirm the agent remains available, reconnect and recover the original timer,
stop it, and shut down the agent. GitHub Actions builds and executes this lifecycle
on Linux, Windows, and macOS. Native delivery is checked separately on an
interactive desktop with `make smoke-notification`, since hosted CI runners do not
provide a reliable signed-in notification session.

As of July 19, 2026, the full packaged lifecycle and native Notification Center
dispatch have passed locally on macOS arm64. Linux and Windows packaged lifecycle
results are intentionally not marked complete until the updated matrix workflow
has run on those operating systems.

## References

- [Textual](https://textual.textualize.io/getting_started/)
- [Python IPC](https://docs.python.org/3/library/multiprocessing.html#listeners-and-clients)
- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html)
- [Python tomllib](https://docs.python.org/3/library/tomllib.html)
- [desktop-notifier](https://github.com/samschott/desktop-notifier)
- [platformdirs](https://platformdirs.readthedocs.io/en/latest/)
- [PyInstaller](https://pyinstaller.org/en/stable/)
- [uv projects](https://docs.astral.sh/uv/concepts/projects/)
