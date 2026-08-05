# Prepare projects and activities

**Status:** Implemented

## Purpose

Let a user add a project or an activity ahead of time, from Manage, without
starting a timer or creating a time entry. Today a project or activity is only
ever created as a side effect of starting a timer, correcting an entry,
creating a manual missed-time entry, or editing an active entry's detail. This
feature adds a direct, explicit way to prepare names for later use.

## Required behavior

- Manage offers a "New project" input and an "Add project" action that
  creates a project with no activities.
- Manage offers a "New activity" project input (with the same typeahead
  suggestions of active projects used elsewhere in the TUI) and activity-name
  input, plus an "Add activity" action that creates an activity under an
  existing, non-archived project.
- On success, both actions report the canonical created name(s), clear the
  relevant input(s), and refresh Manage's active tree and every project/activity
  suggestion source in the same way a successful archive or restore does.
- Creating a project or activity does not affect the active timer, completed
  entries, or any other project or activity.

## Invariants and error handling

- Create a project or activity through an agent-owned application use case and
  one SQLite transaction, exposed over the versioned protocol, exactly like
  archive and restore. The TUI does not infer canonical identity.
- Project and activity name matching is case-insensitive after trimming, the
  same as every other lookup in the product.
- Creating a project is rejected if a project with that name already exists,
  active or archived: `project already exists: <name>`. This is a distinct,
  explicit action, not the implicit get-or-create used by timer start, manual
  entry, correction, and active-detail editing, which is unchanged.
- Creating an activity is rejected if:
  - its project does not exist: `project not found: <project>`;
  - its project exists but is archived: `project is archived: <project>`; or
  - an activity with that name already exists under that project, active or
    archived: `activity already exists: <project>/<activity>`.
- Creating an activity never creates its parent project. The two actions are
  independent; a project must already exist and be selectable before an
  activity can be prepared under it.
- A rejected create leaves stored state, the active timer, and any pending
  Manage confirmation unchanged, and reports a concise error in the persistent
  TUI message area.

## Acceptance criteria

1. Creating a project that does not yet exist succeeds, and the project
   immediately appears in Manage's active tree and in every project suggestion
   list without restarting the TUI.
2. Creating a project whose name already exists, in any case and in either
   archive state, is rejected without creating a duplicate or archived-state
   change.
3. Creating an activity under an existing, non-archived project succeeds and
   immediately appears under that project in Manage's active tree and in
   activity suggestions for that project.
4. Creating an activity under a project that does not exist, or that is
   archived, is rejected with a message naming the problem; no activity is
   created.
5. Creating an activity whose name already exists under its project, in either
   archive state, is rejected without creating a duplicate.
6. Unit, SQLite integration, IPC integration, and Textual workflow tests cover
   every success and rejection path above, including case-insensitive
   duplicate detection and that a rejected create leaves the active timer and
   existing data untouched.

## Documentation impact

- No top-level requirement changes: "Create and list projects and their
  activities" already authorizes this behavior, previously only reachable
  implicitly.
- Architecture records the new agent-owned use cases, their one-transaction
  SQLite writes, and the accompanying protocol version bump.
