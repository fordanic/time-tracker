# Track capture layout and note reset

**Status:** Implemented

## Purpose

Use horizontal space efficiently, support short multiline notes, and prevent a
note from an earlier target being unintentionally carried to an explicitly
selected target.

## Required behavior

- Place project and activity inputs on one row when space permits and stack them
  in narrow terminals.
- Use a two-line multiline note editor with soft wrapping and normal Tab focus
  traversal.
- Preserve line breaks as plain-text note content.
- Keep the normal capture note independent from the quick-switch note. Selecting
  recent work does not change normal capture values; changing deck selection
  clears only the pending quick-switch note. Typing or correcting normal
  project/activity text does not clear its note.

## Invariants and error handling

- Multiline notes follow the existing trim/empty normalization rules.
- Selecting a target never starts, switches, restarts, or edits a timer by
  itself.
- Responsive layout changes do not discard field values or change focus order.

## Acceptance criteria

1. Project and activity share a row at the normal supported width and stack at a
   defined narrow width.
2. The note editor shows two lines, accepts line breaks, and Tab advances focus.
3. Explicit recent-target selection clears only a prior pending deck note, while
   normal capture values and their note remain unchanged.
4. Start, switch, restart, active-detail edit, recovery, and CSV quoting preserve
   multiline notes.

## Documentation impact

- Neither top-level requirements nor architecture changes.
