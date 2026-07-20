# Competitive assessment and TUI roadmap

_Assessment date: July 20, 2026_

## Purpose and phase

This document compares Time Tracker's TUI with Toggl Track, Clockify, Harvest,
and Timewarrior, then turns the comparison into a next-phase implementation
roadmap. Toggl Track, Clockify, and Harvest represent established desktop timer
products; Timewarrior represents the terminal-native workflow closest to Time
Tracker's local, keyboard-first positioning.

The initial feature baseline described in the authoritative
[README Status](../README.md#status) is implemented. The product can now move from
proving its architecture and core timer behavior to making everyday use faster,
more forgiving, and easier to review. Outstanding validation recorded there may
run in parallel with planning but must be complete before the first roadmap
feature is considered done.

This is a qualitative product and heuristic UX review, not a market-share ranking
or a timed usability test. Competitor behavior was checked against first-party
product and help material. Because products change, the source links and
assessment date are part of the record.

## Continuing scope

The next phase remains a local, single-user, keyboard-first TUI. The assessment
continues to exclude:

- web- and mobile-specific interface patterns;
- graphical desktop surfaces such as tray/menu-bar controls and mini windows;
- billing, invoicing, rates, costs, profitability, expenses, and approvals;
- plugins, third-party integrations, imports, and public automation APIs; and
- accounts, collaboration, cloud synchronization, and telemetry.

Features that were deferred from the initial baseline can now be
considered when they fit the TUI and local-first architecture. These include
correction of completed entries, manual recording of missed time, richer local
review, reversible archive management, reminder controls, and TUI-managed
settings.

The roadmap is a product recommendation, not a requirements source. Before
implementing a selected slice, define its behavior in
[Feature Requirements](feature-requirements.md). Those requirements must conform
to the authoritative [Top-Level Requirements](top-level-requirements.md) and
[Architecture](architecture.md). Preserve the architectural rules that the
background process is the single database writer, transitions are persisted
before success is reported, and business rules remain outside the TUI.

## Executive conclusion

Time Tracker is already stronger than the cloud-first products on local authority,
offline reliability, and a small product model. Its persisted active-timer
recovery is also a proven baseline. Its largest next-phase gaps are no longer
infrastructure gaps. They are daily-use gaps:

1. Repeated work is slower to resume than in every compared product.
2. A tracking mistake or missed timer cannot be corrected inside the product.
3. Start, switch, and restart intent is not sufficiently explicit.
4. Capture, review, export, and archive management compete on one dense screen.
5. History lacks the day context, filtering, and summaries expected once real data
   accumulates.
6. Reminder configuration requires editing TOML and restarting the background
   process.

The recommended next product milestone is **Daily-use usability and correction**.
It should deliver a recent-work flow, unambiguous timer actions, correction and
manual-entry workflows, safer archive handling, and the prerequisite Track,
Review, Manage, and Settings view scaffold. The following milestone fills those
views with broader review and reporting.

## Completed baseline

The current implementation provides:

- an explicit project → activity model with an optional note;
- one timer at a time, with atomic switching and no overlap during a switch;
- prominent active project, activity, local start time, note, and live elapsed
  duration while the TUI is open;
- durable SQLite storage and restoration after TUI closure, agent restart, or
  process failure;
- keyboard and pointer actions for start/switch, stop, export, archive, and active
  reminder confirmation;
- case-insensitive project and activity completion as the user types;
- chronological completed-entry history and local daily project/activity totals;
- CSV export of either representation, with explicit overwrite confirmation;
- project and activity archiving without loss of history; and
- configurable native reminders owned by the background process, including while
  the TUI is closed.

These behaviors are summarized in the [README](../README.md), implemented across
the application, agent, infrastructure, and TUI boundaries described in the
[architecture](architecture.md), and presented by the
[Textual application](../src/time_tracker/tui/app.py). They establish a sound base
for planned work.

## Competitor assessments

### Toggl Track

Toggl's desktop apps combine a running timer with recent entries. A previous entry
can be continued from its row, the last entry can be continued with a keyboard
shortcut, and similar entries may be grouped. The apps also support a default
project, obvious running state, offline capture, configurable shortcuts, reminder
windows, and snoozing. Existing entries can be edited, and manual entries can be
created. See the current
[macOS desktop guide](https://support.toggl.com/en-us/article/toggl-track-desktop-app-for-macos-1669b8x/)
and [Windows desktop guide](https://support.toggl.com/en-us/article/toggl-track-desktop-app-for-windows-5w1y5/).

**UX strengths**

- Repeating work is fast: continue the last entry or restart from a recent row.
- Users can start first and supply or correct details later, making capture
  forgiving.
- The interface distinguishes current timer state from recent history.
- Grouping reduces noise when the same work is started and stopped repeatedly.
- Reminder windows and snooze controls reduce notification fatigue.

**UX costs and limits**

- Many modes and preferences add conceptual weight to a simple timer.
- Several visibility mechanisms depend on graphical desktop chrome.
- Account and synchronization behavior are irrelevant to this local-first app.

**Relevant lesson:** make recurring work and correction first-class, but implement
them through the existing local application and protocol boundaries rather than
copying Toggl's graphical or cloud machinery.

### Clockify

Clockify's desktop app centers on a running stopwatch, supports cached offline
tracking, a default or last-used project, configurable start/stop shortcuts, and
reminder schedules. Its entry list supports editing and manual capture. Reports
provide date presets plus project, task, description, and other filters. See
Clockify's [desktop overview](https://clockify.me/desktop-time-tracking),
[Mac app guide](https://clockify.me/help/apps/mac-desktop-app), and
[report filtering guide](https://clockify.me/help/reports/filtering-reports).

**UX strengths**

- Defaults and recent data minimize repeated selection.
- Entry correction and manual capture address forgotten or inaccurate timers.
- Preset date ranges and composable filters make large histories manageable.
- Reminder schedules expose common settings without requiring file editing.

**UX costs and limits**

- Review and reporting are separated from the desktop capture surface.
- Cached offline behavior remains subordinate to a cloud account and sync state.
- The broad product model exposes fields and team concepts that do not benefit a
  local single-user tracker.

**Relevant lesson:** separate capture from review and settings, while keeping all
three within the TUI and sharing application-layer projections.

### Harvest

Harvest's desktop timesheet is organized by day. Project/task fields autocomplete,
project/task pairs can be saved as favorites and started directly, and keyboard
shortcuts can move between days and entries or start and stop a selected entry.
Users can edit an existing entry or add a duration/start-and-stop entry for missed
work. Harvest's Windows desktop app requires an internet connection. See the
[desktop tracking guide](https://support.getharvest.com/hc/en-us/articles/360048180372-Windows-app-Tracking-time),
[favorites guide](https://support.getharvest.com/hc/en-us/articles/360048685451-Windows-App-Using-Favorites),
[keyboard shortcut guide](https://support.getharvest.com/hc/en-us/articles/360048685411-Windows-app-Keyboard-shortcuts),
and [desktop overview](https://support.getharvest.com/hc/en-us/articles/4407342303757-Windows-app-Overview).

**UX strengths**

- The daily timesheet answers “what did I track today?” before presenting a long
  history.
- Favorites make a structured project/task model fast for repetitive work.
- Correction and missed-time entry are integrated into the same day-oriented
  review workflow.
- Keyboard navigation applies to capture and review, not only start/stop.

**UX costs and limits**

- Choosing a project/task pair in a separate entry flow is slower for uncommon
  work than a compact inline timer.
- Favorites add a list that the user must curate.
- Requiring a connection is a significant weakness relative to Time Tracker.

**Relevant lesson:** make Review the place where a user understands and corrects
one day, and derive recent work automatically before requiring curated favorites.

### Timewarrior

Timewarrior is a local command-line time tracker. Its core workflow is deliberately
small: `timew start`, `timew stop`, and `timew continue`; starting while another
interval is open closes the previous interval. It supports recording closed
intervals, annotating and retagging entries, and correcting timestamps through
move, lengthen, shorten, resize, split, and join commands. `summary` defaults to
the current day, with concise date hints for other ranges. See the official
[overview](https://timewarrior.net/docs/what/),
[command reference](https://timewarrior.net/docs/),
[continue reference](https://timewarrior.net/reference/timew-continue.1/), and
[summary tutorial](https://timewarrior.net/tutorial/summary/).

**UX strengths**

- The verb-first command model is fast and memorable for terminal users.
- `continue` makes the most common repeated action explicit.
- Correction is powerful without requiring a graphical timeline.
- The default summary is scoped to today and includes a daily total.
- Date hints provide compact expert filters.

**UX costs and limits**

- Users must remember syntax, quoting, hints, and identifiers.
- The correction command set is powerful but fragmented across many verbs.
- Free-form tags do not communicate Time Tracker's project/activity relationship.
- Running state is queried rather than persistently visible.

**Relevant lesson:** a TUI can provide strong correction and review without
becoming a GUI, but should expose one coherent edit workflow rather than mirroring
Timewarrior's command surface.

## Cross-product comparison

The ratings below describe only the local, single-user workflow relevant to this
roadmap. “Partial” means the capability exists with extra steps or weaker
authority.

| Product | Repeat common work | Correct or add past time | Keyboard-first workflow | Review context | Local/offline authority | Reminder control |
| --- | --- | --- | --- | --- | --- | --- |
| **Time Tracker (current)** | Partial: autocomplete, but no recent/continue action after reopening | None: completed entries are immutable and missed time cannot be added | Strong in-app F-key coverage | Partial: entry/daily toggle, no filters or day grouping | Strong: SQLite is authoritative | Basic intervals and active confirmation |
| **Toggl Track** | Strong: continue last or a recent entry, optional grouping | Strong editing and manual entry | Strong, including configurable shortcuts | Strong list grouping; graphical views omitted | Partial: offline cache eventually syncs | Strong schedule windows and snooze |
| **Clockify** | Strong through defaults and recent data | Strong editing and manual entry | Strong, including configurable shortcuts | Strong filters; reporting is separate from capture | Partial: cached offline capture tied to sync | Strong schedule preferences |
| **Harvest** | Strong: favorites and selected-entry restart | Strong day-oriented editing and missed-time entry | Strong capture and review shortcuts | Strong day-oriented timesheet | Weak: desktop app requires internet | Scheduled reminders |
| **Timewarrior** | Strong: explicit `continue` | Strong closed-interval capture and correction commands | Strong command-line workflow | Strong today-first summary and date ranges | Strong: local files are authoritative | None built in |

## TUI implementation roadmap

### Baseline track — complete outstanding validation

Close the acceptance and platform-test gaps recorded in the
[README Status](../README.md#status) before declaring the first roadmap slice
complete. This work is a parallel quality gate, not a reason to postpone product
design.

### Milestone 1 — daily-use usability and correction

This is the recommended next implementation milestone.

#### 1. Add Recent activities / Track again

Show up to five unique project/activity pairs, ordered by most recently completed
use and excluding archived targets. Selecting a pair should populate the fields,
clear the note, and focus the note field; the user then starts after optionally
adding a new note.

Implement the recent-pair projection in the application layer and expose it over
the versioned protocol. Do not derive business behavior independently in the TUI.
No new persistence or migration should be necessary.

Acceptance focus:

- a common activity is restartable with two actions after opening the TUI;
- duplicate pairs collapse to their most recent use;
- archived targets never appear; and
- a historical note is not accidentally reused.

#### 2. Make Start, Switch, and Restart explicit

Change the primary action according to active and selected state:

- `Start` when no timer is active;
- `Switch from <current> to <selected>` when the pair changes;
- `Already tracking` when pair and normalized note are unchanged; and
- `Restart with new note` when only the note changes.

Disable the no-op state. Preserve one transactional timestamp for switch and
restart transitions. Put the behavior in the application layer so the protocol,
agent, TUI, and tests agree.

#### 3. Split the single screen into focused views

Establish four keyboard-addressable views before adding the correction controls:

- **Track:** persistent active-timer strip, reminder, project/activity/note,
  recent activities, and start/stop;
- **Review:** completed entries, summaries, filters, correction, manual entry, and
  export;
- **Manage:** active and archived projects/activities; and
- **Settings:** reminder configuration and application paths/status.

Keep the active-timer strip and elapsed duration visible across views. Define
stable shortcuts for switching views and expose shortcut help inside the TUI.
Retain the existing F-key bindings during transition.

#### 4. Add correction and missed-time workflows

Add a Review action for one selected completed entry. The first correction slice
should support changing project, activity, note, start, and stop. Follow it with
manual creation of one closed entry for missed time. The milestone also includes
editing the active entry's project, activity, and note without changing its
original start time; this should use the same target and note validation rules.

Recommended invariants:

- a new or reassigned entry uses a selectable, non-archived target; creating a new
  project/activity follows the same naming rules as starting a timer, while an
  existing historical assignment may remain on its archived target when only time
  or note is corrected;
- stop is strictly after start;
- local input is converted to an unambiguous UTC instant before persistence;
- changes are persisted transactionally before success is shown; and
- completed entries should not overlap if the single-timer product model is to
  remain meaningful. Confirm this policy in the feature requirements before
  implementation.

The completed-entry overlap policy is a gate for this slice: correction and manual
entry must not be implemented until the feature requirements explicitly allow or
reject overlap and define the user-facing error behavior.

This work requires new application use cases, agent protocol methods, SQLite
repository operations, and unit/integration/e2e tests. It should not require a
schema migration unless revision history or undo is deliberately added.

#### 5. Make archive management safe and reversible

Move archive actions out of the capture fields. Validate the exact target and ask
for confirmation, including the existing rule that an active timer continues.
Add a Manage view that lists archived projects and activities and supports
unarchive. Reversibility is now preferable to treating a mistaken archive as a
permanent limitation.

Preserve the current hierarchy semantics: archiving or unarchiving a project does
not rewrite its activities' individual archive flags. Unarchiving a project makes
its non-archived activities selectable again. An activity cannot be unarchived
while its parent project remains archived; the user must restore the project
first.

### Milestone 2 — review and reporting

#### 6. Make Review day-oriented

Group completed entries by local date, show the date once per group, use compact
local `HH:MM` row values, and show each day's total. Preserve full offset-aware
timestamps in details and CSV. Show today's total in the Track view using the
shared reporting projection.

#### 7. Add filters and broader local summaries

Add date, project, and activity filters with `Today`, `This week`, `This month`,
and custom local date-range presets. Support project/activity totals across the
selected range while retaining the existing daily projection. Apply the same
filter model to on-screen detail, summaries, and CSV export so the displayed and
exported datasets cannot silently diverge.

Specify inclusive date boundaries, local time-zone and daylight-saving behavior,
archived-target selection, empty states, and filter combination semantics in the
feature requirements before implementation.

### Milestone 3 — configuration and reminder UX

#### 8. Manage supported settings from the TUI

Add a Settings view for the existing reminder toggles and intervals. Keep TOML as
the durable human-readable format, but write it through an application/config
port, validate before replacing the file, and allow the agent to reload supported
settings without a manual stop/restart cycle.

#### 9. Add reminder windows and snooze

Allow working-day/time windows and explicit snooze. Define whether snooze is
in-memory or persisted, what resets it, and how it interacts with start, switch,
stop, and background-process restart. Keep notification failure separate from
authoritative timer state.

#### 10. Evaluate favorites, defaults, and idle detection last

Derived recents may remove the need for favorites or a default project. Revisit
them after dogfooding the recent-work flow and collecting direct feedback.

Local idle detection could help with forgotten stops, but it introduces
platform-specific behavior and correction choices. If pursued, make it opt-in,
keep observed activity local, prompt rather than silently rewriting time, and put
OS behavior behind a narrow adapter. It is not part of the next two milestones.

## Explicit non-goals

The following remain outside the roadmap:

- web, mobile, or GUI interfaces, including tray/menu-bar mini timers;
- cloud sync, accounts, teams, approvals, or cross-device state;
- billable flags, rates, budgets, invoices, profitability, or expenses;
- plugins, imports, third-party integrations, or public automation APIs;
- screenshots, GPS tracking, employee surveillance, or telemetry; and
- calendar integration and graphical activity timelines.

Pomodoro and other focus modes are not prohibited by the interface constraint,
but they do not address the current product's most important gaps and should not
displace the roadmap above.

## Recommended implementation sequence

1. Enumerate and close the remaining baseline acceptance/platform checks.
2. Define feature requirements for Recent activities and explicit
   Start/Switch/Restart behavior; implement the projection and protocol slice end
   to end.
3. Establish the Track/Review/Manage/Settings view structure and persistent timer
   strip before adding more controls to the existing screen.
4. Specify correction invariants; implement completed-entry edit, active metadata
   edit, and manual closed entry as separate vertical slices.
5. Add archive confirmation, archived-item listing, and unarchive.
6. Add day-grouped history and today's total.
7. Specify and implement shared filters, range summaries, and filtered export.
8. Add TUI-managed settings and agent reload.
9. Add reminder windows and snooze.
10. Reassess favorites, defaults, and prompt-only idle detection from observed
    use before expanding the product further.

For every slice, keep domain/application logic independent of Textual, route all
writes through the background process, add tests with the implementation, and
finish with the repository's complete canonical check suite.
