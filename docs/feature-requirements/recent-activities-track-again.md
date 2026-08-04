# Recent activities / Track again

**Status:** Implemented

## Purpose

Let a user resume common work without retyping a project and activity after the
TUI opens, while keeping the user in control of the new timer and its note.

## Required behavior

- Show up to five unique project/activity pairs in the Track workflow, ordered
  by most recently completed use.
- Derive recent pairs in the application layer and expose them through the
  versioned agent protocol; the TUI must not independently infer recency or
  eligibility from history.
- Exclude a pair when its project or activity is archived. Collapse repeated
  completed entries for the same pair to the pair's most recent use.
- Present recent pairs as the quick switch deck with visible number shortcuts.
  Numbered or pointer selection highlights one pair, updates its pending action,
  and copies its project and activity into Manual entry while clearing its note,
  without changing timer state.
- Use a dedicated single-line optional note below the deck for the pending
  action. Confirm Start or Switch with `Enter` rather than a separate action
  button; never copy a historical note. After persistence, copy a non-empty note
  supplied for this quick switch into the Manual entry note field.
- Refresh recent pairs after connection, timer transitions, active-detail edits,
  archive, and restoration so visible choices reflect authoritative storage.
- When no eligible completed pair exists, show a concise empty state instead of
  a selectable recent item.

## Invariants and error handling

- Historical notes are never copied into either note input by recent-work
  selection or confirmation.
- Selecting a recent pair has no persistence side effects. Starting the selected
  work continues to use the existing validated and durable timer transition.
- If recent pairs cannot be loaded, retain the current capture inputs and report
  the agent error through the TUI's existing message area.

## Acceptance criteria

1. After opening the TUI with eligible history, a user can select a recent pair
   with `1` through `5` and confirm its pending Start or Switch with `Enter`.
2. Given repeated completed entries, each project/activity pair appears once at
   the position of its most recent completion, and no more than five pairs appear.
3. A pair whose project or activity is archived does not appear, including after
   an archive action in the connected TUI.
4. Selecting a recent pair highlights its canonical names, leaves capture inputs
   and the active timer unchanged, and describes the pending action. Confirming
   a current pair remains a no-op.
5. Unit, IPC integration, and Textual workflow tests cover projection ordering,
   deduplication, archive exclusion, protocol transport, selection, note handling,
   confirmation, current-pair rejection, and refresh behavior.

## Documentation impact

- Neither the top-level requirements nor the architecture changes. This feature
  implements the already-authorized fast keyboard workflow through the existing
  application, agent, and TUI boundaries and requires no schema migration.
