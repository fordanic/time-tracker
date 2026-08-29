# Architecture

This document is the technical source of truth for the application. Product
top-level behavior and scope belong in
[Top-Level Requirements](top-level-requirements.md). Additional approved feature
behavior is recorded in [Feature Requirements](feature-requirements/README.md) and must
conform to both authoritative documents.

## Overview

```text
+-------------+      local IPC      +--------------------+     +--------+
| Textual TUI | <-----------------> | Background process | --> | SQLite |
+-------------+                     +---------+----------+     +--------+
                                              ^    |
                                    local IPC |    +----------> OS notifier
                                              |
+------------+    loopback HTTP    +----------+--------+
| Browser UI | <-----------------> | Python web adapter |
+------------+                     +-------------------+
```

The TUI and optional local web server are alternative foreground clients. One
long-lived background process—called the agent in code and operational
documentation—owns timer state, reminders, and all database writes. Closing
either interface does not stop that process. This boundary keeps product behavior
independent of Textual and browser presentation code.

The web server is a Python interface adapter. It serves compiled browser assets
and translates same-origin JSON HTTP requests to the existing authenticated agent
protocol. The browser never connects to agent IPC or SQLite. Version 1 rejects
simultaneous TUI and web foreground clients because concurrent clients are not a
protocol guarantee.

## Technology choices

| Concern | Choice |
| --- | --- |
| Runtime | CPython 3.14 |
| Project management | `uv`, `pyproject.toml`, and a `src/` layout |
| TUI | Textual |
| Local web server | Starlette served by Uvicorn on `127.0.0.1` |
| Browser UI | TypeScript and Preact, built with Vite |
| Host browser launch | Python `webbrowser`; Windows `cmd.exe` URL association from WSL |
| Background work | `asyncio` |
| Local IPC | `multiprocessing.connection` |
| Persistence | Standard-library `sqlite3` and numbered SQL migrations |
| Configuration | TOML via `tomllib` |
| Platform paths | `platformdirs` |
| Notifications | Narrow native adapter: `desktop-notifier` on Linux/Windows, `osascript` on macOS, WinRT toasts on WSL |
| Local binaries | PyInstaller, run separately on each target OS |
| Release publication | GitHub Actions, Git tags, and GitHub CLI |
| Quality tools | pytest, pytest-asyncio, Ruff, and mypy |

An ORM, dependency-injection framework, remotely reachable network service, and
external migration framework are intentionally unnecessary for the current
product. Node.js is a development and build dependency only; native packages
contain compiled browser assets and no Node runtime.

## Process and IPC

- Starting either interface starts the background process if needed; an explicit
  lifecycle command stops it. Starting at login is deferred. The default command
  starts the TUI. `time-tracker --web` starts the loopback server on port `47831`
  and opens the default browser unless `--no-open` is present. `--port PORT`
  overrides that stable default and is valid only with `--web`.
- Prevent a second background process with an instance lock.
- Use `AF_UNIX` sockets on Linux and macOS and `AF_PIPE` named pipes on Windows.
- Authenticate connections with a per-user secret.
- Send versioned UTF-8 JSON using `send_bytes` and `recv_bytes`; never use the
  pickle-based `send` or `recv` methods.
- A request has a protocol version, request ID, method, and parameters. A response
  has the request ID and either a result or structured error.
- The current protocol supports one foreground agent-protocol client. Multiple
  concurrent protocol clients are not a guarantee. Version 1 reports a clear
  conflict rather than allowing simultaneous TUI and web clients. Browser tabs
  are HTTP consumers of one web process and are not independent protocol clients.
- Bump the protocol version when a genuinely new capability is added, such as
  completed-entry deletion (version 6); a minor addition to an existing settings
  area does not require a bump.

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
  web/                # Loopback ASGI adapter and compiled browser assets
  cli.py               # Interface launch and process lifecycle

web/                   # TypeScript/Preact source and build configuration

tests/
  unit/
  integration/
  e2e/
```

- Domain and application code must not depend on Textual, the web framework,
  SQLite, IPC, or a notification library.
- Interfaces call application use cases; they do not implement timer rules.
- Clocks, repositories, and notification services are injected for deterministic
  testing. No dependency-injection framework is used.
- The TUI uses the background process and protocol; it never accesses SQLite
  directly.
- The web adapter uses the same background process and protocol, serializes its
  blocking IPC calls away from the ASGI event loop, and never accesses SQLite
  directly. Browser code performs presentation and immediate field validation
  only.

## Local web boundary

- Bind only to IPv4 loopback. LAN binding is not configurable in version 1.
- Use a Starlette application served programmatically by Uvicorn. The stable
  default origin is `http://127.0.0.1:47831`; `--port` changes it explicitly. If
  the selected port is unavailable, fail clearly without opening a browser or
  selecting another port, so browser-local appearance remains origin-stable.
- Open the browser only after the server accepts connections. With `--no-open`,
  print the exact URL after readiness. Browser-open failure reports the URL and
  leaves the server running. `Ctrl+C` stops only the foreground web server and
  leaves the background agent and active timer running.
- On a WSL host with Windows interop, a narrow host-browser adapter invokes the
  Windows command processor without a Linux shell or interpolated command string
  and uses the registered URL association to open the loopback origin in the
  Windows default browser. The adapter resolves the Windows system executable
  without relying on inherited `PATH`, applies a timeout, and falls back to
  Python's platform browser launcher before reporting the URL. It does not
  broaden the `127.0.0.1` binding or change same-origin validation.
- Serve one same-origin Preact application and explicit JSON endpoints. Use
  modest polling for active state and reminders; derive the one-second elapsed
  display from the authoritative aware start timestamp between polls.
- One web process owns one IPC client and an async serialization lock. Multiple
  browser tabs may reach that server, but requests still pass through one
  foreground agent connection.
- Accept only `Host: 127.0.0.1:<selected-port>` and mutation Origin
  `http://127.0.0.1:<selected-port>`. Emit no permissive CORS response. Generate
  a fresh 256-bit URL-safe token at each web-server launch, embed it in the
  uncached same-origin HTML as `<meta name="time-tracker-token">`, and require
  its exact value in `X-Time-Tracker-Token` for every mutation. Accept mutation
  bodies only as JSON up to 64 KiB and expose no state-changing `GET` route.
- Send a restrictive Content Security Policy, deny framing, use same-origin
  resource isolation, and disable MIME sniffing. Do not load runtime assets from
  third-party origins.
- Do not place the launch token, tracked names, notes, or entry data in URLs or
  access logs.
- Browser appearance is local to browser storage with System, Light, and Dark
  values. The stable default origin preserves it across launches. It does not
  reuse or overwrite the Textual theme setting; an explicit port has its own
  browser-local preference.

## Persistence and time

The minimal SQLite model is:

```text
Project(id, name, archived_at?, created_at)
Activity(id, project_id, name, archived_at?, created_at)
TimeEntry(id, activity_id, started_at_utc, stopped_at_utc?, note?, created_at)
```

- Enable foreign keys for every connection.
- Track applied numbered SQL migrations in `schema_migrations`.
- Use transactions for timer transitions. Switching to another pair or restarting
  the active pair with a different normalized note stops the current entry and
  starts the next with one captured timestamp. An unchanged pair and normalized
  note is rejected in the application layer before the repository or clock is
  invoked.
- Edit active-entry details through an agent-owned application use case and one
  SQLite transaction. The transaction preserves the active row's identity and
  timestamps, retains an unchanged archived assignment when only its note changes,
  or resolves/creates a selectable changed target before updating activity and
  note. The agent updates active-reminder metadata after commit without signaling
  a timer transition or resetting the monotonic deadline.
- Correct a completed entry through an agent-owned application use case and one
  SQLite transaction. That transaction resolves or creates a selectable target,
  rejects archived reassignment, checks the corrected half-open interval against
  every other completed or active entry, and updates the existing row only after
  all checks pass. Adjacent interval boundaries are valid; no schema or revision
  history is added for the first correction slice.
- Delete a completed entry through an agent-owned application use case and one
  SQLite transaction, exposed over protocol version 6. The repository verifies
  that the identifier names a completed entry before deleting only that entry;
  the active timer and project/activity records are unchanged.
- Create a manual completed entry through an agent-owned application use case and
  one SQLite transaction. The application validates normalized values and captures
  the creation time from its injected clock; the transaction resolves or creates
  a selectable target, applies the same half-open overlap check as correction, and
  inserts the closed entry only after every check passes. The active timer is
  read for overlap validation but is never mutated.
- Resolve archive confirmation targets and archive or restore projects and
  activities through agent-owned application use cases exposed over the versioned
  protocol. Selection queries exclude archived rows, while archived-list queries
  retain canonical hierarchy context and archived names remain reserved. Each
  transition updates only the target archive flag in one SQLite transaction and
  does not mutate the active timer or historical entries. Project transitions do
  not rewrite child activity flags, and activity restore rejects an archived
  parent project.
- Create a project or an activity through an agent-owned application use case
  and one SQLite transaction, exposed over the versioned protocol like archive
  and restore. Each is a distinct, explicit action that rejects an existing
  name (active or archived) rather than reusing it, and activity creation
  rejects a missing or archived parent project rather than creating one. This
  is separate from the existing implicit get-or-create performed by timer
  start, manual entry, correction, and active-detail editing, which is
  unchanged.
- Enforce at most one entry with no stop time using a partial unique index.
- Store UTC instants as integer microseconds since the Unix epoch. Convert them to
  local, offset-aware ISO 8601 values at presentation and export boundaries.
- The TUI renders editable entry boundaries as timezone-free local wall-clock
  values. It resolves a changed value through the host's local-time rules before
  sending an offset-aware instant to the agent, rejects ambiguous or nonexistent
  wall times, and preserves the stored instant when its displayed value is left
  unchanged. The agent and application layers continue to receive aware instants.
- Derive duration from timestamps; do not store an independently mutable duration.
- Use a monotonic clock for in-process scheduling and persisted UTC instants for
  recovery.
- CSV export is an agent application use case: it reads completed entries through
  the repository port and writes filtered entries, local-day project/activity
  summaries, or selected-range project/activity totals through CSV output ports.
  One typed application filter model owns inclusive local-date, project, and
  activity matching. Shared application projections split and clip entries at
  local calendar boundaries and are used by both the TUI and export service. The
  TUI resolves preset controls into that model, renders the returned projection,
  and sends the same validated filter, selected representation, destination, and
  explicit overwrite-confirmation flag over IPC. The agent reconstructs and
  validates the filter before export; active entries are excluded by the
  completed-entry query. No schema migration is required.

SQLite and the background process remain authoritative even when notification
delivery fails or the TUI disconnects.

## Configuration, notifications, and packaging

- Read user-edited TOML with `tomllib`; defaults and validation live in typed
  application configuration. The background process exposes current supported
  settings and saves changes through an application/configuration port. Its TOML
  adapter atomically replaces a complete validated file; invalid input or a write
  failure leaves the prior file and live schedule unchanged.
- The optional TOML file has one `[reminders]` table with independent
  `inactive_enabled`/`active_enabled` booleans and positive
  `inactive_interval_minutes`/`active_interval_minutes` numbers, an optional
  weekly local-time delivery window, a positive snooze duration, and independent
  opt-in idle-reminder state with a positive threshold in minutes. Configuration
  is loaded when the background process starts. A successful agent-owned
  foreground save reloads it immediately, clears a prompt created by the replaced
  schedule, and resets the current timer state's monotonic deadline from the save
  time.
- The same strict TOML file may contain `[ui]` and `[export]` tables. The UI table
  stores the selected Textual theme name, and the export table stores one
  validated delimiter (`comma` or `pipe`). Comma remains the default. Saving one
  settings area atomically preserves the other tables. The TUI applies an
  available saved theme on launch and durably replaces it when the user selects
  another theme; an unavailable saved theme falls back to the built-in default.
- Export writers receive the currently configured delimiter through the
  application boundary for each request. Python's CSV writer remains responsible
  for quoting delimiters, quotes, and line breaks, so changing the delimiter does
  not introduce presentation or escaping rules into the agent or TUI.
- Use `platformdirs` for per-user configuration, data, state, runtime, and log
  locations.
- Use simple native notifications. Native notification action buttons are
  deferred; the agent retains the latest due reminder in memory for a connected
  foreground interface to poll over IPC. Confirming an active reminder clears
  that prompt and restarts the active monotonic interval without mutating the
  persisted timer.
  Ignoring it leaves both the timer and repeating schedule unchanged.
- `desktop-notifier` uses desktop services on Linux and WinRT on Windows. macOS
  uses its built-in `osascript` notification command: on the current macOS 26
  validation host, `UNUserNotificationCenter` rejected an otherwise valid
  ad-hoc-signed local bundle. Reminder text is passed as command arguments rather
  than interpolated into AppleScript source. Delivery failures do not affect
  authoritative timer state and are written to the platform-appropriate agent
  log. Surfacing native delivery failures in the TUI is not currently required.
- A WSL host reports Linux, so `desktop-notifier` selects its D-Bus backend, but a
  WSL distribution provides no notification daemon and delivery always fails.
  Detect WSL from the kernel release and registered Windows interop, then deliver
  a Windows toast through the Windows PowerShell 5.1 WinRT notification API. The
  agent registers one stable current-user application identity with a display
  name so toasts are attributed to Time Tracker and manageable in the Windows
  notification settings; Windows consumes the first toast from an unseen identity,
  so first-time registration is followed by one warm-up notification. Reminder
  text crosses into Windows through the shared process environment rather than
  script source or a command line, invocations are timeout-bounded so the agent
  loop cannot stall, and an unavailable interpreter falls back to desktop-service
  delivery for a user running their own daemon inside WSL. WSLg provides no X11
  screen-saver extension, so idle detection reports itself unavailable there.
- Reminder deadlines use a monotonic schedule. A persisted start, switch, or stop
  resets the relevant deadline, as does explicit confirmation of an active
  reminder; closing a foreground interface does not affect it. The default
  schedule is five minutes without a timer and 30 minutes with one.
- Optional idle-triggered active reminders use an agent-owned poller and a narrow,
  injected operating-system adapter that reports only elapsed local input-idle
  duration. The adapter never exposes input content. Detector state is advisory
  and in memory, may request the existing active-reminder channel early, and
  cannot mutate persisted timer state. Adapter failure leaves normal reminder
  scheduling and authoritative timer state unchanged. Polling occurs at most every
  15 seconds only while the feature and a timer are active. macOS uses Core
  Graphics combined-session idle duration, Windows uses `GetLastInputInfo`, and
  supported interactive Linux X11 sessions use the XScreenSaver extension;
  unsupported sessions expose the feature as unavailable.
- An application reminder-window policy uses the agent's local aware wall clock
  only to decide whether a due monotonic deadline may be presented and to find the
  next weekly opening. It supports same-day and overnight windows and suppresses
  catch-up bursts. Snooze is agent-owned in-memory state that replaces the current
  deadline without changing timer or configuration; timer transitions, active
  confirmation, settings reload, and process restart reset the normal interval,
  while active-detail edits preserve the deadline.
- Build with PyInstaller on the target OS; it is not used for cross-compilation.
- Build browser assets deterministically before packaging and include the
  production HTML, CSS, and JavaScript under `time_tracker.web`. The frozen
  runtime does not contain Node.js or `node_modules`.
- Linux and Windows builds are one-file executables. macOS builds are ad-hoc-signed
  `.app` bundles, with the TUI executable inside the bundle.
- Windows file-version resources and macOS bundle-version metadata are generated
  from the canonical application version. Updating a macOS bundle property is
  followed by another ad-hoc signature so release packaging does not invalidate
  the bundle.
- `src/time_tracker/__init__.py` is the single application-version source.
  Hatch reads the same value for project metadata, and the CLI and frozen
  executable import it at runtime. Final versions use `X.Y.Z`; release candidates
  use the PEP 440 form `X.Y.ZrcN`. The corresponding Git tag is `v<version>`.
- A manually dispatched release workflow validates its expected version and
  candidate-or-final kind against the canonical version in the selected commit.
  It then runs the complete repository checks on Linux, Windows, and macOS,
  builds each native package on its target operating system, exercises the
  packaged lifecycle, verifies the frozen executable's version, and creates a
  versioned operating-system/architecture archive plus a SHA-256 checksum.
- Build jobs have read-only repository access. They transfer archives and
  checksums to one publication job through GitHub Actions artifacts. The
  publication job alone receives `contents: write`.
- After all platform jobs succeed, the publication job verifies every checksum,
  creates or verifies one annotated version tag at the workflow commit, and uses
  GitHub CLI with the workflow token to create a non-draft prerelease for an
  `rc` version or a final release for a final version.
- Release workflow runs are serialized per version. Re-running the same version
  at the same commit reuses the tag and release, does not overwrite existing
  asset names, and uploads only missing assets. A tag at another commit, a
  lightweight tag, or a release with the wrong prerelease state stops
  publication.

## Testing and platform validation

Use unit tests for domain behavior, integration tests for SQLite, IPC, HTTP,
recovery, and migrations, Textual tests for critical terminal workflows, and
browser tests for critical web workflows at desktop and mobile widths. CI runs
the canonical Python and frontend checks on Linux, Windows, and macOS.

Maintain validation of the minimal packaged application on all three platforms:

1. Start the background process from either interface and leave it running after
   the foreground interface closes.
2. Exchange authenticated JSON over `AF_UNIX` and `AF_PIPE`.
3. Deliver a native notification with no foreground interface open, including
   local signing on macOS and delivery to the Windows desktop from WSL.
4. Reconnect an interface and stop the process cleanly.

If an IPC or notification choice fails, replace that adapter without changing the
domain or application boundary.

The automated packaged smoke runs two real Textual app sessions from the frozen
artifact using an isolated data directory: start a timer, close the first TUI,
confirm the agent remains available, reconnect and recover the original timer,
stop it, and shut down the agent. The GitHub Actions workflow is configured to
build and execute this lifecycle on Linux, Windows, and macOS. Native delivery is
checked separately on an interactive desktop with `make smoke-notification`,
since hosted CI runners do not provide a reliable signed-in notification session.
The same smoke covers WSL, where delivery must reach the Windows desktop.
The release workflow repeats the canonical checks and packaged lifecycle on each
target operating system before the publication job can create a tag or upload an
asset.

The packaged web smoke starts the loopback server from the frozen artifact,
loads the compiled shell, starts a timer through HTTP, closes the web server while
leaving the agent and active entry running, relaunches the server, recovers and
stops the timer, and shuts down the agent. Broader source-browser tests cover
switch, restart, active editing, reminders, Review, Manage, and Settings. Chromium
is the release-gating automated browser engine; interactive Safari and Firefox
results are recorded as validation rather than blocking native publication. WSL
uses the Linux artifact and remains an interactive validation target, not a
fourth native package.

Canonical frontend checks are `npm run format:check`, `npm run lint`,
`npm run typecheck`, `npm run test`, `npm run test:e2e`, and `npm run build`.
Security integration tests reject unexpected Host and Origin values, invalid
mutation tokens, non-JSON and oversized bodies, framing, and non-loopback
binding. Accessibility checks use WCAG AA contrast thresholds: 4.5:1 for normal
text and 3:1 for large text and essential user-interface boundaries.

Current platform results and outstanding validation are recorded only in the
[README Status](../README.md#status) section.

## References

- [Textual](https://textual.textualize.io/getting_started/)
- [Starlette](https://www.starlette.io/)
- [Uvicorn](https://www.uvicorn.org/)
- [Preact](https://preactjs.com/)
- [Vite](https://vite.dev/)
- [Python IPC](https://docs.python.org/3/library/multiprocessing.html#listeners-and-clients)
- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html)
- [Python tomllib](https://docs.python.org/3/library/tomllib.html)
- [desktop-notifier](https://github.com/samschott/desktop-notifier)
- [Windows toast notifications and application identity](https://learn.microsoft.com/en-us/windows/apps/design/shell/tiles-and-notifications/send-local-toast-other)
- [platformdirs](https://platformdirs.readthedocs.io/en/latest/)
- [PyInstaller](https://pyinstaller.org/en/stable/)
- [uv projects](https://docs.astral.sh/uv/concepts/projects/)
