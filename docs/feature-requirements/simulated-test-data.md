# Simulated test data

**Status:** Implemented

## Purpose

Give developers a quick, repeatable way to populate an empty local database with
realistic projects, activities, completed entries, and notes for manual TUI
testing.

## Required behavior

- `make seed-test-data CONFIRM=1` stops the background agent and waits for it to
  release the database before writing.
- The target creates a fixed, deterministic data set so repeated clean-and-seed
  cycles produce the same project, activity, time, duration, and note patterns
  for the same ending date.
- The generated local calendar window contains the most recent 45 complete days:
  it is inclusive from 45 days before the run date through the day before the run
  date. Every Monday through Friday in that window has completed entries, and
  Saturdays and Sundays have none.
- The data includes multiple projects and activities, varied entry durations,
  entries both with and without notes, and no active timer.
- Seeding changes only the SQLite database. Existing configuration, credentials,
  runtime files, and logs are preserved.

## Invariants and error handling

- Explicit confirmation is required because the target writes simulated records
  to the user's default local database.
- The seed command refuses to run when the database already contains any project
  or entry. It directs the developer to explicitly clear the database first,
  preventing simulated records from mixing with existing data.
- Generated entries use local wall-clock work times converted to UTC through the
  same timestamp boundary as normal manually created entries. Entries have
  positive durations and never overlap.
- The existing application and SQLite repository boundaries create and validate
  the records; the TUI never writes SQLite directly.
- A failure to stop the agent or validate the empty database prevents seeding.

## Acceptance criteria

1. Running the confirmed target against an empty database creates multiple
   projects, activities, and completed entries spanning the inclusive 45-day
   window without creating an active timer.
2. Every weekday in the window contains at least one entry, no weekend contains
   an entry, and the data includes both populated and empty notes.
3. Running without confirmation fails before stopping the agent or writing any
   file.
4. Running against a non-empty database fails without adding or changing any
   project, activity, or entry.
5. Unit and integration tests cover generation boundaries, weekday-only data,
   orchestration order, persisted records, and the non-empty database guard.

## Documentation impact

- The README documents the developer command and its empty-database prerequisite.
- Neither the top-level product requirements nor Architecture changes: this is a
  guarded developer workflow that reuses the existing application and SQLite
  boundaries rather than a new product capability or technical boundary.
