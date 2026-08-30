# Completed-entry correction

**Status:** Implemented

## Purpose

Let a user repair an inaccurate completed timer inside the product without
discarding the entry or editing SQLite directly. This is the first ordered slice
of the roadmap's correction and missed-time workflow; manual closed-entry creation
and active-entry editing remain later slices.

## Required behavior

- In Review's completed-entry mode, let the user load the selected completed row
  into correction fields for project, activity, note, start, and stop, then save
  the corrected entry through the background process.
- Populate start and stop as local `YYYY-MM-DD HH:MM:SS` wall-clock timestamps
  without UTC-offset suffixes. Resolve changed input through the user's local
  time zone and reject ambiguous or nonexistent local times so each edited value
  maps to one unambiguous UTC instant, including during daylight-saving
  transitions.
- Populate start and stop with whole-second precision and retain the stored
  instant for a boundary left at its displayed value. Stored transitions carry
  sub-second precision and a switch records one instant as both the earlier
  entry's stop and the later entry's start, so resubmitting a displayed boundary
  must not move it into a neighboring entry.
- Trim project and activity names and normalize the note by trimming it and
  treating an empty value as no note, consistently with timer capture.
- When the project/activity assignment changes, reuse a matching selectable target
  case-insensitively or create a new project/activity using the timer-start naming
  rules. Reject reassignment to an archived project or activity.
- When the assignment is unchanged, allow correction of only time or note while
  retaining the historical target even if it has since been archived.
- After a successful correction, refresh completed history, daily summaries,
  recent activities, and selectable project suggestions, keep the corrected row
  selected when possible, and show the canonical persisted values.
- Correction is unavailable in daily-summary mode and when no completed row is
  selected.

## Invariants and error handling

- Stop must be strictly after start.
- Completed and active entries use half-open intervals: `[start, stop)`. A
  correction must not overlap any other entry, including the active entry, but may
  touch another entry's start or stop. The entry being corrected is excluded from
  its own overlap check.
- Target resolution, overlap validation, and the update occur in one SQLite
  transaction owned by the background process. The original entry remains
  unchanged if any validation or persistence step fails, and success is reported
  only after commit.
- The entry identifier and original creation timestamp do not change. Duration
  remains derived from corrected timestamps; no revision history or undo record is
  added in this slice.
- Reject an unknown entry, invalid, ambiguous, or nonexistent local timestamp,
  non-positive interval,
  archived reassignment, or overlap with a concise error in the persistent TUI
  message area. A rejection leaves the correction fields available for repair.

## Acceptance criteria

1. A user can select one completed entry in Review, load its canonical values,
   change all five editable fields, save, and immediately see the corrected row.
2. Timezone-free local input is resolved to UTC before persistence; malformed,
   ambiguous, or nonexistent local input is rejected without changing history.
3. Saving with stop equal to or before start is rejected. Saving an interval that
   intersects another completed or active entry is rejected, while an interval
   that only touches a neighboring boundary succeeds. Correcting only the note,
   target, or one boundary of an entry that adjoins a neighbor at a sub-second
   instant succeeds and leaves the untouched boundary byte-identical.
4. Reassignment reuses canonical names case-insensitively, can create a new
   selectable pair, and rejects archived targets. An unchanged archived assignment
   remains valid for time- or note-only correction.
5. Correction preserves the entry ID, excludes the active timer from mutation,
   persists atomically, and updates history, summaries, export input data, and
   recent-work projections through their existing shared sources.
6. Unit, SQLite integration, IPC integration, and Textual workflow tests cover
   normalization and timestamp validation, successful correction, overlap and
   archived-target rejection, retained sub-second boundaries, protocol transport,
   row selection, and refresh.

## Documentation impact

- Top-level requirements now authorize completed-entry correction and define the
  no-overlap rule. Architecture records the agent-owned transactional correction
  boundary. The existing schema already supports the update, so no migration is
  required.
