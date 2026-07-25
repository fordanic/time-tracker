# Review selection and action layout

**Status:** Implemented

## Purpose

Make Review filtering and entry actions easier to understand and operate without
typing known project and activity names.

## Required behavior

- Replace Review's project and activity free-text filters with Select controls.
- Include explicit all-projects and all-activities options.
- Populate projects from completed history, including archived historical names,
  and limit activity choices to the selected project when one is selected.
- Place Load selected entry and Add missed entry directly below the history
  table, aligned to the left.
- Left-align Daily summaries and Range totals with visible spacing between them.

## Invariants and error handling

- Date, project, and activity filtering remains case-insensitive and shared by
  detail, summaries, totals, and export.
- Refreshing history preserves a still-valid selection and otherwise falls back
  to the corresponding unfiltered option.
- Summary modes retain their existing mutual exclusion and continue disabling
  completed-entry editing.

## Acceptance criteria

1. A user can select unfiltered, active, or archived historical targets without
   entering free text.
2. Selecting a project updates the activity choices and rendered results.
3. Entry buttons appear below the table and summary switches are left-aligned
   with separation at supported widths.
4. Textual tests cover selection, refresh, archived choices, layout order,
   summary interaction, and export consistency.

## Documentation impact

- Neither top-level requirements nor architecture changes.
