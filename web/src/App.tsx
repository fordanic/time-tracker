import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { get } from "./api.ts";
import { ManageView } from "./ManageView.tsx";
import { ReviewView } from "./ReviewView.tsx";
import { SettingsView } from "./SettingsView.tsx";
import { TrackView } from "./TrackView.tsx";
import type { Bootstrap, Reminder, Timer } from "./types.ts";
import { elapsed } from "./utils.ts";

type View = "track" | "review" | "manage" | "settings";

export function App() {
  const [view, setView] = useState<View>("track");
  const [data, setData] = useState<Bootstrap | null>(null);
  const [active, setActive] = useState<Timer | null>(null);
  const [reminder, setReminder] = useState<Reminder | null>(null);
  const [status, setStatus] = useState("Loading local data…");
  const [connected, setConnected] = useState(true);
  const [clock, setClock] = useState(Date.now());
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [viewShortcutArmed, setViewShortcutArmed] = useState(false);
  const viewShortcutArmedRef = useRef(false);
  const viewShortcutTimer = useRef<number | null>(null);

  const refresh = useCallback(async (message?: string) => {
    try {
      const next = await get<Bootstrap>("/api/bootstrap");
      setData(next);
      setActive(next.active);
      setReminder(next.reminder);
      setConnected(true);
      setStatus(message ?? "Local data is up to date.");
    } catch (error) {
      setConnected(false);
      setStatus(
        error instanceof Error ? error.message : "Local agent unavailable",
      );
    }
  }, []);

  useEffect(() => void refresh(), [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      const target = event.target;
      const editable =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      const inDialog =
        target instanceof HTMLElement &&
        Boolean(target.closest('[role="dialog"], dialog'));
      const destination: Record<string, View> = {
        t: "track",
        r: "review",
        m: "manage",
        s: "settings",
      };
      const disarmViewShortcut = () => {
        viewShortcutArmedRef.current = false;
        setViewShortcutArmed(false);
        if (viewShortcutTimer.current !== null) {
          window.clearTimeout(viewShortcutTimer.current);
          viewShortcutTimer.current = null;
        }
      };

      if (event.repeat || event.isComposing) return;
      if (
        event.key === "Escape" &&
        editable &&
        !inDialog &&
        !event.altKey &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.shiftKey
      ) {
        event.preventDefault();
        (target as HTMLElement).blur();
        disarmViewShortcut();
        viewShortcutArmedRef.current = true;
        setViewShortcutArmed(true);
        viewShortcutTimer.current = window.setTimeout(disarmViewShortcut, 1500);
        return;
      }

      const next = destination[event.key.toLowerCase()];
      if (viewShortcutArmedRef.current) {
        disarmViewShortcut();
        if (next && !event.altKey && !event.ctrlKey && !event.metaKey) {
          event.preventDefault();
          setView(next);
        }
        return;
      }

      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (editable) return;
      if (event.key === "?") {
        event.preventDefault();
        setShortcutsOpen((open) => !open);
        return;
      }
      if (next) {
        event.preventDefault();
        setView(next);
      }
    };
    window.addEventListener("keydown", listener);
    return () => {
      window.removeEventListener("keydown", listener);
      if (viewShortcutTimer.current !== null)
        window.clearTimeout(viewShortcutTimer.current);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let failures = 0;
    let timeout = 0;
    const poll = async () => {
      if (document.visibilityState === "hidden") {
        timeout = window.setTimeout(poll, 2000);
        return;
      }
      try {
        const next = await get<{
          active: Timer | null;
          reminder: Reminder | null;
        }>("/api/state");
        if (cancelled) return;
        setActive(next.active);
        setReminder(next.reminder);
        setConnected(true);
        failures = 0;
      } catch {
        if (cancelled) return;
        setConnected(false);
        failures += 1;
        setStatus(
          "Connection unavailable. Displaying the last confirmed state.",
        );
      }
      timeout = window.setTimeout(poll, Math.min(30_000, 2000 * 2 ** failures));
    };
    timeout = window.setTimeout(poll, 2000);
    const refocus = () => {
      window.clearTimeout(timeout);
      void poll();
    };
    window.addEventListener("focus", refocus);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      window.removeEventListener("focus", refocus);
    };
  }, []);

  return (
    <div class="app-shell">
      <a class="skip-link" href="#main-content">
        Skip to content
      </a>
      <header class="topbar">
        <div>
          <span class="eyebrow">LOCAL · PRIVATE</span>
          <strong class="brand">Time Tracker</strong>
        </div>
        <span class={connected ? "connection ok" : "connection bad"}>
          <span aria-hidden="true">●</span>{" "}
          {connected ? "Connected" : "Unavailable"}
        </span>
      </header>

      <section class="active-shell" aria-label="Active timer">
        {active ? (
          <>
            <div>
              <span class="eyebrow">TRACKING NOW</span>
              <h1>
                {active.project} <span>/ {active.activity}</span>
              </h1>
              <p>{active.note || "No note"}</p>
            </div>
            <output class="elapsed" aria-label="Elapsed time">
              {elapsed(active.started_at, clock)}
            </output>
          </>
        ) : (
          <div>
            <span class="eyebrow">READY</span>
            <h1>No active timer</h1>
            <p>Choose recent work or enter a new project and activity.</p>
          </div>
        )}
      </section>

      <nav class="view-nav" aria-label="Main views">
        {(["track", "review", "manage", "settings"] as const).map((item) => (
          <button
            key={item}
            aria-label={item[0]?.toUpperCase() + item.slice(1)}
            class={view === item ? "selected" : ""}
            aria-current={view === item ? "page" : undefined}
            onClick={() => setView(item)}
          >
            <kbd aria-hidden="true">{item[0]?.toUpperCase()}</kbd>
            {item[0]?.toUpperCase()}
            {item.slice(1)}
          </button>
        ))}
      </nav>

      <details
        class="shortcut-help"
        open={shortcutsOpen}
        onToggle={(event) => setShortcutsOpen(event.currentTarget.open)}
      >
        <summary>
          Keyboard shortcuts <kbd>?</kbd>
        </summary>
        <div>
          <span>
            <kbd>1–5</kbd> select recent work
          </span>
          <span>
            <kbd>Enter</kbd> confirm selected work
          </span>
          <span>
            <kbd>G</kbd> Start / switch
          </span>
          <span>
            <kbd>U</kbd> Update active
          </span>
          <span>
            <kbd>X</kbd> Stop
          </span>
          <span>
            <kbd>Ctrl/⌘ + Enter</kbd> Start / switch while editing
          </span>
          <span>
            <kbd>Ctrl/⌘ + Shift + Enter</kbd> Update while editing
          </span>
          <span>
            <kbd>Ctrl/⌘ + Alt/⌥ + Enter</kbd> Stop while editing
          </span>
          <span>
            <kbd>T</kbd> Track
          </span>
          <span>
            <kbd>R</kbd> Review
          </span>
          <span>
            <kbd>M</kbd> Manage
          </span>
          <span>
            <kbd>S</kbd> Settings
          </span>
          <span>
            <kbd>Esc, T/R/M/S</kbd> change view while editing
          </span>
        </div>
      </details>

      {viewShortcutArmed && (
        <div class="view-shortcut-ready" role="status" aria-live="polite">
          View shortcut ready: press <kbd>T</kbd>, <kbd>R</kbd>, <kbd>M</kbd>,
          or <kbd>S</kbd>.
        </div>
      )}

      <div class="status" role="status" aria-live="polite">
        {status}
      </div>

      <main id="main-content">
        {!data ? (
          <section class="panel">
            <p>Loading…</p>
          </section>
        ) : view === "track" ? (
          <TrackView
            data={{ ...data, active, reminder }}
            connected={connected}
            announce={setStatus}
            refresh={refresh}
          />
        ) : view === "review" ? (
          <ReviewView
            data={data}
            connected={connected}
            announce={setStatus}
            refresh={refresh}
          />
        ) : view === "manage" ? (
          <ManageView
            data={data}
            connected={connected}
            announce={setStatus}
            refresh={refresh}
          />
        ) : (
          <SettingsView
            data={data}
            connected={connected}
            announce={setStatus}
            refresh={refresh}
          />
        )}
      </main>
    </div>
  );
}
