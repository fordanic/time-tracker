# TUI active timer layout

**Status:** Implemented

## Purpose

Give the running timer a clearer visual hierarchy in the TUI, consistent with
the established web interface, so the current work and elapsed time can be read
at a glance.

## Required behavior

- Present the active timer as a two-column strip: project/activity and optional
  note on the left, with the live elapsed clock on the right.
- Make project/activity visually prominent and left-aligned. Show the optional
  note beneath it; when no note exists, show a subdued `No note` state.
- Render the elapsed duration as a large terminal-native clock aligned to the
  right. Show the timezone-free local start timestamp beneath the clock.
- Keep the active-timer strip visible and updating once per second in every TUI
  view, as it is today. When no timer is active, retain a concise ready state and
  hide the elapsed/start panel.

## Invariants and error handling

- Layout and typography do not change timer persistence, elapsed-time
  calculation, reminder scheduling, controls, shortcuts, or focus order.
- The strip remains usable in supported terminal widths and under every built-in
  Textual palette without hard-coded colors.
- Project, activity, and note content is rendered as text rather than markup.

## Acceptance criteria

1. A running timer shows prominent left-aligned project/activity text, its note
   beneath, and a larger right-aligned `HH:MM:SS` elapsed clock.
2. The local `Started YYYY-MM-DD HH:MM:SS` value appears beneath the elapsed
   clock without a UTC-offset suffix.
3. A timer without a note shows `No note`, and an inactive timer does not show a
   stale elapsed clock or start timestamp.
4. The active strip remains visible across Track, Review, Manage, and Settings,
   and Textual workflow tests cover its content, alignment, and live state.

## Documentation impact

- Neither the top-level requirements nor architecture changes. This is a TUI
  presentation refinement within the existing timer and interface boundaries.
