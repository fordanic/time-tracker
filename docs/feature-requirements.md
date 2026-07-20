# Feature Requirements

This document records additional feature requirements that have been selected
for implementation. It is subordinate to
[Top-Level Requirements](top-level-requirements.md) and
[Architecture](architecture.md), which are the authoritative product and technical
documents. A feature requirement must conform to both and cannot override either
one.

The [competitive assessment and TUI roadmap](competitive-assessment.md) is
planning input. A candidate from that assessment belongs here only after it has
been selected for implementation.

## Requirements workflow

For each selected feature:

1. Define its user-visible behavior, invariants, error handling, and acceptance
   criteria in this document before implementation.
2. Update [Top-Level Requirements](top-level-requirements.md) first, or in the
   same change, if the feature changes a durable product rule, quality constraint,
   or product boundary.
3. Update [Architecture](architecture.md) first, or in the same change, if the
   feature changes a technical choice or boundary.
4. Implement and test the feature against the approved requirements.

## Approved feature requirements

### Recent activities / Track again

**Status:** Implemented

#### Purpose

Let a user resume common work without retyping a project and activity after the
TUI opens, while keeping the user in control of the new timer and its note.

#### Required behavior

- Show up to five unique project/activity pairs in the Track workflow, ordered
  by most recently completed use.
- Derive recent pairs in the application layer and expose them through the
  versioned agent protocol; the TUI must not independently infer recency or
  eligibility from history.
- Exclude a pair when its project or activity is archived. Collapse repeated
  completed entries for the same pair to the pair's most recent use.
- Selecting a recent pair populates the project and activity inputs, clears the
  note input, and focuses the note input. It does not start or switch a timer.
- Refresh recent pairs after a timer is stopped and after a project or activity
  is archived so the visible choices reflect authoritative storage.
- When no eligible completed pair exists, show a concise empty state instead of
  a selectable recent item.

#### Invariants and error handling

- Historical notes are never copied into the note input by the recent-work
  action.
- Selecting a recent pair has no persistence side effects. Starting the selected
  work continues to use the existing validated and durable timer transition.
- If recent pairs cannot be loaded, retain the current capture inputs and report
  the agent error through the TUI's existing message area.

#### Acceptance criteria

1. After opening the TUI with eligible history, a user can select a recent pair
   and start it with two actions.
2. Given repeated completed entries, each project/activity pair appears once at
   the position of its most recent completion, and no more than five pairs appear.
3. A pair whose project or activity is archived does not appear, including after
   an archive action in the connected TUI.
4. Selecting a recent pair replaces the project and activity inputs with their
   canonical names, clears any note text, focuses the note input, and leaves the
   active timer unchanged until Start is invoked.
5. Unit, IPC integration, and Textual workflow tests cover projection ordering,
   deduplication, archive exclusion, protocol transport, selection, note clearing,
   and refresh after stop.

#### Documentation impact

- Neither the top-level requirements nor the architecture changes. This feature
  implements the already-authorized fast keyboard workflow through the existing
  application, agent, and TUI boundaries and requires no schema migration.

### Explicit Start, Switch, and Restart actions

**Status:** Implemented

#### Purpose

Make the primary timer action describe its effect before the user invokes it and
prevent an unchanged selection from silently fragmenting tracked time.

#### Required behavior

- Classify the current capture selection in the application layer and expose the
  classification through the versioned agent protocol.
- Show `Start` when no timer is active.
- Show `Switch from <current> to <selected>` when a timer is active and the
  selected project/activity pair differs from it.
- Show `Already tracking` and disable the primary action when the active and
  selected project/activity pair and normalized note are unchanged.
- Show `Restart with new note` when the selected pair matches the active pair but
  its normalized note differs.
- On TUI recovery, populate the project, activity, and note inputs from the
  active entry so its initial action state is accurate.
- Continue to use `F5` for every enabled primary action. Pointer and keyboard
  invocation must apply the same application use case.

#### Invariants and error handling

- Trim project and activity names and compare existing names case-insensitively
  when classifying a pair. Normalize a note by trimming it and treating an empty
  value as no note; compare non-empty note text case-sensitively.
- A switch or restart closes the active entry and creates its replacement at one
  captured UTC timestamp in the existing repository transaction. A restart keeps
  the same canonical project/activity pair and uses the newly normalized note.
- An unchanged pair and normalized note is rejected in the application layer. It
  must not call the persistence transition, capture a clock instant, replace the
  active entry, add history, or reset reminder scheduling.
- Required-name and archived-target validation continues to use the existing
  application and repository rules. A rejected action leaves the active entry
  unchanged and is reported through the TUI's existing message area.
- If action classification cannot be loaded, report the agent error and disable
  the primary action until a later field or timer refresh succeeds.

#### Acceptance criteria

1. With no active timer, the primary action says `Start` and persists a valid
   selected timer.
2. With an active timer and a different selected pair, the primary action names
   the current and selected pairs; invoking it creates adjacent, non-overlapping
   entries at one transition timestamp.
3. With the same pair and normalized note, the primary action says
   `Already tracking`, is disabled for pointer and `F5` use, and a direct agent
   request is rejected without changing the active entry or history.
4. With the same pair and a different normalized note, the primary action says
   `Restart with new note`; invoking it closes the current entry and starts a new
   same-pair entry with the new note at the identical transition timestamp.
5. Reconnecting to an active timer restores its canonical project, activity, and
   note into the inputs and initially shows `Already tracking`.
6. Unit, IPC integration, SQLite transition, and Textual workflow tests cover all
   four classifications, normalization, no-op protection, recovery, and the
   adjacency of switch and restart transitions.

#### Documentation impact

- The top-level tracking rules now define same-pair restart and unchanged no-op
  behavior, resolving the corresponding open product decision. Architecture now
  records application-layer no-op rejection and the shared transactional boundary
  for switch and restart. No schema migration is required.

### Focused Track, Review, Manage, and Settings views

**Status:** Implemented

#### Purpose

Separate everyday capture, historical review, archive management, and settings
information so later correction and reporting controls do not make one screen
progressively denser, while keeping the current timer continuously visible.

#### Required behavior

- Provide four pointer- and keyboard-addressable views in this order: **Track**,
  **Review**, **Manage**, and **Settings**. Use `F1` through `F4` respectively and
  show those shortcuts in the view selector and in-app shortcut help.
- Keep the active-timer strip, its live elapsed duration, pending reminder prompt,
  and shared success/error message visible while any view is selected.
- Put project/activity/note capture, recent activities, and Start/Stop controls in
  Track.
- Put completed-entry and daily-summary review, CSV destination, and export
  controls in Review. Preserve the current selected representation and pending
  overwrite confirmation when another view is visited.
- Put the existing project and activity archive controls in Manage, with dedicated
  project and activity inputs and the same case-insensitive suggestions and
  application validation used by the existing archive actions. The later
  reversible-archive slice will add confirmation, archived-item listing, and
  unarchive to this view.
- Give Settings a concise read-only explanation of the current TOML-managed
  reminder configuration and restart requirement. Editing and live reload remain
  part of the later TUI-managed-settings slice.
- Retain `F5` through `F10` for timer action, stop, export, project archive,
  activity archive, and active-reminder confirmation. These actions must continue
  to use their owning view's inputs even when another view is selected.
- Start in Track on every TUI launch. Switching views by pointer or shortcut must
  select the same content and place focus on that view's first primary control.

#### Invariants and error handling

- Switching views is presentation-only: it must not make an agent request, mutate
  persisted data, change the active timer, clear capture or export fields, or
  dismiss a reminder or message.
- Timer, review, export, and archive behavior continues to use the existing agent
  and application boundaries; the view scaffold introduces no duplicated
  business rules and no direct storage access.
- An unavailable action is reported through the persistent message area and does
  not force a view change or discard values in another view.
- The active-timer strip continues updating once per second regardless of the
  selected view, and Stop remains disabled when no timer is active.

#### Acceptance criteria

1. On launch, Track is selected and only its view-specific controls are visible;
   `F1` through `F4` and pointer selection each activate the corresponding view.
2. A running timer's project, activity, start time, note, and increasing elapsed
   duration remain visible in Track, Review, Manage, and Settings.
3. Existing capture/recent-work behavior operates in Track, history/summary/export
   behavior operates in Review, and project/activity archiving operates from the
   dedicated Manage inputs.
4. View changes preserve capture values, review mode, export path and overwrite
   confirmation, Manage selections, the current message, and pending reminders.
5. Existing `F5` through `F10` shortcuts retain their actions, including when the
   corresponding controls are outside the selected view.
6. Textual workflow tests cover initial selection, pointer and keyboard view
   navigation, focus, control ownership, persistent timer visibility, state
   preservation, and retained action shortcuts.

#### Documentation impact

- Neither the top-level requirements nor the architecture changes. This is a TUI
  presentation restructure within the existing interface and agent boundary and
  requires no protocol or schema migration.

### Completed-entry correction

**Status:** Implemented

#### Purpose

Let a user repair an inaccurate completed timer inside the product without
discarding the entry or editing SQLite directly. This is the first ordered slice
of the roadmap's correction and missed-time workflow; manual closed-entry creation
and active-entry editing remain later slices.

#### Required behavior

- In Review's completed-entry mode, let the user load the selected completed row
  into correction fields for project, activity, note, start, and stop, then save
  the corrected entry through the background process.
- Populate start and stop as local, offset-aware ISO 8601 timestamps. Accept only
  offset-aware ISO 8601 input so each edited value maps to one unambiguous UTC
  instant, including during daylight-saving transitions.
- Trim project and activity names and normalize the note by trimming it and
  treating an empty value as no note, consistently with timer capture.
- When the project/activity assignment changes, reuse a matching selectable target
  case-insensitively or create a new project/activity using the timer-start naming
  rules. Reject reassignment to an archived project or activity.
- When the assignment is unchanged, allow correction of only time or note while
  retaining the historical target even if it has since been archived.
- After a successful correction, refresh completed history, daily summaries,
  recent activities, and selectable project suggestions, keep the corrected row
  selected when possible, and show the canonical persisted values.
- Correction is unavailable in daily-summary mode and when no completed row is
  selected.

#### Invariants and error handling

- Stop must be strictly after start.
- Completed and active entries use half-open intervals: `[start, stop)`. A
  correction must not overlap any other entry, including the active entry, but may
  touch another entry's start or stop. The entry being corrected is excluded from
  its own overlap check.
- Target resolution, overlap validation, and the update occur in one SQLite
  transaction owned by the background process. The original entry remains
  unchanged if any validation or persistence step fails, and success is reported
  only after commit.
- The entry identifier and original creation timestamp do not change. Duration
  remains derived from corrected timestamps; no revision history or undo record is
  added in this slice.
- Reject an unknown entry, invalid or offset-free timestamp, non-positive interval,
  archived reassignment, or overlap with a concise error in the persistent TUI
  message area. A rejection leaves the correction fields available for repair.

#### Acceptance criteria

1. A user can select one completed entry in Review, load its canonical values,
   change all five editable fields, save, and immediately see the corrected row.
2. Offset-aware input is converted to UTC before persistence and re-rendered in
   the user's local offset; offset-free or malformed input is rejected without
   changing history.
3. Saving with stop equal to or before start is rejected. Saving an interval that
   intersects another completed or active entry is rejected, while an interval
   that only touches a neighboring boundary succeeds.
4. Reassignment reuses canonical names case-insensitively, can create a new
   selectable pair, and rejects archived targets. An unchanged archived assignment
   remains valid for time- or note-only correction.
5. Correction preserves the entry ID, excludes the active timer from mutation,
   persists atomically, and updates history, summaries, export input data, and
   recent-work projections through their existing shared sources.
6. Unit, SQLite integration, IPC integration, and Textual workflow tests cover
   normalization and timestamp validation, successful correction, overlap and
   archived-target rejection, protocol transport, row selection, and refresh.

#### Documentation impact

- Top-level requirements now authorize completed-entry correction and define the
  no-overlap rule. Architecture records the agent-owned transactional correction
  boundary. The existing schema already supports the update, so no migration is
  required.

### Manual missed-time entry

**Status:** Implemented

#### Purpose

Let a user record one forgotten interval as a completed entry without briefly
starting a live timer or editing SQLite directly. This is the second ordered
slice of the roadmap's correction and missed-time workflow.

#### Required behavior

- In Review's completed-entry mode, provide an Add missed entry action that opens
  the existing entry editor in creation mode for project, activity, note, start,
  and stop.
- Clear the target and note fields and prefill an editable one-hour local interval
  ending at the current minute. Render both values as offset-aware ISO 8601
  timestamps.
- Trim project and activity names, normalize an empty or whitespace-only note to
  no note, and accept only offset-aware ISO 8601 timestamps.
- Reuse matching selectable project/activity names case-insensitively or create a
  new selectable pair using the timer-start naming rules. Reject an archived
  project or activity.
- After successful creation, refresh completed history, daily summaries, recent
  activities, and project suggestions; select the new row when possible and leave
  its canonical persisted values in the editor.
- Manual creation is unavailable in daily-summary mode. It does not start, stop,
  switch, or otherwise change the active timer.

#### Invariants and error handling

- Stop must be strictly after start. The new half-open interval `[start, stop)`
  must not overlap any completed or active entry, but may touch an existing
  boundary.
- Target resolution, overlap validation, and insertion occur in one SQLite
  transaction owned by the background process. No partial project, activity, or
  entry is retained when a request is rejected.
- Capture the entry's creation timestamp from the injected application clock only
  after field validation. Duration remains derived from start and stop.
- Reject invalid or offset-free timestamps, missing names, a non-positive
  interval, archived targets, or overlap with a concise error in the persistent
  TUI message area. Preserve the entered values after rejection so they can be
  repaired.

#### Acceptance criteria

1. A user can choose Add missed entry in Review, edit the five entry fields, save,
   and immediately see one new completed row without affecting the active timer.
2. The editor initially offers the previous local hour with explicit UTC offsets;
   offset-free or malformed input is rejected without creating an entry.
3. Stop equal to or before start and overlap with a completed or active entry are
   rejected atomically, while touching an existing boundary succeeds.
4. Creation reuses canonical names case-insensitively, can create a new selectable
   pair, and rejects archived targets without leaving partial target records.
5. The new entry appears in history, summaries, CSV source data, and recent-work
   projection through their existing shared sources and survives agent restart.
6. Unit, SQLite integration, IPC integration, and Textual workflow tests cover
   normalization, injected creation time, target handling, overlap rejection,
   protocol transport, creation mode, active-timer preservation, and refresh.

#### Documentation impact

- Top-level requirements now authorize manual creation of closed missed-time
  entries under the existing single-timer and no-overlap model. Architecture adds
  the agent-owned transactional insertion boundary. The existing schema already
  supports the entry, so no migration is required.

### Active-entry detail editing

**Status:** Implemented

#### Purpose

Let a user correct the project, activity, or note of work that is still running
without ending or restarting its timer. This completes the roadmap's initial
correction and missed-time workflow.

#### Required behavior

- Add an explicit Update active details action to Track, available by pointer and
  `F11`, using the current project, activity, and note inputs.
- Persist changes to the single active entry's project/activity assignment and
  normalized note while preserving its entry ID, original start timestamp, and
  creation timestamp.
- Trim names and normalize notes consistently with Start. When the assignment
  changes, reuse a matching selectable target case-insensitively or create a new
  selectable target under the timer-start naming rules; reject archived targets.
- When the assignment is unchanged, allow a note-only edit while retaining the
  active entry's target even if it has been archived since the timer started.
- Keep Start/Switch/Restart behavior available as the distinct transition choice.
  Enable Update active details only when a timer is active and the normalized
  Track inputs differ from it.
- After success, show canonical persisted values in Track, refresh target
  suggestions, and update the persistent active-timer strip without adding a
  completed entry.

#### Invariants and error handling

- Resolve or create the target and update the active row in one SQLite transaction
  owned by the background process. A rejection leaves both the active entry and
  any attempted new target unchanged.
- Reject missing names, no active timer, an archived reassignment, or normalized
  values identical to the active entry. Report the error in the persistent TUI
  message area without changing timer or reminder state.
- A successful edit does not capture a replacement start time, stop the entry,
  create another entry, or restart the active-reminder interval.
- Update future and already-pending active-reminder text to the new canonical
  project/activity while preserving the existing monotonic reminder deadline.

#### Acceptance criteria

1. With an active timer and changed Track fields, pointer activation or `F11`
   updates project, activity, and note while preserving entry ID and start time.
2. The edit creates no completed entry, does not reset elapsed time, and survives
   TUI and agent restart with its canonical values.
3. Case-insensitive target reuse and new target creation succeed; archived
   reassignment and missing names are rejected atomically. A note-only edit on an
   unchanged archived assignment succeeds.
4. Identical normalized values disable the TUI action and are rejected by a direct
   application or protocol request without invoking the clock or repository edit.
5. Reminder timing is unchanged by success or rejection, while subsequent and
   pending active prompts use the edited canonical project/activity.
6. Unit, SQLite integration, IPC/reminder integration, and Textual workflow tests
   cover normalization, no-op protection, atomic persistence, archived targets,
   shortcut and pointer use, start preservation, no history creation, recovery,
   and reminder metadata without deadline reset.

#### Documentation impact

- Top-level tracking requirements now authorize editing active details without a
  timer transition. Architecture records the transactional update and reminder
  metadata behavior. The existing schema supports the update, so no migration is
  required.

### Safe and reversible archive management

**Status:** Implemented

#### Purpose

Prevent accidental archive actions and let a user restore projects or activities
that were archived by mistake without editing SQLite or losing hierarchy state.

#### Required behavior

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

#### Invariants and error handling

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

#### Acceptance criteria

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

#### Documentation impact

- Top-level requirements now define archive restoration and its hierarchy rules.
  Architecture records the application/protocol boundary and transactional flag
  updates. The existing nullable archive columns support this feature, so no
  schema migration is required.

### Day-oriented Review and today's completed total

**Status:** Approved

#### Purpose

Make accumulated history easier to scan as a local timesheet and show the user
how much completed work has been recorded today without leaving Track.

#### Required behavior

- In Review's completed-entry mode, group completed time by local calendar date,
  show the date only on the first entry row in each group, render local start and
  stop values as compact `HH:MM` times, and add a total row after each day.
- Derive both grouped rows and day totals from one application-layer reporting
  projection. The TUI must not independently calculate date boundaries or
  durations.
- Split an entry that crosses local midnight into one display segment per local
  date so each group total follows the existing daily-summary rule. Each segment
  retains the source entry's identity, project, activity, and note and shows only
  the portion of its derived duration that belongs to that date.
- Loading any segment for correction loads the full source entry once, including
  its complete offset-aware local start and stop timestamps. A day-total row is
  not a completed entry and cannot be loaded for correction.
- Keep the existing Daily summaries representation and both CSV formats
  unchanged. CSV entry export continues to contain each full entry once with
  offset-aware timestamps; summary export continues to use the shared local-day
  split.
- Show `Today's completed time` in Track using the same day-oriented projection.
  It includes completed entry segments assigned to the current local date and
  excludes the active timer until that timer is persisted as completed.
- Refresh the Track total after start transitions that complete an entry, stop,
  correction, and missed-time creation, and roll it over when the local date
  changes while the TUI remains open.

#### Invariants and error handling

- Preserve chronological day and segment ordering. Presentation grouping does
  not mutate, duplicate, or replace persisted entries.
- Resolve local dates and midnight boundaries from stored UTC instants in the
  user's current local time zone, including offset changes. Durations remain
  differences between stored instants rather than differences between displayed
  wall-clock labels.
- Selecting a repeated segment of an entry that spans days always targets the
  same persisted entry ID. Selecting a day-total row reports that a completed
  entry must be selected and leaves editor and history state unchanged.
- If history cannot be loaded, retain the last successfully rendered Track total
  and Review data and report the agent error through the persistent message area.

#### Acceptance criteria

1. Completed time is shown in chronological local-date groups with the date once,
   `HH:MM` row times, and one derived total after each day.
2. An entry crossing local midnight appears as correctly clipped segments in
   both affected groups, and the group totals equal the sum of their segments,
   including across a local UTC-offset change.
3. Loading either segment of a cross-midnight entry opens the same entry ID and
   full offset-aware timestamps; a total row cannot be loaded.
4. Entry and daily-summary CSV output retains its existing schema, full timestamp
   precision, ordering, overwrite confirmation, and midnight-splitting behavior.
5. Track shows the current local date's completed duration, does not count the
   running portion of an active timer, refreshes after relevant writes, and
   changes to the new day's value after local midnight.
6. Application projection and Textual workflow tests cover grouping, compact
   rendering, overnight splitting, day totals, correction selection, today's
   completed total, and retained summary/export behavior.

#### Documentation impact

- Neither the top-level requirements nor the architecture changes. This feature
  presents the already-authorized completed history and local daily totals
  through the existing application reporting and TUI boundaries and requires no
  protocol or schema migration.

## Feature specification template

Use this structure when a feature is selected. Replace the placeholder rather
than treating the template as an approved requirement.

### Feature name

**Status:** Approved | Implemented

#### Purpose

State the user problem and intended outcome.

#### Required behavior

- Describe observable behavior and supported TUI interactions.

#### Invariants and error handling

- Describe rules that must always hold and how rejected actions are reported.

#### Acceptance criteria

1. State a verifiable outcome.

#### Documentation impact

- Note any corresponding change to the top-level requirements or architecture,
  or state that neither authoritative document changes.
