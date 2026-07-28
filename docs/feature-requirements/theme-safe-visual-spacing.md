# Theme-safe visual spacing

**Status:** Implemented

## Purpose

Improve form readability and ensure application styling remains legible across
Textual themes.

## Required behavior

- Remove unintended colored gutters between vertically stacked inputs while
  retaining clear field boundaries.
- Increase vertical separation between Settings rows.
- Vertically center Settings input text without clipping borders or focus state.
- Use semantic Textual theme variables for foreground, background, status, focus,
  and selection colors instead of component-specific literal colors.
- Render an inactive button as a flat surface control with full text opacity
  instead of dimming its label against a saturated variant background, so labels
  such as an inactive Start action stay readable.

## Invariants and error handling

- Layout remains scrollable in short terminals and usable in narrow terminals.
- Styling does not change business behavior, focus order, or enabled state.
- Success and error messages remain distinguishable and legible in both light
  and dark built-in themes.

## Acceptance criteria

1. Settings rows have consistent vertical rhythm and centered input content.
2. Stacked inputs use the parent background between controls.
3. Light and dark theme tests verify readable messages, focus, selection, and
   reminder state without hard-coded palette values.
4. Inactive buttons keep a contrast ratio of at least 4.5:1 in every built-in
   palette that defines concrete colors, and become inactive without changing
   their size.

## Documentation impact

- Neither top-level requirements nor architecture changes.
