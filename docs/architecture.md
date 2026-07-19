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
| Notifications | `desktop-notifier` behind an internal interface |
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

Blocking IPC and SQLite work must not stall reminder scheduling.

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
- Enforce at most one entry with no stop time using a partial unique index.
- Store UTC instants as integer microseconds since the Unix epoch. Convert them to
  local, offset-aware ISO 8601 values at presentation and export boundaries.
- Derive duration from timestamps; do not store an independently mutable duration.
- Use a monotonic clock for in-process scheduling and persisted UTC instants for
  recovery.

SQLite and the background process remain authoritative even when notification
delivery fails or the TUI disconnects.

## Configuration, notifications, and packaging

- Read user-edited TOML with `tomllib`; defaults live in typed application
  configuration. Invalid input is reported without rewriting the file.
- Use `platformdirs` for per-user configuration, data, state, runtime, and log
  locations.
- Use simple native notifications. Interactive notification actions are deferred;
  users act through the TUI.
- `desktop-notifier` uses desktop services on Linux, Notification Center on macOS,
  and WinRT on Windows. Delivery failures are logged and shown in a connected TUI.
- Build with PyInstaller on the target OS; it is not used for cross-compilation.
- macOS notification delivery requires a signed executable or app bundle, so local
  builds may require an ad-hoc signing step.

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

## References

- [Textual](https://textual.textualize.io/getting_started/)
- [Python IPC](https://docs.python.org/3/library/multiprocessing.html#listeners-and-clients)
- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html)
- [Python tomllib](https://docs.python.org/3/library/tomllib.html)
- [desktop-notifier](https://github.com/samschott/desktop-notifier)
- [platformdirs](https://platformdirs.readthedocs.io/en/latest/)
- [PyInstaller](https://pyinstaller.org/en/stable/)
- [uv projects](https://docs.astral.sh/uv/concepts/projects/)
