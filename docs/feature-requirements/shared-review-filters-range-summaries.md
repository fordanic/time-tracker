# Shared Review filters and range summaries

**Status:** Implemented

## Purpose

Let a user narrow accumulated history to a useful local period and target, then
review or export the same selected time without having to reconcile different
datasets.

## Required behavior

- Add an **All time** date preset plus the roadmap presets **Today**, **This
  week**, **This month**, and **Custom**. Today is the current local calendar
  date; This week is the Monday-through-Sunday calendar week containing today;
  and This month is the first through last calendar date of the current local
  month.
- Custom requires an ISO 8601 start date and end date. Both boundaries are
  inclusive. Resolve presets and custom dates in the user's current local time
  zone, including daylight-saving offset changes.
- Add optional project and activity filters. Match trimmed names
  case-insensitively against canonical historical names. An activity without a
  project matches that activity name beneath any project; when both are present,
  both must match the same completed segment.
- Combine date, project, and activity criteria with AND. A blank target criterion
  means any value. Make canonical targets represented in completed history
  available for selection even when the project or activity is now archived.
- Apply one application-layer filter model to completed-entry Review, daily
  summaries, range totals, and all three matching CSV exports. The TUI may resolve
  controls into that model but must not implement separate filtering or
  aggregation rules.
- Date filtering operates on completed-time portions assigned to the selected
  local dates. An entry crossing a selected boundary contributes only its segment
  inside the inclusive date range. With no date bound, retain each full entry.
- Retain the day-grouped completed-entry and daily-summary representations. Add a
  **Range totals** representation with one row per project/activity pair and the
  pair's total completed duration across the current filter.
- Detailed CSV keeps the existing columns. When a date filter clips an entry,
  export the selected contiguous portion with clipped offset-aware start and stop
  timestamps so its duration agrees with the selected Review data. Daily-summary
  CSV keeps its existing columns and contains only selected dates and targets.
  Range-total CSV uses these columns:

  ```text
  project,activity,duration_seconds
  ```

- Changing any filter or representation refreshes Review immediately and clears
  a pending overwrite confirmation. A concise description of the active filter
  remains visible beside the results.
- Show a concise empty state when no completed time matches. Exporting an empty
  selection writes only the selected representation's header and reports zero
  rows.

## Invariants and error handling

- Reject a malformed custom date, a missing custom boundary, or a start date
  after the end date. Keep the last valid rendered selection and do not export
  until the filter is valid; report the error in the persistent message area.
- Derive selected durations from stored UTC instants. Local-date clipping and
  daylight-saving changes must not turn wall-clock labels into authoritative
  durations or create overlaps.
- Filtering and aggregation are read-only. They never mutate entries, archive
  state, targets, the active timer, or reminder scheduling. The active entry
  remains excluded from Review and export.
- Preserve chronological ordering for detailed and daily results. Order range
  totals by case-insensitive project and activity name, with canonical spelling as
  the stable tie-breaker.
- A completed-entry segment remains correctable through its source entry ID.
  Summary and empty-state rows are not correctable. Applying a filter does not
  alter a loaded editor or persist any correction.
- The filter serialized for export must be the same validated model used by the
  current on-screen representation. An agent rejection leaves the destination
  untouched except for the existing confirmed-overwrite semantics.

## Acceptance criteria

1. All time, Today, This week, This month, and a valid custom inclusive range show
   the expected local-date segments, including an entry crossing midnight or a
   UTC-offset transition.
2. Project and activity filters match canonical historical names
   case-insensitively, can select archived targets, work independently, and
   combine with each other and the date filter using AND.
3. Completed-entry, daily-summary, and range-total views derive from the same
   filter; range totals equal the sum of the selected detailed durations for each
   project/activity pair.
4. Each CSV representation applies the current filter. Detailed export clips at
   selected date boundaries, daily export retains local dates, range export uses
   the approved three-column schema, and each exported duration agrees with the
   on-screen selection.
5. Invalid custom input preserves the last valid results, reports a concise
   error, and blocks export. A valid selection with no matches shows an empty
   state and exports a header-only file after normal overwrite confirmation.
6. Unit, CSV, IPC, and Textual workflow tests cover preset boundaries, inclusive
   custom dates, filter combinations, archived targets, empty and invalid states,
   overnight and daylight-saving clipping, all representations, and filtered
   export.

## Documentation impact

- Top-level requirements now authorize shared Review filters and range-total CSV
  export, resolving the corresponding open product decision. Architecture records
  the application-owned filter/projection and protocol transport boundaries. The
  existing entry schema is unchanged, so no migration is required.
