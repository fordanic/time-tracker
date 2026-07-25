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
- Export completed entries or project/activity summaries as UTF-8 delimited
  text, using comma by default or pipe when selected.

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
- [Release guide](docs/releases.md) — versioning, local release builds, and
  GitHub publication without hosted Actions.

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
plus project and activity selections populated from history. Archived historical
targets remain selectable. Daily summaries and range totals by project/activity
use the same filter as day-grouped detail and CSV export; an overnight entry is
clipped to selected local dates, including across offset changes. All three
export representations require explicit overwrite confirmation and use the
configured comma or pipe delimiter with standard quoting. Projects and
activities are shown in active and archived Manage trees. A selected exact node
can be archived after a second explicit confirmation naming the canonical target
and warning that a running timer continues, or restored from the archived tree.
Archived names disappear from new-timer suggestions and remain intact in
history. Restoring a project preserves each activity's independent archive
state, and an activity can be restored only after its parent project.
The Track workflow shows up to five unique recently completed project/activity
pairs, newest first; selecting one prepares it for another timer without copying
its historical note. Archived targets are excluded from this recent-work list.
When connected, the TUI also presents due reminders; confirming an active reminder
restarts its interval without changing the timer, while ignoring it leaves the
timer running and reminders repeating. Track places project and activity
together when space permits and uses a two-line multiline note editor. The TUI
is split into keyboard-addressable Track, Review, Manage, and Settings views. Its
active-timer strip, reminder prompt, and result message remain visible across
views, while the existing action shortcuts continue to work from any view. Its
compact, context-aware shortcut row keeps shortcut help discoverable in narrow
terminals, while the overlay lists every retained F-key action.
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
Settings exposes reminder controls and the comma-or-pipe export choice. Saving
atomically replaces the human-readable TOML configuration, applies changes
without restarting the background process, clears any prompt from a replaced
schedule, and preserves disabled interval values for later re-enabling. Theme
choices made through Textual's theme picker also persist across TUI launches,
with a safe built-in fallback if a saved theme disappears.
An optional shared weekly local-time window suppresses both reminder kinds until
the next selected opening. Any pending reminder can be snoozed for the configured
duration with its button or `F12` without changing timer state; snooze is
in-memory and timer transitions, confirmation, settings reload, or agent restart
restore the normal interval.
Optional local input-idle detection can request the existing active reminder
early after 15 minutes by default, including when periodic active reminders are
disabled. It observes only an operating-system idle duration, never input
content, and never changes tracked time automatically. The prompt can be
confirmed, snoozed, or followed by an explicit Stop; unwanted idle time remains
correctable in Review.

The CI workflow builds and exercises the packaged lifecycle on Linux, Windows,
and macOS; all three jobs passed on July 25, 2026. A local macOS arm64 app-bundle
lifecycle and Notification Center dispatch were validated on July 19, 2026. The
macOS Core Graphics idle-duration adapter was validated interactively on July
22, 2026. A versioned, ad-hoc-signed macOS arm64 release archive, checksum, and
packaged lifecycle were validated locally on July 24, 2026.

Known outstanding validation:

- run the native-notification smoke on interactive Linux and Windows desktops;
- validate idle-duration detection on supported interactive Linux X11 and
  Windows desktop sessions;
- validate versioned release archives and native version metadata on Linux and
  Windows; and
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
make test-unit
make test-integration
make test-e2e
make test
make check
make build
```

Make stores uv's disposable package cache and managed Python installations in the
ignored repository-local `.uv-cache/` and `.uv-python/` directories so commands
do not depend on write access to global user locations. PyInstaller similarly
uses `.pyinstaller-cache/`. Make also removes an unusable generated `.venv`
before syncing. Set `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, or
`PYINSTALLER_CONFIG_DIR` explicitly to override those locations.

`make build` creates a native package for the current operating system in
`dist/`. Linux and Windows use one-file executables. macOS uses an ad-hoc-signed
`.app` bundle and its built-in notification command. Use
`make clean` to remove repository-local build and check artifacts.
To permanently remove the current user's Time Tracker database, configuration,
IPC secret, and runtime files, first stop any work you want to preserve and run
`make clear-local CONFIRM=1`.

Run `make test-unit`, `make test-integration`, or `make test-e2e` while
iterating on one tier; `make test` runs all three. Run the same complete checks
used in CI with `make check`, or directly:

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
actions; and Settings edits TOML-backed reminder and export preferences and
applies them live. The active timer and any pending reminder stay visible while
moving between them. `F5` through `F11` retain their documented actions from
every view, and `F12` snoozes any pending reminder. `Ctrl+K` opens the complete
shortcut overlay, and `Ctrl+C` exits the application.

In Review (`F2`), completed time is grouped by local date with compact `HH:MM`
times and a total after each day. An entry crossing midnight has one display
segment in each affected day. Loading either segment for correction opens the
single full entry with offset-aware timestamps; total rows are not editable. Use
All time, Today, This week, This month, or Custom dates, then optionally select a
project and activity from the history-backed controls. Archived names that
remain in history are included. Date boundaries are inclusive local dates. Use
Daily summaries for local-day totals or Range totals for one total per
project/activity pair; leave both off for completed-entry detail.

Enter a destination in the CSV export path field and press its button or `F7` to
export the visible representation and filter. A date-filtered detailed export
clips start and stop at the selected local-date boundaries; daily and range
summary exports contain the same selected durations. Relative paths are resolved
from the directory where the TUI was launched, and `~` expands to the current
user's home directory. If the destination exists, the TUI requires a second
export action before overwriting it. An empty selection exports the appropriate
header with no data rows. Settings chooses comma (the default) or pipe as the
delimiter; both formats use standard quoting for delimiters, quotes, Unicode,
and multiline notes.

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

Project and activity share a Track row at normal widths and stack in narrow
terminals. The note editor displays two lines and preserves line breaks. When
completed work exists, use the Track again selector below the note to choose from
up to five recent project/activity pairs. Use the arrow keys to move through the
list and Enter to select one. This explicit selection clears and focuses the
note; typing or correcting a target does not clear it, and selection alone does
not change the running timer.

In Manage (`F3`), select a project or activity in the active tree and use Archive
selected or `F8`/`F9`. The first action validates and names the exact target;
invoke it again without changing selection to confirm. Archiving leaves any
running timer active, removes the name from future timer suggestions, and
preserves completed history. Archived names cannot be reused. Select an item in
the archived tree and use Restore selected to make it selectable again. Restore
a parent project before restoring one of its archived activities; restoring the
project alone does not restore independently archived activities.

When a reminder becomes due while the TUI is connected, it appears below the
active timer. For an active timer, press its button or `F10` to confirm that it is
still active and restart the configured interval. Press Snooze or `F12` on either
reminder kind to defer it by the configured duration. Taking no action leaves the
timer running; use Stop or `F6` when the timer should end.

## Configuration

Use Settings (`F4`) to enable or disable each reminder independently, edit its
positive interval in minutes, optionally restrict delivery to selected local
weekdays and `HH:MM` hours, choose a positive snooze duration, and optionally
enable an idle-triggered active reminder with a positive threshold. Settings also
chooses comma or pipe for exports. It reports whether idle detection is available
in the current platform session. An end earlier than the start makes an overnight
window. Saving creates or atomically replaces the optional TOML file and applies
changes immediately; no background-process restart is needed. Theme selections
made through Textual's theme picker are saved to the same file. Run
`uv run time-tracker --config-path` to locate it. When it does not exist,
built-in reminder values, the Textual dark theme, and comma-delimited exports are
used. The complete supported configuration is:

```toml
[reminders]
inactive_enabled = true
inactive_interval_minutes = 5
active_enabled = true
active_interval_minutes = 30
window_enabled = false
window_weekdays = [0, 1, 2, 3, 4]
window_start = "09:00"
window_end = "17:00"
snooze_minutes = 10
idle_enabled = false
idle_threshold_minutes = 15

[ui]
theme = "textual-dark"

[export]
delimiter = ","
```

Each reminder can be disabled independently. Intervals must be positive numbers.
Weekdays use Monday `0` through Sunday `6`; values must be unique, and start and
end must differ. Snoozing clears the current prompt and defers the next reminder
without modifying the timer or recurring interval.
Idle detection polls only while enabled and a timer is active. It requests the
same active reminder early, honors the weekly delivery window, and remains
available when the periodic active reminder is disabled. A detector failure
leaves timer and normal reminder state unchanged and is shown as unavailable in
Settings.
The export delimiter must be `","` or `"|"`. An unavailable saved theme falls
back to `textual-dark` without preventing launch.
Direct edits made outside the TUI still require restarting the background process
with `uv run time-tracker --stop-agent`, then reopening the TUI. Invalid TOML,
unknown keys, and invalid values are reported without changing the file.

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

## Releases

Release candidates and final releases are built and published from development
machines. Publication uses local Git and authenticated GitHub CLI operations; it
does not depend on GitHub Actions or consume hosted Actions minutes.

Versions use `X.Y.Z` for final releases and `X.Y.ZrcN` for release candidates.
`src/time_tracker/__init__.py` is the canonical version source, and `v<version>`
is the corresponding annotated Git tag. Each target operating system must build
its own artifact because PyInstaller does not cross-compile.

1. Install `uv`, GNU Make, Git, and GitHub CLI. Authenticate the publishing
   account:

   ```shell
   gh auth login
   gh auth status
   ```

2. From a branch based on current `main`, set the next version:

   ```shell
   make set-version VERSION=0.2.0rc1
   ```

   Review the canonical source and `uv.lock` changes, commit them, and merge them
   through the normal review process. Increment `rcN` for another candidate.
   Never move or reuse an existing version tag.

3. On a target-platform machine, check out the clean version commit and build the
   release artifact:

   ```shell
   make release-artifact
   ```

   This synchronizes the locked environment, runs formatting, lint, type, unit,
   integration, and end-to-end checks, builds and smoke-tests the native package,
   verifies its reported version, and writes a versioned archive and SHA-256 file
   under `dist/release/`.

4. On the first target platform, publish the version with the command matching
   its kind:

   ```shell
   make publish-release-candidate  # X.Y.ZrcN
   make publish-release            # X.Y.Z
   ```

   Publication repeats the complete validation, creates and pushes the annotated
   tag when needed, and creates a visible GitHub prerelease or final release with
   generated notes and the local platform's archive and checksum.

5. On every other target operating system, check out the exact same tag and run
   the same publication command:

   ```shell
   git fetch --tags origin
   git checkout v0.2.0rc1
   make publish-release-candidate
   ```

   The command verifies the existing tag and GitHub release, then uploads that
   platform's differently named archive and checksum without overwriting an
   existing asset.

6. After candidate approval, create and merge a new version commit without the
   `rcN` suffix, then repeat the target-platform process with
   `make publish-release`. Final artifacts are rebuilt; candidate binaries are
   not relabeled.

Publication requires a clean checkout and stops when the version kind, tag,
frozen version, archive, checksum, authentication, or existing release state is
inconsistent. An interrupted publication can be rerun from the same tagged
commit. See the [release guide](docs/releases.md) for artifact formats and full
safeguards.
