# TUI local time display

**Status:** Implemented

## Purpose

Keep read-only TUI timestamps compact and easy to scan without showing technical
UTC-offset suffixes that are unnecessary when the application already presents
times in the user's local time.

## Required behavior

- Render the active timer's local start as `YYYY-MM-DD HH:MM:SS`, without a UTC
  offset or time-zone label.
- Render the completed-entry deletion confirmation's local start as
  `YYYY-MM-DD HH:MM`, without a UTC offset or time-zone label.
- Keep correction and missed-time inputs offset-aware, because those editable
  values must continue to identify unambiguous instants. Keep exported timestamp
  formats unchanged.

## Invariants and error handling

- Presentation formatting does not change stored UTC instants, elapsed duration,
  local-time conversion, timer transitions, or deletion targets.
- Day-oriented Review rows retain their existing compact local-time display.

## Acceptance criteria

1. A running timer shows its local start through seconds without a UTC-offset
   suffix.
2. A deletion confirmation identifies the selected entry using its local start
   through minutes without a UTC-offset suffix.
3. Correction and missed-time fields still show and require explicit UTC offsets,
   and CSV exports remain offset-aware.
4. Textual workflow tests cover the timezone-free read-only displays.

## Documentation impact

- Neither the top-level requirements nor architecture changes. This feature only
  refines TUI presentation while preserving required offset-aware editing,
  persistence, and export behavior.
