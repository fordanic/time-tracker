# Manual missed-time entry

**Status:** Implemented

## Purpose

Let a user record one forgotten interval as a completed entry without briefly
starting a live timer or editing SQLite directly. This is the second ordered
slice of the roadmap's correction and missed-time workflow.

## Required behavior

- In Review's completed-entry mode, provide an Add missed entry action that opens
  the existing entry editor in creation mode for project, activity, note, start,
  and stop.
- Clear the target and note fields and prefill an editable one-hour local interval
  ending at the current minute. Render both values as timezone-free local
  `YYYY-MM-DD HH:MM:SS` wall-clock timestamps.
- Trim project and activity names, normalize an empty or whitespace-only note to
  no note, and resolve local timestamps through the user's local time zone.
- Reuse matching selectable project/activity names case-insensitively or create a
  new selectable pair using the timer-start naming rules. Reject an archived
  project or activity.
- After successful creation, refresh completed history, daily summaries, recent
  activities, and project suggestions; select the new row when possible and leave
  its canonical persisted values in the editor.
- Manual creation is unavailable in daily-summary mode. It does not start, stop,
  switch, or otherwise change the active timer.

## Invariants and error handling

- Stop must be strictly after start. The new half-open interval `[start, stop)`
  must not overlap any completed or active entry, but may touch an existing
  boundary.
- Target resolution, overlap validation, and insertion occur in one SQLite
  transaction owned by the background process. No partial project, activity, or
  entry is retained when a request is rejected.
- Capture the entry's creation timestamp from the injected application clock only
  after field validation. Duration remains derived from start and stop.
- Reject invalid, ambiguous, or nonexistent local timestamps, missing names, a
  non-positive interval, archived targets, or overlap with a concise error in
  the persistent TUI message area. Preserve the entered values after rejection
  so they can be repaired.

## Acceptance criteria

1. A user can choose Add missed entry in Review, edit the five entry fields, save,
   and immediately see one new completed row without affecting the active timer.
2. The editor initially offers the previous local hour without UTC-offset
   suffixes; malformed, ambiguous, or nonexistent local input is rejected
   without creating an entry.
3. Stop equal to or before start and overlap with a completed or active entry are
   rejected atomically, while touching an existing boundary succeeds.
4. Creation reuses canonical names case-insensitively, can create a new selectable
   pair, and rejects archived targets without leaving partial target records.
5. The new entry appears in history, summaries, CSV source data, and recent-work
   projection through their existing shared sources and survives agent restart.
6. Unit, SQLite integration, IPC integration, and Textual workflow tests cover
   normalization, injected creation time, target handling, overlap rejection,
   protocol transport, creation mode, active-timer preservation, and refresh.

## Documentation impact

- Top-level requirements now authorize manual creation of closed missed-time
  entries under the existing single-timer and no-overlap model. Architecture adds
  the agent-owned transactional insertion boundary. The existing schema already
  supports the entry, so no migration is required.
