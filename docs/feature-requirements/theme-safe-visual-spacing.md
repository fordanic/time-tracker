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

## Documentation impact

- Neither top-level requirements nor architecture changes.
