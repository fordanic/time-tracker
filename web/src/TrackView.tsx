import { useEffect, useMemo, useState } from "preact/hooks";
import { post } from "./api.ts";
import type { Bootstrap, RecentActivity, Timer } from "./types.ts";
import { duration } from "./utils.ts";

interface Props {
  data: Bootstrap;
  connected: boolean;
  announce: (message: string) => void;
  refresh: (message?: string) => Promise<void>;
}

export function TrackView({ data, connected, announce, refresh }: Props) {
  const [recent, setRecent] = useState<RecentActivity | null>(null);
  const [quickNote, setQuickNote] = useState("");
  const [project, setProject] = useState("");
  const [activity, setActivity] = useState("");
  const [note, setNote] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const disabled = busy || !connected;
  const activities = useMemo(
    () => data.activities[project] ?? [],
    [data, project],
  );

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement
      )
        return;
      const index = Number(event.key) - 1;
      const selection = data.recent[index];
      if (index >= 0 && selection) {
        event.preventDefault();
        setRecent(selection);
        setPendingAction(null);
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [data.recent]);

  const applyStart = async (
    targetProject: string,
    targetActivity: string,
    targetNote: string,
  ) => {
    setBusy(true);
    try {
      const classified = await post<{ action: string }>("/api/track/classify", {
        project: targetProject,
        activity: targetActivity,
        note: targetNote || null,
        quick:
          recent?.project === targetProject &&
          recent?.activity === targetActivity,
      });
      if (classified.action === "already_tracking") {
        announce("That project, activity, and note are already active.");
        setPendingAction("No change");
        return;
      }
      setPendingAction(classified.action);
      await post<{ active: Timer }>("/api/timer/start", {
        project: targetProject,
        activity: targetActivity,
        note: targetNote || null,
      });
      setNote("");
      setQuickNote("");
      setRecent(null);
      await refresh(
        `${classified.action[0]?.toUpperCase()}${classified.action.slice(1)} saved.`,
      );
    } catch (error) {
      announce(
        error instanceof Error ? error.message : "Tracking action failed",
      );
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await post("/api/timer/stop");
      await refresh("Timer stopped and saved.");
    } catch (error) {
      announce(error instanceof Error ? error.message : "Stop failed");
    } finally {
      setBusy(false);
    }
  };

  const update = async () => {
    setBusy(true);
    try {
      await post("/api/timer/edit", {
        project: project || data.active?.project || "",
        activity: activity || data.active?.activity || "",
        note: note || null,
      });
      await refresh("Active details updated without restarting time.");
    } catch (error) {
      announce(error instanceof Error ? error.message : "Update failed");
    } finally {
      setBusy(false);
    }
  };

  const reminderAction = async (kind: "confirm" | "snooze") => {
    setBusy(true);
    try {
      await post(`/api/reminder/${kind}`);
      await refresh(
        kind === "confirm" ? "Active work confirmed." : "Reminder snoozed.",
      );
    } catch (error) {
      announce(
        error instanceof Error ? error.message : "Reminder action failed",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="track-grid">
      <section class="panel deck-panel">
        <div class="section-heading">
          <div>
            <span class="eyebrow">QUICK SWITCH</span>
            <h2>Recent work</h2>
          </div>
          <span class="hint">Keys 1–5</span>
        </div>
        <div class="recent-deck" aria-label="Recent work">
          {data.recent.length ? (
            data.recent.slice(0, 5).map((item, index) => (
              <button
                key={`${item.project}/${item.activity}`}
                class={recent === item ? "recent selected" : "recent"}
                onClick={() => {
                  setRecent(item);
                  setPendingAction(null);
                }}
              >
                <kbd>{index + 1}</kbd>
                <span>
                  <strong>{item.project}</strong>
                  <small>{item.activity}</small>
                </span>
              </button>
            ))
          ) : (
            <p class="muted">Completed activities will appear here.</p>
          )}
        </div>
        <label>
          Quick-switch note <span>optional</span>
          <input
            value={quickNote}
            onInput={(event) => setQuickNote(event.currentTarget.value)}
          />
        </label>
        <button
          class="primary full"
          disabled={disabled || !recent}
          onClick={() =>
            recent &&
            void applyStart(recent.project, recent.activity, quickNote)
          }
        >
          {pendingAction
            ? `${pendingAction} selected work`
            : "Apply selected work"}
        </button>
      </section>

      <section class="panel capture-panel">
        <span class="eyebrow">MANUAL CAPTURE</span>
        <h2>What are you working on?</h2>
        <div class="field-row">
          <label>
            Project
            <input
              list="project-options"
              value={project}
              onInput={(event) => setProject(event.currentTarget.value)}
            />
            <datalist id="project-options">
              {data.projects.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </datalist>
          </label>
          <label>
            Activity
            <input
              list="activity-options"
              value={activity}
              onInput={(event) => setActivity(event.currentTarget.value)}
            />
            <datalist id="activity-options">
              {activities.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </datalist>
          </label>
        </div>
        <label>
          Note <span>optional</span>
          <input
            value={note}
            onInput={(event) => setNote(event.currentTarget.value)}
          />
        </label>
        <div class="button-row">
          <button
            class="primary"
            disabled={disabled || !project || !activity}
            onClick={() => void applyStart(project, activity, note)}
          >
            Start / switch
          </button>
          <button
            disabled={disabled || !data.active}
            onClick={() => void update()}
          >
            Update active
          </button>
          <button
            class="danger"
            disabled={disabled || !data.active}
            onClick={() => void stop()}
          >
            Stop
          </button>
        </div>
        <div class="metric">
          <span>Today’s completed time</span>
          <strong>{duration(data.today_completed_seconds)}</strong>
        </div>
      </section>

      {data.reminder && (
        <section class="panel reminder-panel" aria-labelledby="reminder-title">
          <span class="eyebrow">REMINDER</span>
          <h2 id="reminder-title">
            {data.reminder.kind === "active"
              ? "Still active?"
              : "Ready to track?"}
          </h2>
          <p>
            {data.reminder.reason === "idle"
              ? "Your device has been idle. "
              : ""}
            {data.reminder.project &&
              `${data.reminder.project} / ${data.reminder.activity ?? ""}`}
          </p>
          <div class="button-row">
            {data.reminder.kind === "active" && (
              <button
                class="primary"
                disabled={disabled}
                onClick={() => void reminderAction("confirm")}
              >
                Still active
              </button>
            )}
            <button
              disabled={disabled}
              onClick={() => void reminderAction("snooze")}
            >
              Snooze
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
