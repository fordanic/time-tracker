# Focused Track, Review, Manage, and Settings views

**Status:** Implemented

## Purpose

Separate everyday capture, historical review, archive management, and settings
information so later correction and reporting controls do not make one screen
progressively denser, while keeping the current timer continuously visible.

## Required behavior

- Provide four pointer- and keyboard-addressable views in this order: **Track**,
  **Review**, **Manage**, and **Settings**. Use `F1` through `F4` respectively and
  show those shortcuts in the view selector and in-app shortcut help.
- Keep the active-timer strip, its live elapsed duration, pending reminder prompt,
  and shared success/error message visible while any view is selected.
- Put the quick switch deck and pending action, normal project/activity/note
  capture, and separate current-timer Stop and Update controls in Track.
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

## Invariants and error handling

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

## Acceptance criteria

1. On launch, Track is selected and only its view-specific controls are visible;
   `F1` through `F4` and pointer selection each activate the corresponding view.
2. A running timer's project, activity, start time, note, and increasing elapsed
   duration remain visible in Track, Review, Manage, and Settings.
3. Quick-switch and normal capture behavior operate in Track,
   history/summary/export behavior operates in Review, and project/activity
   archiving operates from the dedicated Manage inputs.
4. View changes preserve capture values, review mode, export path and overwrite
   confirmation, Manage selections, the current message, and pending reminders.
5. Existing `F5` through `F10` shortcuts retain their actions, including when the
   corresponding controls are outside the selected view.
6. Textual workflow tests cover initial selection, pointer and keyboard view
   navigation, focus, control ownership, persistent timer visibility, state
   preservation, and retained action shortcuts.

## Documentation impact

- Neither the top-level requirements nor the architecture changes. This is a TUI
  presentation restructure within the existing interface and agent boundary and
  requires no protocol or schema migration.
