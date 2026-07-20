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
