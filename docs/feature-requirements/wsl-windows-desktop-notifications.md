# WSL notification delivery to the Windows desktop

**Status:** Implemented

## Purpose

Deliver native reminders to the Windows desktop when the application runs inside
the Windows Subsystem for Linux. The Linux build selects a D-Bus notification
backend from the reported platform alone, but a WSL distribution provides no
notification daemon, so `org.freedesktop.Notifications` is unavailable and every
native reminder fails. The agent logs the failure and retains the prompt for a
connected TUI, which means a WSL user is reminded only while the TUI is open —
losing exactly the case reminders exist for. WSL is a routine Linux development
and usage host whose desktop is Windows, so the reminder must reach that desktop
through a narrow host adapter rather than a new product surface.

## Required behavior

- Detect a WSL host from the running kernel rather than from environment
  variables a user may have altered: the platform reports Linux, the kernel
  release names Microsoft, and Windows interop is registered. Treat a
  non-interop WSL session as not supported by this adapter.
- On a detected WSL host, deliver the reminder as a Windows toast notification
  through the Windows PowerShell interpreter's WinRT notification API. Prefer
  the Windows PowerShell 5.1 interpreter, which starts substantially faster than
  PowerShell 7 from WSL.
- Present the same reminder content as every other platform, including the
  active, inactive, and idle-reason titles and messages and the configured idle
  threshold. This adapter changes delivery only.
- Publish a stable application identity so the toast is attributed to Time
  Tracker and the user can manage it in the Windows notification settings.
  Register the identity idempotently in the current user's registry with a
  display name, once per agent process, and never require administrator rights,
  a Windows-side installation, or an added third-party dependency.
- The first toast sent from an identity Windows has not seen before is consumed
  while Windows registers that identity. When the adapter registers the identity
  for the first time, dispatch one warm-up notification so a real reminder is not
  the one Windows discards. Its content must be meaningful if Windows does render
  it, and it must occur at most once per identity per user.
- Resolve the interpreter without depending on the inherited `PATH`, because a
  distribution may be configured not to append Windows paths. Fall back to
  translating the Windows system path into a WSL path.
- Bound every interpreter invocation with a timeout so a hung or slow Windows
  process cannot stall the agent's reminder loop or its persistence work.
- If the host is WSL but interop, the interpreter, or the toast dispatch is
  unavailable, attempt the existing desktop-service delivery, so a user who runs
  their own Linux notification daemon inside WSL keeps working delivery.

## Invariants and error handling

- Reminder text is passed to the interpreter as data through the process
  environment, using WSL's environment-sharing variable, and never interpolated
  into executable script source or into a shell command line. This preserves the
  rule already established for the macOS adapter: user-controlled reminder text
  must not become executable content.
- The only durable machine state this adapter creates is the current-user
  application-identity registry entry and its display name. It writes no
  machine-wide state, no scheduled task, no shortcut, and no file outside the
  application's own directories.
- Delivery is decided by the interpreter's exit status. Informational
  interpreter output on the error stream, such as the serialized progress record
  emitted on first module use, must not be treated as a delivery failure.
- Delivery failure, timeout, and interop absence leave persisted timer state, the
  reminder schedule, and its monotonic deadlines unchanged. They are reported
  through the existing agent log, and the due reminder remains available to a
  connected TUI exactly as on other platforms. The adapter must not retry a
  failed dispatch in a loop or emit a failure notification.
- The background process remains the only component that sends notifications and
  the only database writer. The TUI must not invoke the interpreter or detect the
  host independently.
- Host detection, interpreter resolution, command construction, environment
  assembly, and failure mapping are injected or otherwise substitutable so unit
  tests cover them deterministically on any platform without starting a Windows
  process.
- This feature covers notification delivery only. It does not add Windows-side
  idle detection. On WSL, WSLg's X server provides no screen-saver extension, so
  the existing X11 idle adapter cannot report idle duration; per the approved
  opt-in idle-reminder requirement, idle detection must report itself as
  unavailable in Settings in that session rather than appearing available until
  its first failing poll.

## Acceptance criteria

1. On a WSL host with interop, a due reminder produces one Windows toast
   notification attributed to Time Tracker, with the same title and message the
   other platforms present, including the idle reason and configured threshold.
2. Host detection identifies WSL from kernel release and interop registration,
   reports a plain Linux desktop and a native Windows or macOS host as not being
   a WSL host, and does not depend on `WSL_DISTRO_NAME` or `WSL_INTEROP` alone.
3. Reminder text containing quotes, backticks, dollar signs, newlines,
   backslashes, and non-ASCII characters is delivered literally and never
   evaluated. No test or delivery path places reminder text in script source or
   in a shell command line.
4. The application identity is registered idempotently for the current user with
   its display name, repeated agent starts do not duplicate or alter it, and the
   first-time registration is followed by exactly one warm-up notification.
5. A missing interpreter, absent interop, non-zero exit status, or exceeded
   timeout raises a delivery failure that leaves the active timer, entry values,
   reminder schedule, and monotonic deadlines unchanged, is recorded once in the
   agent log, and still leaves the due reminder retrievable by a connected TUI.
6. Informational interpreter output on the error stream with a zero exit status
   is treated as success.
7. The interpreter is resolved when Windows paths are absent from `PATH`.
8. Unit tests cover host detection, interpreter resolution, command and
   environment construction, text-as-data handling, identity registration and
   warm-up, timeout, and failure mapping without starting a Windows process. An
   interactive WSL smoke verifies that a reminder dispatched with no TUI open
   appears on the Windows desktop.

## Documentation impact

- Architecture records the WSL host adapter as a technical choice alongside the
  existing Linux, Windows, and macOS notification adapters, and adds WSL to the
  interactive notification-delivery validation.
- The top-level requirements do not change. Reminder behavior, configuration, and
  the supported operating systems are unchanged, and the existing rules to keep
  application logic independent of notification libraries and to isolate
  operating-system behavior behind narrow adapters already authorize this
  adapter.
- No database migration and no configuration schema change are required.
