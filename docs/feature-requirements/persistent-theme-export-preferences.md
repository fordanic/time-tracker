# Persistent theme and export preferences

**Status:** Implemented

## Purpose

Restore the user's selected theme across launches and support pipe-delimited
exports without making them the default.

## Required behavior

- Persist a selected built-in Textual theme in the human-readable configuration
  and apply it on the next TUI launch.
- Offer every available built-in theme as a Settings choice that applies and
  persists as soon as it is selected, without requiring Save, so the palette is
  reachable without the command palette.
- Keep the Settings choice in step with a theme applied elsewhere, including
  through Textual's command palette.
- Fall back to the built-in default when the saved theme is not available and
  persist the fallback when possible.
- Expose comma and pipe as export-delimiter choices in Settings, with comma as
  the default.
- Apply the configured delimiter to detailed, daily-summary, and range-total
  exports.
- Preserve reminder, theme, and export settings when any one area is saved.

## Invariants and error handling

- Theme selection is presentation-only and never changes timer or reminder
  state.
- Configuration remains strict and atomically replaced; invalid values do not
  overwrite the prior file or live settings.
- Export quoting preserves commas, pipes, quotes, Unicode, and line breaks in
  notes for either delimiter.
- Existing configuration files containing only `[reminders]` continue to load
  with the default theme and comma delimiter.

## Acceptance criteria

1. Selecting another built-in theme, closing the TUI, and reopening it applies
   the same theme.
2. An unknown saved theme falls back safely without preventing launch.
3. Settings round-trip comma and pipe values through TOML and IPC without
   restarting the background process.
4. All three export representations use the chosen delimiter, while comma
   remains the default for existing and absent configurations.
5. Every available palette can be chosen from Settings, applies immediately,
   survives a restart, and the shown choice follows a palette applied elsewhere.
6. Unit, integration, IPC, and Textual tests cover persistence, partial settings
   preservation, fallback, Settings palette selection, live delimiter changes, and
   quoted multiline notes.

## Documentation impact

- Top-level requirements authorize persistent theme and delimiter preferences.
  Architecture records the additional TOML tables and per-export writer setting.
  No database migration is required.
