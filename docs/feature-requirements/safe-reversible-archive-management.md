# Safe and reversible archive management

**Status:** Implemented

## Purpose

Prevent accidental archive actions and let a user restore projects or activities
that were archived by mistake without editing SQLite or losing hierarchy state.

## Required behavior

- Keep project and activity archive actions in Manage and require two explicit
  invocations: the first validates and displays the exact canonical target, and
  the second archives that unchanged target. The confirmation message must state
  that an active timer will continue.
- Track separate in-memory project and activity confirmations. Bind each to the
  trimmed input snapshot and canonical target returned by the first invocation.
  A changed project input clears both confirmations; a changed activity input
  clears the activity confirmation. Whitespace-only edits that preserve the
  trimmed snapshot do not cancel confirmation.
- Preserve a pending confirmation across view changes in the same TUI session.
  Do not persist it across TUI restart. Clear it after a validation failure or
  after the second, mutating invocation succeeds or fails.
- On the second invocation, resolve the inputs again through the application and
  archive only if both the trimmed snapshot and canonical target still match the
  pending confirmation. A validation or persistence failure must not archive a
  different target.
- List archived projects and archived activities in Manage using canonical names.
  The activity list contains activities whose own archive flag is set, not every
  activity made temporarily unselectable by an archived parent. Each archived
  activity is shown with its parent project and indicates when that project is
  also archived. Show a concise empty state for each list when it has no items.
- Let the user restore a selected archived project or activity. Refresh archived
  lists, selectable suggestions, recent activities, and affected Manage inputs
  after every successful archive or restore.
- Archiving or restoring a project changes only the project's archive state; it
  does not rewrite the independent archive state of any child activity.
- Restoring a project makes its non-archived activities selectable immediately.
  An activity that was archived separately remains archived until explicitly
  restored.
- Reject restoration of an activity while its parent project is archived and
  tell the user to restore the project first.
- After project archive, clear both Manage inputs. After activity archive, retain
  the canonical project and clear the activity. After project restore, put the
  canonical project in its input and clear the activity. After activity restore,
  put both canonical names in their inputs.

## Invariants and error handling

- Resolve confirmation targets and perform archive and restore mutations through
  application use cases exposed by the versioned agent protocol. The TUI must not
  infer canonical identity or hierarchy eligibility from display text.
- Project and activity lookup trims input and matches existing names
  case-insensitively. Archive requires an existing non-archived target; restore
  requires an existing archived target.
- Archive and restore update only the relevant `archived_at` value in one
  background-process-owned SQLite transaction. They never delete or rename a
  project, activity, or entry and never stop, restart, or edit an active timer.
- Archived names remain reserved throughout archive and restore transitions.
- Unknown targets, already-archived archive targets, non-archived restore targets,
  and activity restoration beneath an archived project are rejected with a
  concise error in the persistent TUI message area. A rejection leaves stored
  state and the active timer unchanged.

## Acceptance criteria

1. The first project or activity archive invocation names the canonical target,
   performs no write, and warns that an active timer continues; a second
   invocation with unchanged inputs performs the archive.
2. Editing either relevant input cancels its pending confirmation, so a later
   invocation validates the newly entered normalized target instead of archiving
   the prior one. Whitespace-only edits that retain the same trimmed input do not
   cancel it.
3. Manage lists canonical archived projects and project/activity pairs after TUI
   launch and refreshes both lists immediately after archive or restore.
4. Restoring a project preserves every child activity archive flag and makes only
   its non-archived activities selectable. Restoring an eligible activity makes
   that activity selectable without changing its parent or siblings.
5. Restoring an activity beneath an archived project is rejected until the
   project is restored; no partial state change occurs.
6. Archive and restore preserve active and completed entries, keep active elapsed
   time running, and update suggestions and recent-work eligibility from
   authoritative storage.
7. Unit, SQLite integration, IPC integration, and Textual workflow tests cover
   confirmation and cancellation, canonical lookup, archived listings, hierarchy
   rules, successful restore, rejected restore, refresh behavior, and active-timer
   preservation.
8. Tests also cover empty archived lists, canonical parent display for an archived
   activity, unknown/already-archived/non-archived rejection, archived-name
   reservation, and confirmation clearing after a failed or successful mutation.

## Documentation impact

- Top-level requirements now define archive restoration and its hierarchy rules.
  Architecture records the application/protocol boundary and transactional flag
  updates. The existing nullable archive columns support this feature, so no
  schema migration is required.
