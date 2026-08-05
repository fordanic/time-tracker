# Feature Requirements

This directory records additional feature requirements selected for
implementation. Each approved requirement has its own file so its behavior,
invariants, acceptance criteria, status, and documentation impact can evolve
together.

Feature requirements are subordinate to the
[Top-level requirements](../top-level-requirements.md) and
[Architecture](../architecture.md), which are the authoritative product and
technical documents. A feature requirement cannot override either one. A change
to a durable product rule, quality constraint, product boundary, technical
choice, or architectural boundary requires specific approval and an update to
the corresponding authoritative document first or in the same change. The
approval must come from a repository maintainer and be recorded in the change
review.

The [competitive assessment and TUI roadmap](../competitive-assessment.md) is
planning input. A candidate belongs in this directory only after it has been
selected for implementation. It becomes approved when a repository maintainer
accepts a requirement file whose status is `Approved`.

Current implementation and validation results, including outstanding platform
checks, are recorded in the root [README Status](../../README.md#status).

## Requirements workflow

For each selected feature:

1. Create or update one requirement file in this directory before
   implementation.
2. Define its user-visible behavior, invariants, error handling, acceptance
   criteria, status, and documentation impact.
3. Obtain approval and add the requirement to the index below.
4. Update the
   [top-level requirements](../top-level-requirements.md) first or in the same
   change if the feature changes a durable product rule, quality constraint, or
   product boundary.
5. Update [architecture](../architecture.md) first or in the same change if the
   feature changes a technical choice or boundary.
6. Implement and test the feature against the approved requirement.

## Approved feature requirements

- [Recent activities / Track again](recent-activities-track-again.md)
- [Quick switch deck](quick-switch-deck.md)
- [Explicit Start, Switch, and Restart actions](explicit-start-switch-restart-actions.md)
- [Focused Track, Review, Manage, and Settings views](focused-track-review-manage-settings-views.md)
- [Completed-entry correction](completed-entry-correction.md)
- [Manual missed-time entry](manual-missed-time-entry.md)
- [Active-entry detail editing](active-entry-detail-editing.md)
- [Safe and reversible archive management](safe-reversible-archive-management.md)
- [Day-oriented Review and today's completed total](day-oriented-review-todays-completed-total.md)
- [Shared Review filters and range summaries](shared-review-filters-range-summaries.md)
- [TUI-managed reminder settings and live reload](tui-managed-reminder-settings-live-reload.md)
- [Reminder windows and snooze](reminder-windows-snooze.md)
- [Opt-in idle-triggered active reminder](opt-in-idle-triggered-active-reminder.md)
- [Responsive shortcut discovery](responsive-shortcut-discovery.md)
- [Hierarchical project and activity management](hierarchical-project-activity-management.md)
- [Review selection and action layout](review-selection-action-layout.md)
- [Track capture layout and note reset](track-capture-layout-note-reset.md)
- [Theme-safe visual spacing](theme-safe-visual-spacing.md)
- [Persistent theme and export preferences](persistent-theme-export-preferences.md)
- [Versioned release candidates and releases](versioned-release-candidates-releases.md)
- [Prepare projects and activities](prepare-projects-and-activities.md)
- [WSL notification delivery to the Windows desktop](wsl-windows-desktop-notifications.md)
- [Simulated test data](simulated-test-data.md)

## Feature specification template

Create a new file named after the feature, then use this structure. Replace the
placeholders rather than treating the template as an approved requirement.

```markdown
# Feature name

**Status:** Approved | Implemented

## Purpose

State the user problem and intended outcome.

## Required behavior

- Describe observable behavior and supported TUI interactions.

## Invariants and error handling

- Describe rules that must always hold and how rejected actions are reported.

## Acceptance criteria

1. State a verifiable outcome.

## Documentation impact

- Note any corresponding change to the top-level requirements or architecture,
  or state that neither authoritative document changes.
```
