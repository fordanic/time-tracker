# Explicit Start, Switch, and Restart actions

**Status:** Implemented

## Purpose

Make the primary timer action describe its effect before the user invokes it and
prevent an unchanged selection from silently fragmenting tracked time.

## Required behavior

- Classify the current capture selection in the application layer and expose the
  classification through the versioned agent protocol.
- Show `Start` when no timer is active.
- Show `Switch from <current> to <selected>` when a timer is active and the
  selected project/activity pair differs from it.
- Show `Already tracking` and disable the primary action when the active and
  selected project/activity pair and normalized note are unchanged.
- Show `Restart with new note` when the selected pair matches the active pair but
  its normalized note differs.
- On TUI recovery, populate the project, activity, and note inputs from the
  active entry so its initial action state is accurate.
- Continue to use `F5` for every enabled primary action. Pointer and keyboard
  invocation must apply the same application use case.

## Invariants and error handling

- Trim project and activity names and compare existing names case-insensitively
  when classifying a pair. Normalize a note by trimming it and treating an empty
  value as no note; compare non-empty note text case-sensitively.
- A switch or restart closes the active entry and creates its replacement at one
  captured UTC timestamp in the existing repository transaction. A restart keeps
  the same canonical project/activity pair and uses the newly normalized note.
- An unchanged pair and normalized note is rejected in the application layer. It
  must not call the persistence transition, capture a clock instant, replace the
  active entry, add history, or reset reminder scheduling.
- Required-name and archived-target validation continues to use the existing
  application and repository rules. A rejected action leaves the active entry
  unchanged and is reported through the TUI's existing message area.
- If action classification cannot be loaded, report the agent error and disable
  the primary action until a later field or timer refresh succeeds.

## Acceptance criteria

1. With no active timer, the primary action says `Start` and persists a valid
   selected timer.
2. With an active timer and a different selected pair, the primary action names
   the current and selected pairs; invoking it creates adjacent, non-overlapping
   entries at one transition timestamp.
3. With the same pair and normalized note, the primary action says
   `Already tracking`, is disabled for pointer and `F5` use, and a direct agent
   request is rejected without changing the active entry or history.
4. With the same pair and a different normalized note, the primary action says
   `Restart with new note`; invoking it closes the current entry and starts a new
   same-pair entry with the new note at the identical transition timestamp.
5. Reconnecting to an active timer restores its canonical project, activity, and
   note into the inputs and initially shows `Already tracking`.
6. Unit, IPC integration, SQLite transition, and Textual workflow tests cover all
   four classifications, normalization, no-op protection, recovery, and the
   adjacency of switch and restart transitions.

## Documentation impact

- The top-level tracking rules now define same-pair restart and unchanged no-op
  behavior, resolving the corresponding open product decision. Architecture now
  records application-layer no-op rejection and the shared transactional boundary
  for switch and restart. No schema migration is required.
