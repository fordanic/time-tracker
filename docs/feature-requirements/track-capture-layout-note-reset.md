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
- Keep the normal capture note independent from the quick-switch note. Numbered
  or pointer recent-work selection copies project and activity into Manual entry
  and clears its note; changing deck selection clears the pending quick-switch
  note. After a quick-switch Start or Switch is persisted, copy its non-empty
  normalized note into Manual entry. Typing or correcting normal project/activity
  text does not clear its note.

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
3. Numbered or pointer recent-target selection copies its project and activity
   into Manual entry and clears both a prior pending deck note and the Manual
   entry note.
4. A successful quick-switch Start or Switch copies its non-empty persisted note
   into Manual entry before clearing the quick-switch note input.
5. Start, switch, restart, active-detail edit, and recovery preserve notes from
   their owning input.

## Documentation impact

- Neither top-level requirements nor architecture changes.
