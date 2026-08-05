# Quick switch deck

**Status:** Implemented

## Purpose

Let a user resume common work quickly while keeping timer transitions deliberate and clearly separated from editing the active entry.

## Required behavior

- Show up to five unique recent project/activity pairs in the Track workflow, ordered by most recently completed use.
- Derive ordering, canonical names, and eligibility in the application layer and expose them through the versioned agent protocol.
- Exclude archived projects and activities and collapse repeated completed entries to each pair's most recent use.
- Assign visible shortcuts `1` through `5` to the displayed entries.
- Pressing a number shortcut selects and highlights its entry, copies its project
  and activity into Manual entry so the primary action reflects the selection,
  clears the Manual entry note, and does not change timer state.
- Pointer selection must have the same non-persistent effect as a numbered
  shortcut, including updating Manual entry's project and activity and clearing
  its note.
- Moving the highlighted entry with the arrow keys must have the same
  non-persistent effect as pointer and numbered selection.
- Describe the pending confirmed action as:
  - `Start` when no timer is active;
  - `Switch from <current> to <selected>` when another pair is active; or
  - `Current` when the selected pair is already active.
- Pressing `Enter` from the deck or its dedicated single-line optional-note input
  confirms the selected Start or Switch action. Do not show a separate
  quick-switch confirmation button.
- Starting or switching directly from the deck creates the new active entry without copying a historical note.
- Selecting the current pair must not offer a timer transition. `Enter` must leave the active timer unchanged.
- Put the deck first in Track and provide a dedicated single-line optional-note
  input immediately below it. A note entered there applies only to the pending
  Start or Switch. After that action is persisted, copy a non-empty normalized
  note into the Manual entry note field.
- Put the normal capture workflow below the deck under the label `Manual entry`,
  with its own independent single-line optional-note input.
- Put Stop and Update active details below the Manual entry Start action rather
  than associating them with the selected deck entry.
- Keep active-detail editing distinct from switching or restarting. It must continue to preserve the active entry's identity and start time.
- Preserve the existing project, activity, and note capture path for targets not shown in the deck and for creating new targets.
- Refresh the deck and its action descriptions after connection, start, switch, restart, stop, active-detail editing, archive, and restoration.
- When no eligible recent pair exists, show a concise empty state and focus the normal capture path.
- Keep the deck usable without horizontal scrolling at supported narrow terminal widths.

## Invariants and error handling

- Selecting or highlighting an entry has no persistence side effects.
- Confirmed deck actions must use application-layer timer operations through the background agent. The TUI must not implement transition rules independently.
- A confirmed switch must stop the active entry and start the selected pair at one shared UTC transition timestamp without overlap.
- A direct deck action never reuses a historical note.
- Activating the current pair is a rejected no-op and must not change its entry ID, start time, note, history, elapsed time, or reminder deadline.
- Archived or stale targets are rejected without changing timer or reminder state.
- Number shortcuts must not select deck entries while focus is inside a text-editing control.
- If the deck cannot be loaded, retain the active timer and capture fields, keep Stop and Update available, and report the error through the existing message area.
- Success must be reported only after the transition is durably persisted.

## Acceptance criteria

1. Track displays no more than five unique, eligible recent pairs in most-recently-completed order with visible shortcuts `1` through `5`.
2. Pressing a number selects the corresponding entry without starting, stopping, or switching a timer.
3. Pressing `Enter` with no active timer starts the selected pair and updates the current-timer area from canonical persisted values.
4. Pressing `Enter` with another pair active creates adjacent, non-overlapping entries at one transition timestamp.
5. Selecting the current pair shows `Current`; pressing `Enter` leaves the timer, note, history, and reminder deadline unchanged.
6. Historical notes are never copied into deck-started entries.
7. A quick-switch note entered before confirmation is applied to the new active
   entry under the existing note-normalization rules. Numbered, pointer, or
   arrow-key selection updates Manual entry's project and activity and clears its
   independent note; successful confirmation then copies a non-empty persisted
   quick-switch note into that Manual entry note.
8. Number keys entered inside text-editing controls do not change deck selection.
9. Archived pairs do not appear, and archive or restoration refreshes the visible deck.
10. The normal capture path remains available below the deck as `Manual entry`
    for uncommon and new project/activity pairs, with Start followed by Stop and
    Update controls.
11. Unit, SQLite, IPC, and Textual tests cover projection ordering, selection without persistence, Enter confirmation, atomic switching, current-pair no-op behavior, note handling, archive exclusion, focus guards, recovery, and narrow layout.

## Documentation impact

- Neither the top-level requirements nor the architecture changes.
- Update the recent-activities requirement because the quick switch deck replaces its existing two-action selection flow.
- Update the Track layout and focused-view requirements to include the deck, pending action, and separate current-timer controls.
- Update the README and shortcut help with number-key selection, `Enter` confirmation, note handling, and current-pair behavior.
- No schema migration is required.
