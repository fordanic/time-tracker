# Top-Level Requirements

This document and [Architecture](architecture.md) are the authoritative documents
for Time Tracker. This document defines the product's durable top-level behavior,
quality constraints, and boundaries without tying them to a delivery milestone.
Architecture defines the authoritative technical choices and boundaries.

The [competitive assessment and TUI roadmap](competitive-assessment.md) is
planning input, not a requirements source. When a roadmap candidate is selected
for implementation, define its additional behavior and acceptance criteria in
[Feature Requirements](feature-requirements/README.md). Feature requirements are
subordinate to this document and Architecture and cannot override either one. If
a feature changes a top-level product requirement or an architectural boundary,
update the corresponding authoritative document in the same change.

## Purpose

Time Tracker helps one user reliably record time against named activities within
projects. It is local-first, keyboard-first, and works without an account or
internet connection. The current product interface is a TUI.

## Product principles

- **Local authority:** application data remains usable without an account,
  network connection, or remote service.
- **Reliable capture:** an accepted timer transition is durable and recoverable.
- **One clear timer:** at most one activity is active at a time.
- **Fast keyboard workflow:** common tracking actions are efficient without a
  pointer.
- **Derived time:** timestamps are authoritative; duration is calculated rather
  than edited independently.
- **Separation of concerns:** product rules are independent of the TUI and storage
  implementation.
- **User control:** the product does not require telemetry or silently discard
  recorded time.

## Product model

- A project contains activities.
- Every activity belongs to exactly one project.
- A time entry contains an activity, start time, optional stop time, and optional
  note. Its project comes from the activity.
- An entry without a stop time is the active timer. There can be at most one.
- Duration is always derived from timestamps; it is never stored or edited as an
  independent value.

## Required behavior

### Projects and activities

- Create and list projects and their activities.
- Archive projects and activities. Archived items remain visible in history but
  cannot be selected for new timers.
- Archiving does not stop an active entry. Archived names remain reserved and
  cannot be recreated by typing the same name again.
- Projects and activities already used by entries are archived rather than
  permanently deleted.
- Allow archived projects and activities to be restored. Restoring a project does
  not change its activities' independent archive flags; its non-archived
  activities become selectable again. An activity cannot be restored while its
  parent project remains archived.
- Require confirmation of the exact project or activity before archiving it and
  make clear that archiving does not stop an active entry.

### Tracking

- Start and stop an activity from the TUI.
- Starting a different activity automatically stops the active one and starts the
  new one at the same transition timestamp, without overlap.
- Starting the active project/activity with a different normalized note closes
  and restarts it at one transition timestamp; its new entry begins at that
  timestamp with the new note.
- Starting with the same project/activity and normalized note is a rejected
  no-op: it does not create an entry, reset the active start time, or reset timer
  reminders.
- Show the active project, activity, start time, and elapsed duration prominently.
- Allow an optional plain-text note on the active entry.
- Allow the active entry's project, activity, and note to be edited without
  changing its entry identity, original start time, or reminder deadline. A
  changed assignment uses a non-archived target; an unchanged assignment may
  remain on a target archived while it was active.
- Persist an active-detail edit atomically before reporting success. The edit does
  not stop, restart, or add an entry, and reminder prompts use the updated target
  names without restarting their interval.
- Persist each timer transition before reporting success.
- Restore an active timer with its original start time after a restart, crash, or
  forced termination. Recovery must not invent a stop time.

### History and summaries

- List completed entries chronologically with project, activity, local start and
  stop times, derived duration, and note.
- Allow correction of one completed entry's project, activity, note, start, and
  stop. A corrected stop must be strictly after its start, and its half-open
  interval must not overlap another completed or active entry; touching boundaries
  are allowed.
- Allow permanent deletion of one selected completed entry after explicit
  confirmation. Deletion does not change an active timer.
- Reassignment during correction uses a non-archived project/activity target,
  while an unchanged historical assignment may remain on its archived target.
- Persist correction atomically before reporting success and preserve the entry's
  identity. Require offset-aware time input so local edits resolve to unambiguous
  UTC instants.
- Allow manual creation of one completed entry for missed time. It uses a
  non-archived project/activity target, requires an offset-aware start and stop,
  and follows the same strict positive-duration, half-open no-overlap, atomic
  persistence, and derived-duration rules as correction.
- Creating missed time does not change the active timer. It may create a new
  project/activity pair using the same naming and reuse rules as timer start.
- Provide local daily totals per project and activity.
- Split entries crossing local midnight across the corresponding daily totals.
- Filter completed history and summaries by inclusive local calendar-date range,
  project, and activity, and provide project/activity totals across the selected
  range. Apply one filter selection consistently to on-screen detail, summaries,
  and export.
- Preserve historical entries and their names when a project or activity is
  archived.

### Reminders and process lifecycle

- A single background process owns timer state, database access, and reminders.
- Closing the TUI leaves that process and its reminders running. Explicitly
  stopping the process stops reminders but leaves any active entry open.
- With no active timer, send a native desktop notification every five minutes by
  default.
- With an active timer, ask every 30 minutes by default whether it is still active.
- Both reminder intervals are configurable and independently disableable.
- Allow an optional shared weekly local-time window for reminder delivery and a
  configurable explicit snooze duration.
- Allow opt-in local input-idle detection to request an active-timer reminder
  early. Idle detection is advisory and content-free: it must not record input
  details or silently change tracked time.
- A reminder due outside its window waits for the next opening without producing
  catch-up notifications. Snoozing defers the pending reminder without changing
  timer state or its configured recurring interval.
- Ignoring an active reminder leaves the timer running; confirming it restarts the
  interval.
- Reminders require no internet connection. A connected TUI may also show them.

### Storage and configuration

- Store application data in SQLite and configuration in a human-readable TOML
  file at platform-appropriate per-user locations.
- Work with built-in defaults when no configuration file exists.
- Report invalid configuration without overwriting it.
- Persist the selected TUI theme and apply it on the next launch, falling back to
  the built-in default if the saved theme is unavailable.
- Store timestamps in UTC and display them in the user's local time zone.
- Permit entries to cross midnight and reject a stop time before its start time.
- Preserve user data across crashes, restarts, and database migrations.

### Export

- Export completed entries, ordered by start time, to UTF-8 CSV with these
  columns:

  ```text
  project,activity,start_time,stop_time,duration_seconds,note
  ```

- Export timestamps as ISO 8601 with a UTC offset and apply standard CSV quoting.
- Use comma as the default export delimiter and allow the user to select pipe as
  an alternative. Apply standard delimited-text quoting so notes containing the
  selected delimiter, quotes, or line breaks round-trip without data loss.
- Require confirmation before overwriting a file.
- Do not export an active entry.
- Export daily project/activity totals using local calendar dates and these
  columns:

  ```text
  date,project,activity,duration_seconds
  ```

- Order daily summaries by date, project, and activity. Apply the same UTF-8 CSV,
  standard quoting, overwrite-confirmation, and active-entry exclusion rules.
- Export project/activity totals across the selected filter using these columns:

  ```text
  project,activity,duration_seconds
  ```

- A date-filtered completed-entry export clips entries at the selected local-date
  boundaries so exported timestamps and derived durations represent only the
  selected time. Filtered daily and range summaries use the same selected time.
- Order range totals by project and activity. Apply the same UTF-8 CSV, standard
  quoting, overwrite-confirmation, and active-entry exclusion rules. An empty
  filtered export contains the applicable header and no data rows.

## Quality requirements

- Support Linux, Windows, and macOS; develop primarily on Linux and validate all
  three.
- Give every build one application version. Use three-part final versions and
  numbered release candidates, and report the same version from source metadata,
  the CLI, native release artifacts, and Git tags.
- Validate a native release artifact on its target operating system before
  publication and publish its SHA-256 checksum with it.
- Keep common tracking actions fast and keyboard-driven.
- Do not require telemetry, a remote service, or an account.
- Use explicit database migrations and prevent more than one active entry at the
  database boundary.
- Make timer, recovery, switching, and reminder behavior testable with a
  controlled clock.
- Keep domain and application logic independent of Textual, SQLite, IPC, and
  notification libraries.
- Treat the background process as the single database writer.
- Isolate operating-system behavior behind narrow adapters.

## Verification baseline

Automated tests and platform validation must demonstrate that:

1. A user can create a project and activity, track it, stop it, and see the
   correct derived duration.
2. Switching activities produces adjacent, non-overlapping entries.
3. An active timer survives both a normal restart and a simulated crash.
4. Reminders work according to configuration after the TUI closes, and ignoring
   an active reminder does not stop the timer.
5. Archived items remain readable in history but cannot start new timers.
6. Two active entries cannot be created.
7. CSV export preserves timestamps, Unicode, and notes containing commas, quotes,
   and newlines; daily summary export aggregates by project and activity and
   divides entries at local midnight. Shared date/project/activity filters produce
   matching detailed, daily, and range-total exports, including local-boundary
   clipping and header-only empty results.
8. Missing configuration uses defaults; invalid configuration is reported without
   destroying the file.

Keep acceptance criteria for top-level behavior here. Feature-specific acceptance
criteria belong in [Feature Requirements](feature-requirements/README.md). A feature is
not complete until its relevant automated and platform checks pass.

## Product boundaries

The following are not part of the current product direction:

- GUI, web, and mobile interfaces.
- Concurrent timers, users, or foreground clients.
- Accounts, synchronization, collaboration, telemetry, and remote services.
- Billing, invoicing, rates, costs, profitability, expenses, and approvals.
- Plugins, third-party integrations, imports, and public automation APIs.
- Screenshots, GPS tracking, and employee-surveillance features.

Native release-candidate and final-release downloads may be published on GitHub
after automated target-platform validation in the release workflow. Installers,
package-manager publishing, and automatic updates are not currently required.

Features absent from this list are not automatically approved. Record approved
additional feature behavior in [Feature Requirements](feature-requirements/README.md)
before implementation. Update this document first, or in the same change, when a
feature changes a top-level requirement.

## Open product decisions

- Minimum supported OS versions and CPU architectures.
- Behavior during computer sleep, system-clock changes, and time-zone changes.
- Whether the background process starts at login.
- Reminder windows, snooze persistence, and live configuration reload.
- Whether favorites or defaults are needed after dogfooding derived recent work.
