import { useEffect, useRef, useState } from "preact/hooks";
import { post } from "./api.ts";
import { ProjectActivityFields } from "./ProjectActivityFields.tsx";
import type { Bootstrap, Timer } from "./types.ts";
import { duration } from "./utils.ts";

interface Props {
  data: Bootstrap;
  connected: boolean;
  announce: (message: string) => void;
  refresh: (message?: string) => Promise<void>;
}

type TrackAction = "start" | "switch" | "restart" | "already_tracking";

function actionCopy(action: TrackAction | null, ready: boolean) {
  if (!ready) return "Choose a project and activity to preview the action.";
  if (!action) return "Checking action…";
  if (action === "switch") return "Will switch from the current timer.";
  if (action === "restart") return "Will restart this timer with the new note.";
  if (action === "already_tracking")
    return "No change — this work is already active.";
  return "Will start a new timer.";
}

function actionLabel(action: TrackAction | null, ready = true) {
  if (!ready) return "Waiting";
  if (action === "already_tracking") return "No change";
  if (!action) return "Checking";
  return `${action[0]?.toUpperCase()}${action.slice(1)}`;
}

export function TrackView({ data, connected, announce, refresh }: Props) {
  const [recentIndex, setRecentIndex] = useState<number | null>(null);
  const [quickNote, setQuickNote] = useState("");
  const [project, setProject] = useState("");
  const [activity, setActivity] = useState("");
  const [note, setNote] = useState("");
  const [quickAction, setQuickAction] = useState<TrackAction | null>(null);
  const [manualAction, setManualAction] = useState<TrackAction | null>(null);
  const [busy, setBusy] = useState(false);
  const recentButtons = useRef<Array<HTMLButtonElement | null>>([]);
  const disabled = busy || !connected;
  const recent =
    recentIndex === null ? null : (data.recent[recentIndex] ?? null);
  const activeKey = data.active
    ? `${data.active.entry_id}\u0000${data.active.project}\u0000${data.active.activity}\u0000${data.active.note ?? ""}`
    : "";

  useEffect(() => {
    if (!recent) {
      setQuickAction(null);
      return;
    }
    let cancelled = false;
    setQuickAction(null);
    const timeout = window.setTimeout(async () => {
      try {
        const result = await post<{ action: TrackAction }>(
          "/api/track/classify",
          {
            project: recent.project,
            activity: recent.activity,
            note: quickNote || null,
            quick: true,
          },
        );
        if (!cancelled) setQuickAction(result.action);
      } catch {
        if (!cancelled) setQuickAction(null);
      }
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [activeKey, quickNote, recent]);

  useEffect(() => {
    if (!project || !activity) {
      setManualAction(null);
      return;
    }
    let cancelled = false;
    setManualAction(null);
    const timeout = window.setTimeout(async () => {
      try {
        const result = await post<{ action: TrackAction }>(
          "/api/track/classify",
          {
            project,
            activity,
            note: note || null,
            quick: false,
          },
        );
        if (!cancelled) setManualAction(result.action);
      } catch {
        if (!cancelled) setManualAction(null);
      }
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [activity, activeKey, note, project]);

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
        setRecentIndex(index);
        setQuickAction(null);
        window.requestAnimationFrame(() =>
          recentButtons.current[index]?.focus(),
        );
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [data.recent]);

  const applyStart = async (
    targetProject: string,
    targetActivity: string,
    targetNote: string,
    quick: boolean,
  ) => {
    setBusy(true);
    try {
      const classified = await post<{ action: TrackAction }>(
        "/api/track/classify",
        {
          project: targetProject,
          activity: targetActivity,
          note: targetNote || null,
          quick,
        },
      );
      if (classified.action === "already_tracking") {
        announce("That project, activity, and note are already active.");
        if (quick) setQuickAction("already_tracking");
        else setManualAction("already_tracking");
        return;
      }
      await post<{ active: Timer }>("/api/timer/start", {
        project: targetProject,
        activity: targetActivity,
        note: targetNote || null,
      });
      setNote("");
      setQuickNote("");
      setRecentIndex(null);
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
        <div class="recent-deck" role="radiogroup" aria-label="Recent work">
          {data.recent.length ? (
            data.recent.slice(0, 5).map((item, index) => (
              <button
                key={`${item.project}/${item.activity}`}
                ref={(element) => {
                  recentButtons.current[index] = element;
                }}
                type="button"
                role="radio"
                aria-checked={recentIndex === index}
                tabIndex={
                  recentIndex === index || (recentIndex === null && index === 0)
                    ? 0
                    : -1
                }
                class={recentIndex === index ? "recent selected" : "recent"}
                onClick={() => {
                  setRecentIndex(index);
                  setQuickAction(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && recentIndex === index) {
                    event.preventDefault();
                    void applyStart(
                      item.project,
                      item.activity,
                      quickNote,
                      true,
                    );
                    return;
                  }
                  if (event.key !== "ArrowDown" && event.key !== "ArrowUp")
                    return;
                  event.preventDefault();
                  const direction = event.key === "ArrowDown" ? 1 : -1;
                  const next =
                    (index + direction + data.recent.slice(0, 5).length) %
                    data.recent.slice(0, 5).length;
                  setRecentIndex(next);
                  setQuickAction(null);
                  recentButtons.current[next]?.focus();
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
            onInput={(event) => {
              setQuickNote(event.currentTarget.value);
              setQuickAction(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && recent) {
                event.preventDefault();
                void applyStart(
                  recent.project,
                  recent.activity,
                  quickNote,
                  true,
                );
              }
            }}
          />
        </label>
        <div
          class={`action-preview ${quickAction ?? "pending"}`}
          role="status"
          aria-live="polite"
        >
          <strong>{actionLabel(quickAction, Boolean(recent))}</strong>
          <span>{actionCopy(quickAction, Boolean(recent))}</span>
        </div>
        <button
          class="primary full"
          disabled={disabled || !recent || quickAction === "already_tracking"}
          onClick={() =>
            recent &&
            void applyStart(recent.project, recent.activity, quickNote, true)
          }
        >
          {quickAction && quickAction !== "already_tracking"
            ? `${actionLabel(quickAction)} selected work`
            : "Apply selected work"}
        </button>
      </section>

      <section class="panel capture-panel">
        <span class="eyebrow">MANUAL CAPTURE</span>
        <h2>What are you working on?</h2>
        <div class="field-row">
          <ProjectActivityFields
            idPrefix="track"
            project={project}
            activity={activity}
            projects={data.projects}
            activities={data.activities}
            onProjectChange={(value) => {
              setProject(value);
              setManualAction(null);
            }}
            onActivityChange={(value) => {
              setActivity(value);
              setManualAction(null);
            }}
          />
        </div>
        <label>
          Note <span>optional</span>
          <input
            value={note}
            onInput={(event) => {
              setNote(event.currentTarget.value);
              setManualAction(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && project && activity) {
                event.preventDefault();
                void applyStart(project, activity, note, false);
              }
            }}
          />
        </label>
        <div
          class={`action-preview ${manualAction ?? "pending"}`}
          role="status"
          aria-live="polite"
        >
          <strong>
            {actionLabel(manualAction, Boolean(project && activity))}
          </strong>
          <span>{actionCopy(manualAction, Boolean(project && activity))}</span>
        </div>
        <div class="button-row">
          <button
            class="primary"
            disabled={
              disabled ||
              !project ||
              !activity ||
              manualAction === "already_tracking"
            }
            onClick={() => void applyStart(project, activity, note, false)}
          >
            {manualAction && manualAction !== "already_tracking"
              ? actionLabel(manualAction)
              : "Start / switch"}
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
