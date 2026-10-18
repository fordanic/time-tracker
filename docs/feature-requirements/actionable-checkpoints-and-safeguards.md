# Actionable checkpoints and scheduled safeguards

**Status:** Implemented

## Purpose

Help a user who keeps the TUI running but changes work elsewhere notice and act
on project, activity, and stopping transitions. Replace passive active-timer
reminders with checkpoints that can be answered from the TUI or, when running in
WSL, from the Windows native notification. Add configurable lunch and end-of-day
checkpoints, and optionally stop a timer after two consecutive checkpoints are
left unanswered.

The repository maintainer approved this feature, including the change to the
existing ignored-reminder rule, in the October 18, 2026 feature request that
selected implementation.

## Required behavior

- Treat every presented active-timer reminder as a checkpoint. Show the current
  project, activity, checkpoint reason, and these actions:
  Continue, Snooze, Stop, and Switch activity.
- Continue clears the checkpoint, resets the consecutive-unanswered count, and
  restarts the normal active-reminder interval. Snooze clears the visible prompt,
  resets the consecutive-unanswered count, and repeats the same checkpoint after
  the configured snooze duration without changing timer state. Stop durably stops
  the matching active timer at the action time. Switch activity resets the count
  and asks a connected foreground interface to show Track and focus the existing
  recent-work deck; selecting and confirming a recent pair performs the normal
  durable switch.
- Keep the same checkpoint and actions visible in the TUI and local web
  interface. An action from any surface applies to the one authoritative pending
  checkpoint.
- On Windows notifications delivered from WSL, show actionable Continue,
  Snooze, Stop, and Switch activity buttons. Register a current-user custom
  protocol handler that starts the same WSL distribution and Time Tracker command
  with an opaque checkpoint action URI. The command connects through the existing
  authenticated agent IPC; it never accesses SQLite directly.
- Give every active checkpoint an unguessable in-memory identifier. Native action
  URIs contain only the action and identifier, never project names, activity
  names, notes, database paths, IPC secrets, or other tracked content. Reject a
  missing, malformed, expired, already-used, or nonmatching identifier without
  changing timer or reminder state.
- Add optional Lunch and End-of-day checkpoints. Settings provides one enabled
  control and local `HH:MM` time for each plus one shared non-empty set of local
  weekdays. They are disabled by default. A configured checkpoint is emitted
  once on each selected local date when a timer is active.
- Scheduled safeguards use the same actions, response handling, and single
  pending-checkpoint channel as periodic checkpoints. They are independent of
  the reminder delivery window: the window continues to govern periodic and
  idle-triggered reminders, while an enabled lunch or end-of-day checkpoint is
  presented at its configured time.
- Add an opt-in `stop after two unanswered checkpoints` setting, disabled by
  default. Each presented active checkpoint has a fixed five-minute response
  grace period. If no checkpoint action or qualifying foreground timer action is
  accepted before the grace expires, increment the consecutive-unanswered count.
  Do not count a checkpoint whose native delivery failed or was unavailable;
  foreground visibility alone does not make a checkpoint eligible for automatic
  stop.
- When the second consecutive checkpoint expires unanswered, durably stop the
  still-matching active timer at the grace-expiry action time. Then clear pending
  and unanswered state and send a new native notification identifying the
  project/activity and exact local stop time and directing the user to Review for
  correction. The completed entry is otherwise an ordinary entry.
- Continue, Snooze, Stop, Switch activity, a manual start/switch/restart/stop, or
  an active-detail edit resets the consecutive-unanswered count. Settings reload
  and agent restart also reset in-memory checkpoint state. An inactive-timer
  reminder never increments the active checkpoint count and never stops a timer.
- Save the scheduled-checkpoint and automatic-stop settings in the existing
  strict `[reminders]` TOML table and apply a valid save live. A successful save
  clears pending checkpoint state and resets schedules from the save time.
- When a response grace expires, clear that prompt. The periodic deadline already
  scheduled when the checkpoint was presented remains authoritative, so the next
  checkpoint occurs on that cadence rather than five minutes after expiry.
- An active-detail edit clears the pending checkpoint and unanswered count while
  preserving the already-scheduled periodic deadline. A native Switch request
  remains pending until one foreground interface consumes it, or until a timer
  transition, settings reload, or agent restart invalidates it. Consuming it
  clears the checkpoint; changing timer state later remains an explicit action.

## Invariants and error handling

- The background process remains the single database writer and the only owner
  of checkpoint state. Native notification handlers, the TUI, and the web
  interface send authenticated commands; none writes SQLite or infers timer
  transitions independently.
- A Stop or Switch action is conditional on the checkpoint identifier and active
  entry identity captured when the checkpoint was created. A stale native action
  cannot stop, confirm, snooze, or redirect a newer timer.
- Persist a manual or automatic stop before reporting or notifying success. If
  persistence fails, leave the timer active, clear no authoritative timer state,
  log the failure, and do not claim that it stopped.
- Native delivery success means the operating system accepted the notification;
  it does not assert that the user saw it. Automatic stop therefore remains
  explicitly opt-in and is described that way in Settings.
- Use monotonic time for response-grace, periodic, and snooze deadlines. Use an
  aware local wall clock only to find the next scheduled lunch or end-of-day
  occurrence and to render the automatic-stop time.
- Do not catch up scheduled safeguards missed while the agent was stopped, while
  no timer was active, or while another checkpoint already represented the same
  active timer. Do not emit duplicate safeguards for one label and local date.
- If a scheduled safeguard becomes due while another active checkpoint is
  pending, keep one prompt and treat the existing prompt as the checkpoint for
  that moment; do not replace it or increment the unanswered count early.
- Reject equal enabled Lunch and End-of-day times rather than assigning an
  arbitrary label to one simultaneous occurrence. Local-time safeguards follow
  the process's current local clock; the existing open product decision for DST,
  system-clock, and time-zone changes remains unchanged.
- Protocol registration is current-user only, idempotent, timeout-bounded, and
  contains one fixed command template. User-controlled reminder text never enters
  registry command source, PowerShell source, action URIs, or shell interpolation.
  Registration or activation failure leaves timer and checkpoint state unchanged
  and is logged through the existing notification-failure path.
- If an automatic stop fails, clear the expired miss sequence and leave the timer
  active. Do not retry in a loop; a later pair of successfully delivered,
  unanswered checkpoints may try again.
- Reject invalid booleans, empty weekday selections, duplicate or out-of-range
  weekdays, and times not using `HH:MM` without changing the durable file or live
  schedule.

## Acceptance criteria

1. A periodic, lunch, end-of-day, or idle-triggered active checkpoint appears in
   the TUI and web interface with Continue, Snooze, Stop, and Switch activity;
   each accepted action has the specified timer and scheduling effect.
2. A WSL-delivered Windows notification presents the four actions. Its
   current-user protocol registration invokes the originating distribution and
   Time Tracker command, and a valid opaque action reaches the agent without
   exposing tracked content or the IPC secret.
3. A valid Stop action stops only the active entry named by the pending
   checkpoint. Expired, replayed, malformed, and stale actions are rejected and
   cannot affect a later entry.
4. Switch activity resets unanswered state and causes a connected TUI to open
   Track with the recent-work deck focused; confirming a choice uses the existing
   atomic switch behavior.
5. Lunch and End-of-day settings round-trip through strict TOML and live reload.
   Each enabled safeguard fires once on a selected local date while active,
   regardless of the periodic reminder window, and produces no catch-up prompt.
6. With automatic stop disabled, ignored checkpoints never stop a timer. With it
   enabled, one successfully delivered checkpoint that receives no accepted
   response for five minutes records one miss; a response resets the count; and
   the second consecutive expiry stops the matching timer at that expiry time.
7. After automatic stop succeeds, a distinct native notification contains the
   canonical target and exact local stop time, the completed entry is visible in
   Review, and no active timer remains. Persistence failure leaves the timer
   active and does not send the success notification.
8. Inactive reminders, failed native delivery, settings reload, agent restart,
   stale action replay, and a timer transition during a grace period cannot cause
   an automatic stop of the wrong timer.
9. Unit tests cover checkpoint identifiers, grace and consecutive-miss policy,
   scheduled local-time calculation and deduplication, reset behavior, and action
   validation. Integration tests cover IPC actions, live configuration, durable
   stop, and failure behavior. TUI and web tests cover the four controls and
   switch focus. WSL adapter tests cover protocol registration, action URIs,
   text-as-data handling, timeout, and failure mapping without starting Windows.
10. An interactive WSL smoke verifies all four Windows actions against a running
    TUI and verifies the post-auto-stop notification. Until recorded in README
    Status, that native interaction remains an outstanding validation item.

## Documentation impact

- Top-level requirements change the ignored-active-reminder rule to authorize an
  opt-in, two-unanswered-checkpoint automatic stop and add scheduled safeguards
  and active checkpoint actions.
- Architecture replaces the deferred-native-action choice with an authenticated
  current-user activation adapter, records in-memory checkpoint ownership and
  conditional actions, and adds local-wall-clock safeguard scheduling around the
  monotonic reminder scheduler.
- No database migration is required. Pending identifiers, response deadlines,
  unanswered counts, scheduled-date deduplication, and switch requests are
  agent-owned in-memory state; only the completed time entry created by an
  automatic stop is durable.
