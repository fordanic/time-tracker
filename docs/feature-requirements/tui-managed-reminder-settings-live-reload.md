# TUI-managed reminder settings and live reload

**Status:** Implemented

## Purpose

Let a user inspect and change the supported reminder configuration without
leaving the TUI or manually restarting the background process.

## Required behavior

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

## Invariants and error handling

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

## Acceptance criteria

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

## Documentation impact

- Top-level requirements already authorize independently configurable reminder
  intervals and TOML storage, so they do not change. Architecture changes from
  startup-only loading to an agent-owned application/configuration port with
  atomic persistence and live scheduler reload. No database migration is needed.
