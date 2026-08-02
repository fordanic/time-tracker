# Track capture layout and note reset

**Status:** Implemented

## Purpose

Use horizontal space efficiently and prevent a note from one timer workflow from
being unintentionally carried into another.

## Required behavior

- Place project and activity inputs on one row when space permits and stack them
  in narrow terminals.
- Use separate single-line optional-note inputs for Quick switch and Manual
  entry, with normal Tab focus traversal.
- Keep the normal capture note independent from the quick-switch note. Selecting
  recent work does not change normal capture values; changing deck selection
  clears only the pending quick-switch note. Typing or correcting normal
  project/activity text does not clear its note.

## Invariants and error handling

- Both note inputs follow the existing trim/empty normalization rules.
- Selecting a target never starts, switches, restarts, or edits a timer by
  itself.
- Responsive layout changes do not discard field values or change focus order.

## Acceptance criteria

1. Project and activity share a row at the normal supported width and stack at a
   defined narrow width.
2. Quick switch and Manual entry each have one single-line optional-note input,
   and Tab advances focus normally.
3. Explicit recent-target selection clears only a prior pending deck note, while
   normal capture values and their note remain unchanged.
4. Start, switch, restart, active-detail edit, and recovery preserve notes from
   their owning input.

## Documentation impact

- Neither top-level requirements nor architecture changes.
