# Local responsive web GUI

**Status:** Approved

## Purpose

Provide a responsive, same-machine web interface with feature parity to the TUI
while preserving Time Tracker's local authority, keyboard efficiency, durable
timer behavior, and background-agent ownership. The TUI remains the default
interface and the web GUI is an explicit alternative.

## Required behavior

- `time-tracker --web` starts the existing background agent when needed, binds
  only to `127.0.0.1:47831`, and opens the default browser after the server is
  ready. `--no-open` suppresses browser launch and prints the ready URL;
  `--port PORT` explicitly replaces the stable default and is valid only with
  `--web`. An unavailable selected port fails without opening a browser or
  silently choosing another port. Browser-open failure reports the URL and leaves
  the server running. `Ctrl+C` stops the web server but not the agent or timer.
- Keep the ordinary `time-tracker` command as the TUI. Reject simultaneous TUI
  and web foreground clients with a concise conflict instead of racing the
  single-client protocol. Closing either foreground leaves the agent, active
  timer, and reminders running.
- Serve a responsive application usable from 320-pixel phone-sized viewports to
  desktop widths. Use a persistent active-timer shell and four views in order:
  Track, Review, Manage, and Settings. Responsive reflow must preserve entered
  values, selected rows or targets, filters, and pending confirmations.
- Keep active project, activity, local start time, note, and live elapsed duration
  visible across views. Restore the original active entry after browser or server
  restart without inventing a stop time or resetting its reminder interval.
- Track provides the five-item recent-work deck, deliberate selection and
  confirmation, a separate quick-switch note, classified Start/Switch/Restart or
  disabled no-op behavior, manual project/activity/note capture, Stop, Update
  active details, reminders, Still active, Snooze, and today's completed total.
  Selecting deck work by pointer, number key, or arrow navigation copies its
  project and activity into the manual capture fields without changing either
  note. After deck selection, `Tab` moves directly to its optional note and
  `Enter` from either the selected deck item or its note confirms the classified
  action. Both deck and manual capture show whether the current input will start,
  switch, restart, or make no change before confirmation.
- Review provides one shared inclusive local-date/project/activity filter that
  refreshes automatically after a change, without a separate apply action; All
  time, Today, This week, This month, and custom date choices; completed-entry,
  daily-summary, and range-total representations; local-day grouping and
  midnight splitting; completed-entry selection, correction, missed-time
  creation, confirmed permanent deletion, and matching filtered export with
  overwrite confirmation. Correction and missed-time forms use a compact,
  responsive multi-column layout and the same project/activity suggestion
  controls as Track. Export accepts a server-local destination path, just like
  the TUI; it is not a browser download, and it never silently replaces an
  existing file.
- Manage presents selectable and archived projects and activities in their
  hierarchy. It supports exact-target archive confirmation, restore under the
  existing parent/child rules, and explicit creation of projects and activities
  without starting a timer.
- Settings edits and live-applies inactive and active reminder enables and
  intervals, weekly window, snooze duration, idle-triggered reminders and
  threshold, and export delimiter. It shows idle-detection availability and the
  configuration path.
- The web appearance choice is browser-local and limited to System, Light, and
  Dark. The stable default origin preserves it between launches. An explicit port
  has its own browser-local preference. It neither reads nor overwrites the
  persisted Textual palette.
- Preserve keyboard-only use through native focus order and controls. Number keys
  `1` through `5` select and focus recent work only when focus is outside an
  editable control. `T`, `R`, `M`, and `S` open Track, Review, Manage, and
  Settings from outside editable controls; `?` toggles visible web shortcut help.
  From an editable control outside a dialog workflow, `Escape` removes focus from
  that control and arms a visible 1.5-second view chord: the following `T`, `R`,
  `M`, or `S` opens the corresponding view. Another key or expiry cancels the
  chord. Escape retains its native behavior inside dialog workflows.
  On Track, `G` starts or switches the selected quick work, or the manual entry
  when no quick work is selected; `U` updates the active entry; and `X` stops it.
  These single-key action shortcuts apply only outside editable controls. From
  an editable Track control, `Escape` removes focus so the ordinary single-key
  shortcuts can be used; there are no `Ctrl`/`Command` action equivalents. All
  action shortcuts expose disabled-state feedback without invoking a mutation
  and ignore key repeat and input-method composition. Enter or Space activates
  focused controls. Do not reuse the TUI function-key map or intercept browser-
  or operating-system-reserved shortcuts.
- Keep clear vertical separation between the quick-switch note, action status,
  and Apply selected action, and between each Manage creation input and its
  Create action.
- A Review entry editor captures whether it is correcting a specific entry or
  adding missed time when it opens. Save must retain that operation and, for a
  correction, the entry identity even if an automatic Review refresh changes or
  clears the current row selection.
- Favor a compact information-dense presentation on desktop through smaller type,
  spacing, and margins while retaining readable reflow and 44-pixel touch targets
  in narrow layouts.
- Use pointer and touch controls with targets of at least 44 CSS pixels in narrow
  layouts. Use a table for completed entries where it fits and readable entry
  cards on narrow screens. Focused correction, missed-time, archive, delete, and
  overwrite flows use accessible dialogs or narrow-screen sheets.

## Invariants and error handling

- The background agent remains the only SQLite writer and owner of timer and
  reminder state. The browser never connects to SQLite or agent IPC. The Python
  web adapter calls the same agent protocol and shared application projections as
  the TUI and does not reimplement timer, overlap, archive, reminder, date, or
  export rules.
- One web process owns one authenticated IPC client and serializes all calls.
  Blocking IPC work runs outside the ASGI event loop. Multiple tabs may use that
  server but do not become independent agent-protocol clients. In this feature,
  “foreground client” means a process connected to the agent protocol, not an HTTP
  tab.
- Report success only from the canonical response returned after the agent has
  committed a mutation. A timeout, disconnect, rejected request, or validation
  error must not be presented as success.
- Poll only compact authoritative state while the document is visible, pause in a
  hidden tab, refresh immediately on focus regain, and derive interim elapsed
  display from the aware persisted start instant. A poll failure retains the last
  successful read-only state, marks the connection unavailable, disables
  mutations, and retries with bounded backoff.
- Bind only to IPv4 loopback; LAN and remote binding are not configurable. Accept
  only `Host: 127.0.0.1:<selected-port>` and mutation Origin
  `http://127.0.0.1:<selected-port>`. Do not emit permissive CORS headers.
- Generate a fresh 256-bit URL-safe token at each server launch, embed it in the
  uncached same-origin HTML as `<meta name="time-tracker-token">`, and require its
  exact value in `X-Time-Tracker-Token` for every state-changing request. State
  changes accept JSON only up to 64 KiB and are never exposed as `GET` routes.
- Serve only same-origin packaged assets with a restrictive Content Security
  Policy, denied framing, same-origin resource isolation, and MIME-sniffing
  protection. Do not load runtime code, fonts, analytics, telemetry, or other
  assets from a network origin.
- Do not put the launch token, project/activity names, notes, timestamps, entry
  data, or reminder content in URLs or access logs.
- Use one JSON response envelope with either canonical data or a structured
  stable error code, concise user-safe message, and optional field name. Browser
  behavior must not depend on parsing exception text.
- All existing naming, note normalization, selectable-target, archive, timestamp,
  half-open overlap, derived-duration, date-filter, export quoting, overwrite,
  reminder, snooze, idle, and committed-before-success rules remain unchanged.
- Version 1 parity is exhaustively defined by this file, the top-level
  requirements, and the approved feature requirements indexed on August 12,
  2026. A later feature must explicitly state whether and how it extends each
  supported interface rather than silently expanding this baseline.
- Invalid fields receive accessible inline errors and retain the user's input for
  correction. Global connection or persistence failures are announced in a
  persistent screen-reader status region without clearing unrelated view state.

## Acceptance criteria

1. The default command still launches the TUI. The exact web flags, stable port,
   readiness, browser-open and failure behavior match this requirement and leave
   the agent and active timer running when the web server closes.
2. Source-browser end-to-end tests start, switch or restart, reconnect to the
   original active entry, edit its details without resetting time, stop it,
   retrieve or act on a reminder, and exercise Review, Manage, and Settings with
   every successful mutation already durable. The frozen package smoke loads its
   embedded shell and proves start, server close, recovery, stop, and agent
   shutdown.
3. Track implements all recent, manual, classified action, reminder, active-edit,
   and today's-total behaviors with matching agent results and no duplicated
   business classification in TypeScript. Deck selection has one roving tab stop,
   mirrors the selected project and activity into manual capture, tabs next to the
   quick note, and confirms from the selected item or note with Enter;
   authoritative action previews update for deck and manual input. Visible `G`,
   `U`, and `X` shortcuts perform Start/Switch, Update, and Stop respectively only
   when their corresponding Track action is available. `Escape` leaves an
   editable Track control so those same shortcuts become available, without
   defining `Ctrl`/`Command` action equivalents. Direct view shortcuts remain
   inactive while editing, while the timed `Escape` view chord changes views from
   those controls without intercepting dialog Escape behavior.
4. Review implements all three representations, shared filters, local-day splits,
   correction, missed time, deletion, and matching exports, including offset-aware
   input, overlap rejection, header-only empty export, and overwrite confirmation.
   Filter changes apply automatically, and entry forms retain values while
   presenting project/activity suggestions consistently with Track. Save invokes
   the captured correction or creation operation even if an automatic query has
   refreshed the visible Review selection.
5. Manage implements hierarchical create, exact archive confirmation, and restore
   semantics, including active-timer preservation and archived-parent rejection.
6. Settings round-trips every supported durable value, live-reloads the reminder
   schedule under existing rules, reports idle availability, preserves unrelated
   TOML tables, and keeps browser appearance independent of the TUI palette.
7. At 320, 720, and 1280 CSS pixels, compact layouts have no horizontal page
   overflow, clipped essential content, or lost state. The quick-switch action
   sequence and Manage creation controls retain clear vertical separation.
   Keyboard-only and touch workflows, visible focus, labels, error associations,
   status announcements, 200% zoom, reduced motion, and light/dark contrast meet
   WCAG AA thresholds of 4.5:1 for normal text and 3:1 for large text and
   essential interface boundaries.
8. Security tests reject non-loopback configuration, unexpected Host, cross-origin
   mutations, missing or incorrect launch tokens, non-JSON or oversized mutation
   bodies, framing, and sensitive URL/log data. Third-party runtime requests are
   absent.
9. The web process remains one serialized foreground IPC client; simultaneous TUI
   and web launch is rejected clearly, while multiple browser tabs cannot create
   concurrent agent connections or overlapping timers.
10. Python unit/integration tests; `npm run format:check`, `npm run lint`,
    `npm run typecheck`, `npm run test`, `npm run test:e2e`, and `npm run build`;
    existing TUI regression tests; deterministic assets; and the packaged web
    lifecycle pass on Linux, Windows, and macOS before release status is complete.
    Chromium is the automated release-gating engine. Safari, Firefox, and WSL are
    interactive validation targets whose gaps are recorded in README Status.

## Documentation impact

- Approved by the maintainer on August 12, 2026 as an intentional change to the
  former GUI/web product exclusion and network-service architecture boundary.
- Update `docs/top-level-requirements.md`, `docs/architecture.md`, the feature
  index, README usage/status, build guidance, and packaged validation guidance.
- The approved design and implementation sequence are retained in
  `docs/web-gui-proposal.md` for review context; this file is the authoritative
  feature-specific behavior.
