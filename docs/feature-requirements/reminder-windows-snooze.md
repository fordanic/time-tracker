# Reminder windows and snooze

**Status:** Implemented

## Purpose

Keep reminders useful without interrupting the user outside their chosen working
hours, and let a due prompt be deferred without confirming or changing timer
state.

## Required behavior

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

## Invariants and error handling

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

## Acceptance criteria

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

## Documentation impact

- Top-level reminder requirements now authorize a shared optional weekly window
  and explicit snooze. Architecture records wall-clock window policy around the
  monotonic scheduler and in-memory snooze ownership. No database migration is
  required.
