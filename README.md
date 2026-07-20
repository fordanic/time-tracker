# Time Tracker

A local-first time tracker for Linux, Windows, and macOS, with Linux as the
primary development environment. The product uses a keyboard-driven TUI backed by
a local background process.

## Top-level requirements

- Organize activities within projects.
- Track one activity at a time, with automatically derived start, stop, and
  duration.
- Preserve an active timer across restarts and crashes.
- Continue reminders after the TUI closes by using a background process.
- Store data locally in SQLite and settings in TOML.
- Export completed entries or daily project/activity summaries to UTF-8 CSV.

The product remains local, single-user, and TUI-only. See the top-level
requirements for authoritative product behavior and the competitive assessment
for candidate usability work. Selected additions are specified in the feature
requirements before implementation.

## Architecture

The Textual TUI is a client of a single Python background process. That process
owns timer state, reminders, and SQLite access. A versioned local protocol keeps
business logic independent of Textual presentation code.

## Documentation

- [Top-level requirements](docs/top-level-requirements.md) — authoritative product
  behavior and scope.
- [Architecture](docs/architecture.md) — technical choices and boundaries.
- [Feature requirements](docs/feature-requirements.md) — approved additional
  feature behavior subordinate to the top-level requirements and architecture.
- [Competitive assessment and TUI roadmap](docs/competitive-assessment.md) —
  desktop and terminal time-tracking UX patterns and the recommended TUI roadmap.
- [Agent guidance](AGENTS.md) — repository working rules.
- [Commit guidelines](docs/commits.md) — commit preparation and message format.

## Status

This section is the current source of truth for implementation and validation
status. The initial product baseline is implemented. The Textual TUI connects to
a single authenticated background process. It creates or reuses project and
activity names, starts, switches, and stops one SQLite-backed timer, and restores
an active timer after TUI closure, agent restart, or forced process termination.
The primary action explicitly says whether it will start, switch, or restart work;
an unchanged project/activity and normalized note shows Already tracking and is
disabled instead of fragmenting the active entry. Changing only the note restarts
the same pair with adjacent entries at one transactional timestamp.
The background process also owns monotonic reminder scheduling, TOML-configured
intervals, and native notification delivery after the TUI closes. The TUI lists
completed time chronologically in local-date groups with compact local start and
stop times, derived segment durations, notes, and a total after each day. Entries
crossing local midnight are divided into display segments while retaining one
editable entry identity and full offset-aware timestamps in the editor. Track
shows the current local day's completed total from the same projection and
excludes a running timer until it is stopped. Review filters completed time by
All time, Today, This week, This month, or an inclusive custom local date range,
plus optional case-insensitive project and activity names. Archived historical
targets remain filterable. Daily summaries and range totals by project/activity
use the same filter as day-grouped detail and CSV export; an overnight entry is
clipped to selected local dates, including across offset changes. All three CSV
representations require explicit overwrite confirmation. Projects and activities
can be archived
from the TUI after a second explicit confirmation naming the canonical target and
warning that a running timer continues. Archived names disappear from new-timer
suggestions, remain intact in history, are listed in Manage, and can be restored
there. Restoring a project preserves each activity's independent archive state,
and an activity can be restored only after its parent project.
The Track workflow shows up to five unique recently completed project/activity
pairs, newest first; selecting one prepares it for another timer without copying
its historical note. Archived targets are excluded from this recent-work list.
When connected, the TUI also presents due reminders; confirming an active reminder
restarts its interval without changing the timer, while ignoring it leaves the
timer running and reminders repeating. The TUI is split into keyboard-addressable
Track, Review, Manage, and Settings views. Its active-timer strip, reminder prompt,
and result message remain visible across views, while the existing action
shortcuts continue to work from any view.
In Review's completed-entry mode, a selected entry can be loaded and corrected
without changing its identity. Project, activity, note, start, and stop are
editable; offset-aware timestamps are persisted in UTC, and corrections that
overlap another completed or active entry are rejected while adjacent boundaries
remain valid.
The same Review editor can create one closed entry for missed time. It suggests
the previous local hour, reuses or creates a selectable project/activity pair,
and applies the correction workflow's duration, offset, overlap, and atomicity
rules without changing a running timer.
Track also provides an explicit active-detail update that changes the running
entry's project, activity, or note without changing its identity, original start,
elapsed time, or reminder deadline. Updated names are used by pending and future
active reminders.

The CI workflow is configured to build and exercise the packaged lifecycle on
Linux, Windows, and macOS. A local macOS arm64 app-bundle lifecycle and
Notification Center dispatch were validated on July 19, 2026.

Known outstanding validation:

- run the updated packaged-lifecycle workflow successfully on Linux and Windows;
- run the native-notification smoke on interactive Linux and Windows desktops;
  and
- record any additional unmet acceptance criteria here when identified.

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
the primary button or `F5` and the Stop button or `F6`. The primary action says
Start with no active timer, names both pairs before a switch, says Already
tracking and is disabled for an unchanged selection, or says Restart with new
note when only the normalized note differs. Existing project and activity names
are suggested as you type; press the right arrow to accept a completion. Closing
the TUI leaves the background process and any active timer running. Run
`uv run time-tracker --stop-agent` to stop only the process; the persisted timer
remains active and is recovered the next time the application starts.

While a timer is running, change its Track fields and use Update active details or
`F11` to persist those values without restarting it. Start/Switch/Restart via `F5`
remains the separate timer-transition choice. The update action is disabled when
the normalized fields already match the running entry. Track's completed-today
total does not include the running portion until Stop persists it.

Use `F1` through `F4` to switch between Track, Review, Manage, and Settings. The
same views can be selected from the tab row. Track owns timer capture and recent
activities; Review owns history, summaries, and CSV export; Manage owns archive
actions; and Settings explains how to find and apply the currently TOML-managed
reminder configuration. The active timer and any pending reminder stay visible
while moving between them. `F5` through `F11` retain their documented actions
from every view.

In Review (`F2`), completed time is grouped by local date with compact `HH:MM`
times and a total after each day. An entry crossing midnight has one display
segment in each affected day. Loading either segment for correction opens the
single full entry with offset-aware timestamps; total rows are not editable. Use
All time, Today, This week, This month, or Custom dates, then optionally enter a
project and activity. Target matching is case-insensitive and accepts archived
names that remain in history. Date boundaries are inclusive local dates. Use
Daily summaries for local-day totals or Range totals for one total per
project/activity pair; leave both off for completed-entry detail.

Enter a destination in the CSV export path field and press its button or `F7` to
export the visible representation and filter. A date-filtered detailed export
clips start and stop at the selected local-date boundaries; daily and range
summary exports contain the same selected durations. Relative paths are resolved
from the directory where the TUI was launched, and `~` expands to the current
user's home directory. If the destination exists, the TUI requires a second
export action before overwriting it. An empty selection exports the appropriate
header with no data rows.

To correct completed work, turn off Daily summaries and Range totals, select its
history row, and choose Load selected entry. Edit the project, activity, note,
start, or stop and save the correction. Start and stop use ISO 8601 values with
an explicit UTC offset, as prefilled by the application. The stop must be after
the start, and the corrected interval cannot overlap another completed or running
entry.

To record forgotten work, choose Add missed entry in the same completed-entry
mode. The editor starts with blank project, activity, and note fields and a
one-hour interval ending at the current local minute. Adjust the values and create
the entry; the same timestamp and no-overlap rules apply, and any active timer
continues unchanged.

When completed work exists, use the one-line Track again selector below the note
field to choose from up to five recent project/activity pairs. Use the arrow keys
to move through the list and Enter to select one. The note is cleared and focused
so a new note can be entered before starting with F5; the selection alone does not
change the running timer.

In Manage (`F3`), enter an existing project or project/activity pair and use its
archive button or `F8`/`F9`. The first action validates and names the exact target;
invoke it again without editing the inputs to confirm. Archiving leaves any
running timer active, removes the name from future timer suggestions, and
preserves completed history. Archived names cannot be reused. Select an item in
the archived project or activity lists and use its Restore button to make it
selectable again. Restore a parent project before restoring one of its archived
activities; restoring the project alone does not restore independently archived
activities. The archive buttons remain pointer-accessible but are omitted from
keyboard tab navigation; their function-key shortcuts remain available from
every view and use the Manage inputs.

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

The GitHub Actions workflow is configured to run the checks, native build, and
packaged lifecycle smoke on Python 3.14 across Linux, Windows, and macOS; see
[Status](#status) for current validation results. Native notification delivery
requires an interactive desktop session and is therefore a manual platform smoke.
