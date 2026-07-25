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
- Clear the note only when the user explicitly selects a target from recent work
  or another selection control. Typing or correcting project/activity text does
  not clear it.

## Invariants and error handling

- Multiline notes follow the existing trim/empty normalization rules.
- Selecting a target never starts, switches, restarts, or edits a timer by
  itself.
- Responsive layout changes do not discard field values or change focus order.

## Acceptance criteria

1. Project and activity share a row at the normal supported width and stack at a
   defined narrow width.
2. The note editor shows two lines, accepts line breaks, and Tab advances focus.
3. Explicit recent-target selection clears the note, while typed target edits do
   not.
4. Start, switch, restart, active-detail edit, recovery, and CSV quoting preserve
   multiline notes.

## Documentation impact

- Neither top-level requirements nor architecture changes.
