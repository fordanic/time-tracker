import { useCallback, useEffect, useState } from "preact/hooks";
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
            class={view === item ? "selected" : ""}
            aria-current={view === item ? "page" : undefined}
            onClick={() => setView(item)}
          >
            {item[0]?.toUpperCase()}
            {item.slice(1)}
          </button>
        ))}
      </nav>

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
