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

**Status:** Implemented

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

### Shared Review filters and range summaries

**Status:** Implemented

#### Purpose

Let a user narrow accumulated history to a useful local period and target, then
review or export the same selected time without having to reconcile different
datasets.

#### Required behavior

- Add an **All time** date preset plus the roadmap presets **Today**, **This
  week**, **This month**, and **Custom**. Today is the current local calendar
  date; This week is the Monday-through-Sunday calendar week containing today;
  and This month is the first through last calendar date of the current local
  month.
- Custom requires an ISO 8601 start date and end date. Both boundaries are
  inclusive. Resolve presets and custom dates in the user's current local time
  zone, including daylight-saving offset changes.
- Add optional project and activity filters. Match trimmed names
  case-insensitively against canonical historical names. An activity without a
  project matches that activity name beneath any project; when both are present,
  both must match the same completed segment.
- Combine date, project, and activity criteria with AND. A blank target criterion
  means any value. Make canonical targets represented in completed history
  available for selection even when the project or activity is now archived.
- Apply one application-layer filter model to completed-entry Review, daily
  summaries, range totals, and all three matching CSV exports. The TUI may resolve
  controls into that model but must not implement separate filtering or
  aggregation rules.
- Date filtering operates on completed-time portions assigned to the selected
  local dates. An entry crossing a selected boundary contributes only its segment
  inside the inclusive date range. With no date bound, retain each full entry.
- Retain the day-grouped completed-entry and daily-summary representations. Add a
  **Range totals** representation with one row per project/activity pair and the
  pair's total completed duration across the current filter.
- Detailed CSV keeps the existing columns. When a date filter clips an entry,
  export the selected contiguous portion with clipped offset-aware start and stop
  timestamps so its duration agrees with the selected Review data. Daily-summary
  CSV keeps its existing columns and contains only selected dates and targets.
  Range-total CSV uses these columns:

  ```text
  project,activity,duration_seconds
  ```

- Changing any filter or representation refreshes Review immediately and clears
  a pending overwrite confirmation. A concise description of the active filter
  remains visible beside the results.
- Show a concise empty state when no completed time matches. Exporting an empty
  selection writes only the selected representation's header and reports zero
  rows.

#### Invariants and error handling

- Reject a malformed custom date, a missing custom boundary, or a start date
  after the end date. Keep the last valid rendered selection and do not export
  until the filter is valid; report the error in the persistent message area.
- Derive selected durations from stored UTC instants. Local-date clipping and
  daylight-saving changes must not turn wall-clock labels into authoritative
  durations or create overlaps.
- Filtering and aggregation are read-only. They never mutate entries, archive
  state, targets, the active timer, or reminder scheduling. The active entry
  remains excluded from Review and export.
- Preserve chronological ordering for detailed and daily results. Order range
  totals by case-insensitive project and activity name, with canonical spelling as
  the stable tie-breaker.
- A completed-entry segment remains correctable through its source entry ID.
  Summary and empty-state rows are not correctable. Applying a filter does not
  alter a loaded editor or persist any correction.
- The filter serialized for export must be the same validated model used by the
  current on-screen representation. An agent rejection leaves the destination
  untouched except for the existing confirmed-overwrite semantics.

#### Acceptance criteria

1. All time, Today, This week, This month, and a valid custom inclusive range show
   the expected local-date segments, including an entry crossing midnight or a
   UTC-offset transition.
2. Project and activity filters match canonical historical names
   case-insensitively, can select archived targets, work independently, and
   combine with each other and the date filter using AND.
3. Completed-entry, daily-summary, and range-total views derive from the same
   filter; range totals equal the sum of the selected detailed durations for each
   project/activity pair.
4. Each CSV representation applies the current filter. Detailed export clips at
   selected date boundaries, daily export retains local dates, range export uses
   the approved three-column schema, and each exported duration agrees with the
   on-screen selection.
5. Invalid custom input preserves the last valid results, reports a concise
   error, and blocks export. A valid selection with no matches shows an empty
   state and exports a header-only file after normal overwrite confirmation.
6. Unit, CSV, IPC, and Textual workflow tests cover preset boundaries, inclusive
   custom dates, filter combinations, archived targets, empty and invalid states,
   overnight and daylight-saving clipping, all representations, and filtered
   export.

#### Documentation impact

- Top-level requirements now authorize shared Review filters and range-total CSV
  export, resolving the corresponding open product decision. Architecture records
  the application-owned filter/projection and protocol transport boundaries. The
  existing entry schema is unchanged, so no migration is required.

### TUI-managed reminder settings and live reload

**Status:** Implemented

#### Purpose

Let a user inspect and change the supported reminder configuration without
leaving the TUI or manually restarting the background process.

#### Required behavior

- In Settings, show independent enabled controls and interval-minute inputs for
  inactive-timer and active-timer reminders, initialized from the agent's current
  durable configuration. Show the configuration file path so the human-readable
  source remains discoverable.
- Accept positive numeric minute intervals, including fractional values. Retain
  each interval value when its reminder is disabled so re-enabling it does not
  require re-entry.
- Save all four supported reminder values as one complete `[reminders]` TOML
  table through an application configuration port owned by the background
  process. Validate the typed configuration before writing and atomically replace
  the destination so a failed write cannot leave a partial file.
- After durable replacement succeeds, apply the new enabled intervals to the
  running agent without a stop/restart cycle. Reset the schedule for the current
  active or inactive timer state from the successful save time and clear any
  already-pending reminder because it belongs to the replaced schedule.
- Report a successful save in the persistent message area. A newly opened TUI or
  a restarted agent must read back the same saved values.

#### Invariants and error handling

- Reject blank, non-numeric, non-finite, zero, or negative intervals. Keep both
  the existing file and live reminder schedule unchanged and report a concise
  validation error.
- A persistence failure keeps the live schedule unchanged and is reported without
  claiming success. Timer state, entries, targets, and reminder confirmation
  semantics are never changed by configuration editing.
- Configuration remains strict: unknown TOML sections or keys are still rejected
  when loading a user-edited file. A TUI save writes only the currently supported
  keys and built-in defaults remain effective when no file exists.
- Live reload changes reminder deadlines only as the explicit consequence of a
  successful settings save. Native notification delivery failure remains
  separate from authoritative configuration and timer state.

#### Acceptance criteria

1. Settings displays the effective defaults when no file exists and round-trips
   enabled, disabled, integer, and fractional interval values through the agent.
2. A successful save atomically creates or replaces valid TOML, immediately
   applies it without restarting the agent, clears a pending reminder, and resets
   the current state's deadline from the save.
3. Invalid TUI input and simulated write failure preserve the prior file and live
   schedule and present an error.
4. Restarting the TUI and agent after a save shows and uses the durable values.
5. Unit, IPC/reminder integration, and Textual workflow tests cover defaults,
   round-trip persistence, live enable/disable reload, pending-prompt clearing,
   validation failure, and restart recovery.

#### Documentation impact

- Top-level requirements already authorize independently configurable reminder
  intervals and TOML storage, so they do not change. Architecture changes from
  startup-only loading to an agent-owned application/configuration port with
  atomic persistence and live scheduler reload. No database migration is needed.

### Reminder windows and snooze

**Status:** Implemented

#### Purpose

Keep reminders useful without interrupting the user outside their chosen working
hours, and let a due prompt be deferred without confirming or changing timer
state.

#### Required behavior

- Settings provides an optional weekly reminder window, expressed as one or more
  local weekdays and local `HH:MM` start and end times. The window is disabled by
  default so existing reminder behavior is preserved.
- A start earlier than the end defines a same-day window. A start later than the
  end defines an overnight window that begins on each selected weekday and ends
  on the following local day. Equal start and end is rejected as ambiguous.
- Both inactive- and active-timer reminders use the same window. When an interval
  becomes due outside it, no native notification or TUI prompt is emitted; the
  reminder becomes due at the next opening instead of accumulating missed
  notifications.
- Settings provides one positive snooze duration in minutes. When any reminder is
  pending, a Snooze action clears its TUI prompt and schedules that reminder kind
  from the snooze action time. The active timer, completed history, reminder
  interval, and active-confirmation semantics are unchanged.
- Snooze is available by pointer and `F12`. Active reminders retain their separate
  `F10` confirmation action; inactive reminders expose only Snooze.
- Save the complete window and snooze configuration with the existing reminder
  settings and apply it live. A successful save clears any prompt and resets the
  current timer state's normal interval from the save time.

#### Invariants and error handling

- Interpret weekday and clock values in the agent process's current local time
  zone. Re-evaluate the wall clock only at window boundaries; continue to use a
  monotonic clock for interval and snooze deadlines so system-clock changes do
  not shorten an in-progress interval.
- Snooze state is deliberately in-memory and is not written to SQLite or TOML.
  Start, switch, stop, active confirmation, successful settings replacement, and
  background-process restart replace it with the normal interval. Editing active
  details preserves an existing snooze deadline while updating reminder text.
- Repeated polling or Snooze invocation without a pending reminder is a rejected
  no-op. A rejection does not alter schedule, configuration, or timer state and is
  reported in the persistent TUI message area.
- Reject an enabled window with no weekdays, an unknown or duplicate weekday,
  malformed clock value, or equal start and end. Reject blank, non-numeric,
  non-finite, zero, or negative snooze minutes. A validation or persistence
  failure leaves the prior durable configuration, live schedule, and pending
  reminder unchanged.
- Daylight-saving transitions use the platform time zone's normal local-time
  resolution. A closed period never produces catch-up bursts: at most one
  reminder becomes pending when the next window opens.

#### Acceptance criteria

1. With the window disabled, both reminder kinds repeat at their configured
   intervals exactly as before.
2. With a same-day or overnight window enabled, a reminder due outside the window
   is suppressed until the next selected opening, while one due inside it is
   delivered normally.
3. Snoozing either reminder kind clears the pending prompt, emits no timer write,
   and delivers the next reminder after the configured snooze duration.
4. Timer transitions, active confirmation, settings replacement, and agent
   restart cancel snooze in favor of the normal interval; active-detail editing
   preserves its deadline and updates pending or future reminder names.
5. The complete configuration round-trips through strict TOML, IPC, and Settings;
   invalid window or snooze input changes neither durable nor live state.
6. Unit, IPC/reminder integration, and Textual workflow tests cover window
   inclusion and next-opening behavior, overnight windows, snooze for both kinds,
   reset rules, configuration round-trip, validation, and pointer/shortcut use.

#### Documentation impact

- Top-level reminder requirements now authorize a shared optional weekly window
  and explicit snooze. Architecture records wall-clock window policy around the
  monotonic scheduler and in-memory snooze ownership. No database migration is
  required.

### Opt-in idle-triggered active reminder

**Status:** Implemented

#### Purpose

Help a user notice a timer that may have been left running while the computer was
unattended, without observing application content or silently changing recorded
time. This is the selected outcome of the roadmap's final reassessment: derived
recent work already covers the main favorites/default-project benefit, while
idle awareness addresses the distinct remaining forgotten-stop risk.

#### Required behavior

- Add an idle-reminder enabled control and positive idle-threshold-minutes input
  to Settings. Detection is disabled by default, the default threshold is 15
  minutes, positive fractional minutes are accepted consistently with reminder
  intervals, and the configured threshold is retained while disabled.
- While a timer is active and idle detection is enabled, let the background
  process obtain the operating system's local input-idle duration through a
  narrow injected adapter. Do not inspect, record, or persist keys, pointer
  positions, application names, window titles, screenshots, or other activity
  content.
- When one continuous idle episode reaches the configured threshold, request the
  existing active-timer reminder early. Its native notification and connected-TUI
  prompt content must identify idleness as the reason and show the configured
  threshold. Detection remains independently available when periodic active
  reminders are disabled.
- Use the existing active-reminder actions: `F10` confirms that tracking should
  continue, `F12` snoozes the prompt, and Stop or `F6` stops the timer at the time
  of that explicit stop action. Direct the user to Review correction when idle
  time should be removed from the completed entry.
- Apply the configured reminder window to an idle-triggered reminder. If the
  threshold is reached outside the window, defer presentation until the next
  opening without emitting catch-up prompts.
- Emit at most one initial idle-triggered reminder for a continuous idle episode.
  Observed user input makes a later idle episode eligible; active-reminder snooze
  may repeat the pending prompt under its existing deadline semantics.
- Treat only idle time attributable to the current active timer as eligible. If
  the operating system reports an idle episode that began before the active
  entry, the eligible duration begins at the active entry's persisted start.
- Save the enabled state and threshold with the complete reminder configuration,
  apply a successful save live, and expose whether idle detection is available in
  the current platform session.
- Poll only while detection is enabled and a timer is active. Once eligible idle
  reaches the threshold, request the reminder within 15 seconds.

#### Invariants and error handling

- Observed idle duration and episode state are advisory and in memory. They never
  start, stop, switch, restart, edit, or create an entry; never change an active
  entry's start; and are not stored in SQLite, TOML, exports, logs, or history.
  Only the enabled setting and threshold are durable.
- The background process owns idle polling and reminder coordination. The TUI
  must not poll the operating system or infer idle state independently. Use an
  injected fake detector and clocks for deterministic application and scheduler
  tests.
- An idle trigger uses the single pending active-reminder channel. If an active
  reminder is already pending, treat that prompt as handling the episode and do
  not replace it or enqueue another. If idle wins a simultaneous deadline, label
  the one prompt as idle-triggered. Once an idle-triggered prompt is pending,
  deferred by the window, or snoozed, a normal active deadline and further idle
  episodes do not replace or duplicate it. Existing confirmation, snooze,
  reminder-window, settings-reload, and timer-transition behavior remains
  unchanged.
- User input after an idle reminder was requested does not cancel its pending,
  deferred, or snoozed prompt. `F10` confirmation both restarts the normal active
  interval and establishes a new activity baseline immediately; a later full idle
  threshold may then trigger again without depending on the next detector poll.
- A valid settings replacement clears any pending or snoozed prompt and resets
  the normal schedule under the existing rule. Enabling detection or changing
  its threshold also establishes a new activity baseline at the save time, so an
  already-in-progress idle episode cannot trigger immediately from pre-save idle.
- A start, switch, restart, or stop clears the in-memory idle episode state.
  Editing active details preserves it because that edit is not a timer
  transition.
- Reject a blank, non-numeric, non-finite, zero, or negative threshold without
  changing the durable configuration or live detector state.
- If the platform adapter is unavailable or fails, leave timer state and the
  normal reminder schedule unchanged, log the operational failure without idle
  or input data, and show idle detection as unavailable in Settings. Do not emit
  repeated failure notifications or retry continuously; retry when settings are
  next saved or the agent restarts.
- Computer sleep, wall-clock changes, and detector-specific idle accounting may
  affect the advisory duration but must never alter persisted time. Timer and
  reminder deadlines retain their existing UTC and monotonic-clock authority.
- The one-prompt limit is per continuous idle episode observed by one agent
  lifetime. Because episode state is deliberately not persisted, an agent restart
  may produce another advisory prompt if the same operating-system idle episode
  remains eligible.

#### Acceptance criteria

1. Idle detection is disabled by default; Settings round-trips its enabled state
   and positive threshold through strict TOML and the agent protocol and applies
   a valid change without restarting the agent.
2. With an active timer and available detector, one continuous eligible idle
   episode reaching the threshold produces one idle-labelled active reminder;
   no timer, entry, or database value changes.
3. Idle time predating the current active entry does not trigger early. Enabling
   or changing the threshold during an idle episode starts eligibility at the
   save time. A later user-input reset followed by another full threshold makes a
   new episode eligible.
4. `F10`, `F12`, and `F6` retain confirmation, snooze, and explicit-stop
   behavior for an idle-triggered prompt. Removing idle time remains an explicit
   completed-entry correction rather than an automatic rewrite.
5. An existing pending active reminder consumes the episode without duplication.
   An idle-triggered prompt is not replaced by a later normal deadline or input,
   and one reached outside the configured window is presented at the next opening
   without a catch-up burst.
6. Start, switch, restart, and stop clear idle episode state; active-detail
   editing preserves it; disabling the feature stops polling without changing
   the timer or periodic-reminder configuration, while still performing the
   normal schedule reset required after any successful settings replacement.
7. An unavailable or failing detector leaves authoritative timer and reminder
   state intact, records no input detail, reports one stable unavailable status
   in Settings, and retries only after settings save or agent restart.
8. Unit, agent/reminder integration, IPC/configuration, and Textual workflow tests
   cover threshold crossing, timer-start clipping, episode reset, prompt
   deduplication, window and snooze interaction, live settings, unavailable
   detection, and the no-automatic-mutation guarantee. Interactive platform
   smokes verify idle-duration detection on supported interactive Linux, Windows,
   and macOS sessions.

#### Documentation impact

- Top-level requirements now authorize opt-in, prompt-only local idle detection
  and resolve that open product decision. Architecture records the injected
  operating-system adapter and agent-owned advisory polling boundary. No database
  migration is required.

### Responsive shortcut discovery

**Status:** Implemented

#### Purpose

Keep keyboard actions discoverable without overflowing the bottom row in narrow
terminals, while retaining the existing F-key accelerators.

#### Required behavior

- Retain F1 through F12 with their existing actions.
- Use `Ctrl+K` for the complete shortcut overlay and `Ctrl+C` to quit; avoid
  terminal flow-control and bell combinations such as `Ctrl+Q` and `Ctrl+G`.
- Replace the always-expanded global shortcut row with a compact,
  context-relevant summary for the selected view.
- Keep an always-visible shortcut-help action at the start of the summary and
  present every binding in a dedicated overlay.
- Include reminder actions in the compact summary only while a reminder is
  pending.

#### Invariants and error handling

- Hiding a binding from the compact row does not disable it.
- The shortcut overlay is read-only, keyboard dismissible, and does not mutate or
  clear any workflow state.
- At narrow widths the shortcut-help action remains visible even when later
  context actions are clipped.

#### Acceptance criteria

1. F1 through F12 retain their documented actions.
2. Track, Review, Manage, and Settings show only their relevant action summary.
3. Shortcut help lists all view, timer, reminder, archive, export, update, and
   quit bindings and can be opened and closed without changing app state.
4. A narrow-terminal Textual test verifies that shortcut help remains
   discoverable and the full global binding list is not rendered in the footer.

#### Documentation impact

- Neither top-level requirements nor architecture changes. This refines the TUI
  presentation of existing keyboard behavior.

### Hierarchical project and activity management

**Status:** Implemented

#### Purpose

Let users browse and select archive targets instead of retyping exact project and
activity names.

#### Required behavior

- Manage displays all selectable projects and their activities in one
  hierarchical tree.
- Selecting a project or activity enables one archive action for that exact node.
- Manage displays archived projects and activities in a second hierarchical tree
  and restores the selected exact node.
- F8 and F9 retain project-archive and activity-archive behavior for the
  corresponding selected node.
- Refresh both trees whenever Manage is selected so changes made while another
  view is active are visible immediately.
- Refresh both trees after every successful archive or restore and keep a
  sensible neighboring selection when possible.

#### Invariants and error handling

- Archiving still requires a second explicit confirmation naming the canonical
  target and warning that a running timer continues.
- An activity cannot be restored while its parent project is archived.
- Restoring a project does not change independent child archive flags.
- Tree selection and expansion are presentation-only and never change storage.

#### Acceptance criteria

1. Active projects and activities are visible without typing and either node kind
   can be selected and archived after confirmation.
2. Archived projects and activities are visible with parent context and either
   node kind can be selected for restore.
3. Parent restore ordering, active-timer preservation, exact-target
   confirmation, and reserved-name behavior remain unchanged.
4. Textual tests cover project and activity selection, confirmation, refresh,
   restore ordering, empty states, and F8/F9.

#### Documentation impact

- Neither top-level requirements nor architecture changes. Existing archive
  behavior is presented through a safer TUI selection model.

### Review selection and action layout

**Status:** Implemented

#### Purpose

Make Review filtering and entry actions easier to understand and operate without
typing known project and activity names.

#### Required behavior

- Replace Review's project and activity free-text filters with Select controls.
- Include explicit all-projects and all-activities options.
- Populate projects from completed history, including archived historical names,
  and limit activity choices to the selected project when one is selected.
- Place Load selected entry and Add missed entry directly below the history
  table, aligned to the left.
- Left-align Daily summaries and Range totals with visible spacing between them.

#### Invariants and error handling

- Date, project, and activity filtering remains case-insensitive and shared by
  detail, summaries, totals, and export.
- Refreshing history preserves a still-valid selection and otherwise falls back
  to the corresponding unfiltered option.
- Summary modes retain their existing mutual exclusion and continue disabling
  completed-entry editing.

#### Acceptance criteria

1. A user can select unfiltered, active, or archived historical targets without
   entering free text.
2. Selecting a project updates the activity choices and rendered results.
3. Entry buttons appear below the table and summary switches are left-aligned
   with separation at supported widths.
4. Textual tests cover selection, refresh, archived choices, layout order,
   summary interaction, and export consistency.

#### Documentation impact

- Neither top-level requirements nor architecture changes.

### Track capture layout and note reset

**Status:** Implemented

#### Purpose

Use horizontal space efficiently, support short multiline notes, and prevent a
note from an earlier target being unintentionally carried to an explicitly
selected target.

#### Required behavior

- Place project and activity inputs on one row when space permits and stack them
  in narrow terminals.
- Use a two-line multiline note editor with soft wrapping and normal Tab focus
  traversal.
- Preserve line breaks as plain-text note content.
- Clear the note only when the user explicitly selects a target from recent work
  or another selection control. Typing or correcting project/activity text does
  not clear it.

#### Invariants and error handling

- Multiline notes follow the existing trim/empty normalization rules.
- Selecting a target never starts, switches, restarts, or edits a timer by
  itself.
- Responsive layout changes do not discard field values or change focus order.

#### Acceptance criteria

1. Project and activity share a row at the normal supported width and stack at a
   defined narrow width.
2. The note editor shows two lines, accepts line breaks, and Tab advances focus.
3. Explicit recent-target selection clears the note, while typed target edits do
   not.
4. Start, switch, restart, active-detail edit, recovery, and CSV quoting preserve
   multiline notes.

#### Documentation impact

- Neither top-level requirements nor architecture changes.

### Theme-safe visual spacing

**Status:** Implemented

#### Purpose

Improve form readability and ensure application styling remains legible across
Textual themes.

#### Required behavior

- Remove unintended colored gutters between vertically stacked inputs while
  retaining clear field boundaries.
- Increase vertical separation between Settings rows.
- Vertically center Settings input text without clipping borders or focus state.
- Use semantic Textual theme variables for foreground, background, status, focus,
  and selection colors instead of component-specific literal colors.

#### Invariants and error handling

- Layout remains scrollable in short terminals and usable in narrow terminals.
- Styling does not change business behavior, focus order, or enabled state.
- Success and error messages remain distinguishable and legible in both light
  and dark built-in themes.

#### Acceptance criteria

1. Settings rows have consistent vertical rhythm and centered input content.
2. Stacked inputs use the parent background between controls.
3. Light and dark theme tests verify readable messages, focus, selection, and
   reminder state without hard-coded palette values.

#### Documentation impact

- Neither top-level requirements nor architecture changes.

### Persistent theme and export preferences

**Status:** Implemented

#### Purpose

Restore the user's selected theme across launches and support pipe-delimited
exports without making them the default.

#### Required behavior

- Persist a selected built-in Textual theme in the human-readable configuration
  and apply it on the next TUI launch.
- Fall back to the built-in default when the saved theme is not available and
  persist the fallback when possible.
- Expose comma and pipe as export-delimiter choices in Settings, with comma as
  the default.
- Apply the configured delimiter to detailed, daily-summary, and range-total
  exports.
- Preserve reminder, theme, and export settings when any one area is saved.

#### Invariants and error handling

- Theme selection is presentation-only and never changes timer or reminder
  state.
- Configuration remains strict and atomically replaced; invalid values do not
  overwrite the prior file or live settings.
- Export quoting preserves commas, pipes, quotes, Unicode, and line breaks in
  notes for either delimiter.
- Existing configuration files containing only `[reminders]` continue to load
  with the default theme and comma delimiter.

#### Acceptance criteria

1. Selecting another built-in theme, closing the TUI, and reopening it applies
   the same theme.
2. An unknown saved theme falls back safely without preventing launch.
3. Settings round-trip comma and pipe values through TOML and IPC without
   restarting the background process.
4. All three export representations use the chosen delimiter, while comma
   remains the default for existing and absent configurations.
5. Unit, integration, IPC, and Textual tests cover persistence, partial settings
   preservation, fallback, live delimiter changes, and quoted multiline notes.

#### Documentation impact

- Top-level requirements authorize persistent theme and delimiter preferences.
  Architecture records the additional TOML tables and per-export writer setting.
  No database migration is required.

### Versioned release candidates and releases

**Status:** Implemented

#### Purpose

Make a reviewed build identifiable and repeatable, and allow release
candidates and final releases to be published from target-platform development
machines when GitHub Actions minutes are unavailable.

#### Required behavior

- Keep one canonical application version. Use `X.Y.Z` for a final version and
  `X.Y.ZrcN`, where `N` starts at one, for a release candidate.
- Derive Python project metadata and `time-tracker --version` from that canonical
  value. Use it for Windows file-version resources and macOS bundle metadata, and
  use `v<version>` as the corresponding Git tag.
- Provide one command to set and validate the canonical version and refresh the
  lockfile for the dynamic project metadata.
- Provide a local target-platform command that runs the complete checks, builds
  the native package, runs the packaged lifecycle smoke, verifies the frozen
  executable reports the canonical version, and creates a versioned archive plus
  SHA-256 checksum.
- Name release assets with the application version, operating system, and CPU
  architecture so independently built platform assets can coexist in one GitHub
  release.
- Provide separate local publication commands for release candidates and final
  releases. The first platform creates the annotated tag and GitHub release;
  later platforms upload their independently validated assets to the same tag.
- Publish a candidate as a visible GitHub prerelease and a final version as a
  visible GitHub release. Generate release notes from Git history through GitHub.

#### Invariants and error handling

- Reject malformed versions, a candidate publication for a final version, and a
  final publication for a candidate version before changing Git or GitHub state.
- Refuse publication from a dirty checkout, when an existing version tag points
  to another commit, when the packaged executable reports another version, or
  when the expected archive or checksum is absent.
- Authenticate GitHub CLI access before creating or pushing a tag. Re-running
  publication at the same version commit is resumable: reuse the exact tag and
  release, but refuse to overwrite an existing asset silently.
- Build each native artifact on its target operating system; do not present
  PyInstaller as a cross-compiler. A GitHub release may be populated by multiple
  machines, but every uploaded asset follows the same local validation path.
- Tag pushes do not trigger the hosted check workflow. No release or
  release-candidate operation depends on GitHub Actions.

#### Acceptance criteria

1. Project metadata, the source CLI, and the frozen executable report the same
   canonical final or release-candidate version.
2. A target-platform release build produces the documented versioned archive
   and a checksum that verifies its exact bytes.
3. Candidate publication creates or reuses `vX.Y.ZrcN` and a GitHub prerelease;
   final publication creates or reuses `vX.Y.Z` and a non-prerelease release.
4. A second target platform can upload a differently named asset to the same
   release without replacing an existing asset.
5. Unit tests cover version validation and replacement, platform/architecture
   naming, version verification, archive contents, checksums, and publication
   precondition failures.

#### Documentation impact

- Top-level requirements now require consistent build identity and permit
  locally validated GitHub downloads. Architecture records the version source,
  native artifact format, and local GitHub CLI publication boundary. No product
  data or protocol migration is required.

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
