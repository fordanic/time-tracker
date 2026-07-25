# Opt-in idle-triggered active reminder

**Status:** Implemented

## Purpose

Help a user notice a timer that may have been left running while the computer was
unattended, without observing application content or silently changing recorded
time. This is the selected outcome of the roadmap's final reassessment: derived
recent work already covers the main favorites/default-project benefit, while
idle awareness addresses the distinct remaining forgotten-stop risk.

## Required behavior

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

## Invariants and error handling

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

## Acceptance criteria

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

## Documentation impact

- Top-level requirements now authorize opt-in, prompt-only local idle detection
  and resolve that open product decision. Architecture records the injected
  operating-system adapter and agent-owned advisory polling boundary. No database
  migration is required.
