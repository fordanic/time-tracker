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
- Render correction and missed-time start/stop fields as timezone-free local
  `YYYY-MM-DD HH:MM:SS` wall-clock values. Resolve changed values through the
  system local time zone and reject ambiguous or nonexistent local times. Keep
  exported timestamp formats unchanged.

## Invariants and error handling

- Presentation formatting does not change stored UTC instants, elapsed duration,
  local-time conversion, timer transitions, or deletion targets.
- Day-oriented Review rows retain their existing compact local-time display.

## Acceptance criteria

1. A running timer shows its local start through seconds without a UTC-offset
   suffix.
2. A deletion confirmation identifies the selected entry using its local start
   through minutes without a UTC-offset suffix.
3. Correction and missed-time fields omit UTC offsets, changed values resolve to
   unambiguous local instants, and CSV exports remain offset-aware.
4. Textual workflow tests cover the timezone-free read-only displays.

## Documentation impact

- Top-level requirements now permit interfaces to resolve timezone-free local
  wall-clock input while rejecting ambiguous or nonexistent times. Architecture
  records the TUI-owned local-time resolution boundary; persistence is unchanged.
