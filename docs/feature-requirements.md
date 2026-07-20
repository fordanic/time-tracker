# Feature Requirements

This document records additional feature requirements that have been selected
for implementation. It is subordinate to
[Top-Level Requirements](top-level-requirements.md) and
[Architecture](architecture.md), which are the authoritative product and technical
documents. A feature requirement must conform to both and cannot override either
one.

The [competitive assessment and TUI roadmap](competitive-assessment.md) is
planning input. A candidate from that assessment belongs here only after it has
been selected for implementation.

## Requirements workflow

For each selected feature:

1. Define its user-visible behavior, invariants, error handling, and acceptance
   criteria in this document before implementation.
2. Update [Top-Level Requirements](top-level-requirements.md) first, or in the
   same change, if the feature changes a durable product rule, quality constraint,
   or product boundary.
3. Update [Architecture](architecture.md) first, or in the same change, if the
   feature changes a technical choice or boundary.
4. Implement and test the feature against the approved requirements.

## Approved feature requirements

### Recent activities / Track again

**Status:** Implemented

#### Purpose

Let a user resume common work without retyping a project and activity after the
TUI opens, while keeping the user in control of the new timer and its note.

#### Required behavior

- Show up to five unique project/activity pairs in the Track workflow, ordered
  by most recently completed use.
- Derive recent pairs in the application layer and expose them through the
  versioned agent protocol; the TUI must not independently infer recency or
  eligibility from history.
- Exclude a pair when its project or activity is archived. Collapse repeated
  completed entries for the same pair to the pair's most recent use.
- Selecting a recent pair populates the project and activity inputs, clears the
  note input, and focuses the note input. It does not start or switch a timer.
- Refresh recent pairs after a timer is stopped and after a project or activity
  is archived so the visible choices reflect authoritative storage.
- When no eligible completed pair exists, show a concise empty state instead of
  a selectable recent item.

#### Invariants and error handling

- Historical notes are never copied into the note input by the recent-work
  action.
- Selecting a recent pair has no persistence side effects. Starting the selected
  work continues to use the existing validated and durable timer transition.
- If recent pairs cannot be loaded, retain the current capture inputs and report
  the agent error through the TUI's existing message area.

#### Acceptance criteria

1. After opening the TUI with eligible history, a user can select a recent pair
   and start it with two actions.
2. Given repeated completed entries, each project/activity pair appears once at
   the position of its most recent completion, and no more than five pairs appear.
3. A pair whose project or activity is archived does not appear, including after
   an archive action in the connected TUI.
4. Selecting a recent pair replaces the project and activity inputs with their
   canonical names, clears any note text, focuses the note input, and leaves the
   active timer unchanged until Start is invoked.
5. Unit, IPC integration, and Textual workflow tests cover projection ordering,
   deduplication, archive exclusion, protocol transport, selection, note clearing,
   and refresh after stop.

#### Documentation impact

- Neither the top-level requirements nor the architecture changes. This feature
  implements the already-authorized fast keyboard workflow through the existing
  application, agent, and TUI boundaries and requires no schema migration.

### Explicit Start, Switch, and Restart actions

**Status:** Implemented

#### Purpose

Make the primary timer action describe its effect before the user invokes it and
prevent an unchanged selection from silently fragmenting tracked time.

#### Required behavior

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

#### Invariants and error handling

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

#### Acceptance criteria

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

#### Documentation impact

- The top-level tracking rules now define same-pair restart and unchanged no-op
  behavior, resolving the corresponding open product decision. Architecture now
  records application-layer no-op rejection and the shared transactional boundary
  for switch and restart. No schema migration is required.

## Feature specification template

Use this structure when a feature is selected. Replace the placeholder rather
than treating the template as an approved requirement.

### Feature name

**Status:** Approved | Implemented

#### Purpose

State the user problem and intended outcome.

#### Required behavior

- Describe observable behavior and supported TUI interactions.

#### Invariants and error handling

- Describe rules that must always hold and how rejected actions are reported.

#### Acceptance criteria

1. State a verifiable outcome.

#### Documentation impact

- Note any corresponding change to the top-level requirements or architecture,
  or state that neither authoritative document changes.
