# Responsive shortcut discovery

**Status:** Implemented

## Purpose

Keep keyboard actions discoverable without overflowing the bottom row in narrow
terminals, while retaining the existing F-key accelerators.

## Required behavior

- Retain F1 through F12 with their existing actions.
- Use `Ctrl+K` for the complete shortcut overlay and `Ctrl+C` to quit; avoid
  terminal flow-control and bell combinations such as `Ctrl+Q` and `Ctrl+G`.
- Replace the always-expanded global shortcut row with a compact,
  context-relevant summary for the selected view.
- Keep an always-visible shortcut-help action at the start of the summary and
  present every binding in a dedicated overlay.
- Include reminder actions in the compact summary only while a reminder is
  pending.

## Invariants and error handling

- Hiding a binding from the compact row does not disable it.
- The shortcut overlay is read-only, keyboard dismissible, and does not mutate or
  clear any workflow state.
- At narrow widths the shortcut-help action remains visible even when later
  context actions are clipped.

## Acceptance criteria

1. F1 through F12 retain their documented actions.
2. Track, Review, Manage, and Settings show only their relevant action summary.
3. Shortcut help lists all view, timer, reminder, archive, export, update, and
   quit bindings and can be opened and closed without changing app state.
4. A narrow-terminal Textual test verifies that shortcut help remains
   discoverable and the full global binding list is not rendered in the footer.

## Documentation impact

- Neither top-level requirements nor architecture changes. This refines the TUI
  presentation of existing keyboard behavior.
