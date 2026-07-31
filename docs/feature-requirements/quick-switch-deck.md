# Quick switch deck

**Status:** Implemented

## Purpose

Let a user resume common work quickly while keeping timer transitions deliberate and clearly separated from editing the active entry.

## Required behavior

- Show up to five unique recent project/activity pairs in the Track workflow, ordered by most recently completed use.
- Derive ordering, canonical names, and eligibility in the application layer and expose them through the versioned agent protocol.
- Exclude archived projects and activities and collapse repeated completed entries to each pair's most recent use.
- Assign visible shortcuts `1` through `5` to the displayed entries.
- Pressing a number shortcut selects and highlights its entry but does not change timer state.
- Pointer selection and keyboard selection must have the same non-persistent effect.
- Describe the pending confirmed action as:
  - `Start` when no timer is active;
  - `Switch from <current> to <selected>` when another pair is active; or
  - `Current` when the selected pair is already active.
- Pressing `Enter` confirms the selected Start or Switch action.
- Starting or switching directly from the deck creates the new active entry without copying a historical note.
- Selecting the current pair must not offer a timer transition. `Enter` must leave the active timer unchanged.
- Provide an explicit optional-note interaction before confirmation. A note entered there applies only to the pending Start or Switch.
- Keep Stop and Update active details associated with the current-timer area rather than the selected deck entry.
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
7. An optional note entered before confirmation is applied to the new active entry under the existing note-normalization rules.
8. Number keys entered inside text-editing controls do not change deck selection.
9. Archived pairs do not appear, and archive or restoration refreshes the visible deck.
10. The normal capture path remains available for uncommon and new project/activity pairs.
11. Unit, SQLite, IPC, and Textual tests cover projection ordering, selection without persistence, Enter confirmation, atomic switching, current-pair no-op behavior, note handling, archive exclusion, focus guards, recovery, and narrow layout.

## Documentation impact

- Neither the top-level requirements nor the architecture changes.
- Update the recent-activities requirement because the quick switch deck replaces its existing two-action selection flow.
- Update the Track layout and focused-view requirements to include the deck, pending action, and separate current-timer controls.
- Update the README and shortcut help with number-key selection, `Enter` confirmation, note handling, and current-pair behavior.
- No schema migration is required.
