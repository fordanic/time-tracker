# Day-oriented Review and today's completed total

**Status:** Implemented

## Purpose

Make accumulated history easier to scan as a local timesheet and show the user
how much completed work has been recorded today without leaving Track.

## Required behavior

- In Review's completed-entry mode, group completed time by local calendar date,
  show the date only on the first entry row in each group, render local start and
  stop values as compact `HH:MM` times, and add a total row after each day.
- Draw a theme-safe horizontal divider row between local dates in both
  completed-entry and daily-summary modes. Divider rows are presentation only:
  they do not represent reporting data, are excluded from export, and cannot be
  loaded, corrected, or deleted as completed entries.
- Derive both grouped rows and day totals from one application-layer reporting
  projection. The TUI must not independently calculate date boundaries or
  durations.
- Split an entry that crosses local midnight into one display segment per local
  date so each group total follows the existing daily-summary rule. Each segment
  retains the source entry's identity, project, activity, and note and shows only
  the portion of its derived duration that belongs to that date.
- Loading any segment for correction loads the full source entry once, including
  its complete timezone-free local start and stop wall-clock timestamps. A day-total row is
  not a completed entry and cannot be loaded for correction.
- Keep the existing Daily summaries representation and both CSV formats
  unchanged. CSV entry export continues to contain each full entry once with
  offset-aware timestamps; summary export continues to use the shared local-day
  split.
- Show `Today's completed time` in Track using the same day-oriented projection.
  It includes completed entry segments assigned to the current local date and
  excludes the active timer until that timer is persisted as completed.
- Refresh the Track total after start transitions that complete an entry, stop,
  correction, and missed-time creation, and roll it over when the local date
  changes while the TUI remains open.

## Invariants and error handling

- Preserve chronological day and segment ordering. Presentation grouping does
  not mutate, duplicate, or replace persisted entries.
- Resolve local dates and midnight boundaries from stored UTC instants in the
  user's current local time zone, including offset changes. Durations remain
  differences between stored instants rather than differences between displayed
  wall-clock labels.
- Selecting a repeated segment of an entry that spans days always targets the
  same persisted entry ID. Selecting a day-total row reports that a completed
  entry must be selected and leaves editor and history state unchanged.
- If history cannot be loaded, retain the last successfully rendered Track total
  and Review data and report the agent error through the persistent message area.

## Acceptance criteria

1. Completed time is shown in chronological local-date groups with the date once,
   `HH:MM` row times, one derived total after each day, and a visible boundary
   between adjacent dates in completed-entry and daily-summary modes.
2. An entry crossing local midnight appears as correctly clipped segments in
   both affected groups, and the group totals equal the sum of their segments,
   including across a local UTC-offset change.
3. Loading either segment of a cross-midnight entry opens the same entry ID and
   full timezone-free local wall-clock timestamps; a total row cannot be loaded.
4. Entry and daily-summary CSV output retains its existing schema, full timestamp
   precision, ordering, overwrite confirmation, and midnight-splitting behavior.
5. Track shows the current local date's completed duration, does not count the
   running portion of an active timer, refreshes after relevant writes, and
   changes to the new day's value after local midnight.
6. Application projection and Textual workflow tests cover grouping, compact
   rendering, overnight splitting, day totals, correction selection, today's
   completed total, and retained summary/export behavior.

## Documentation impact

- Neither the top-level requirements nor the architecture changes. This feature
  presents the already-authorized completed history and local daily totals
  through the existing application reporting and TUI boundaries and requires no
  protocol or schema migration.
