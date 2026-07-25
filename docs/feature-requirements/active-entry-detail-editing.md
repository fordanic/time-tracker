# Active-entry detail editing

**Status:** Implemented

## Purpose

Let a user correct the project, activity, or note of work that is still running
without ending or restarting its timer. This completes the roadmap's initial
correction and missed-time workflow.

## Required behavior

- Add an explicit Update active details action to Track, available by pointer and
  `F11`, using the current project, activity, and note inputs.
- Persist changes to the single active entry's project/activity assignment and
  normalized note while preserving its entry ID, original start timestamp, and
  creation timestamp.
- Trim names and normalize notes consistently with Start. When the assignment
  changes, reuse a matching selectable target case-insensitively or create a new
  selectable target under the timer-start naming rules; reject archived targets.
- When the assignment is unchanged, allow a note-only edit while retaining the
  active entry's target even if it has been archived since the timer started.
- Keep Start/Switch/Restart behavior available as the distinct transition choice.
  Enable Update active details only when a timer is active and the normalized
  Track inputs differ from it.
- After success, show canonical persisted values in Track, refresh target
  suggestions, and update the persistent active-timer strip without adding a
  completed entry.

## Invariants and error handling

- Resolve or create the target and update the active row in one SQLite transaction
  owned by the background process. A rejection leaves both the active entry and
  any attempted new target unchanged.
- Reject missing names, no active timer, an archived reassignment, or normalized
  values identical to the active entry. Report the error in the persistent TUI
  message area without changing timer or reminder state.
- A successful edit does not capture a replacement start time, stop the entry,
  create another entry, or restart the active-reminder interval.
- Update future and already-pending active-reminder text to the new canonical
  project/activity while preserving the existing monotonic reminder deadline.

## Acceptance criteria

1. With an active timer and changed Track fields, pointer activation or `F11`
   updates project, activity, and note while preserving entry ID and start time.
2. The edit creates no completed entry, does not reset elapsed time, and survives
   TUI and agent restart with its canonical values.
3. Case-insensitive target reuse and new target creation succeed; archived
   reassignment and missing names are rejected atomically. A note-only edit on an
   unchanged archived assignment succeeds.
4. Identical normalized values disable the TUI action and are rejected by a direct
   application or protocol request without invoking the clock or repository edit.
5. Reminder timing is unchanged by success or rejection, while subsequent and
   pending active prompts use the edited canonical project/activity.
6. Unit, SQLite integration, IPC/reminder integration, and Textual workflow tests
   cover normalization, no-op protection, atomic persistence, archived targets,
   shortcut and pointer use, start preservation, no history creation, recovery,
   and reminder metadata without deadline reset.

## Documentation impact

- Top-level tracking requirements now authorize editing active details without a
  timer transition. Architecture records the transactional update and reminder
  metadata behavior. The existing schema supports the update, so no migration is
  required.
