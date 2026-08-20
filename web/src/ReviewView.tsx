import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { post } from "./api.ts";
import { ProjectActivityFields } from "./ProjectActivityFields.tsx";
import type { Bootstrap, ReviewData, ReviewFilter, Segment } from "./types.ts";
import { duration, localInputValue, offsetInstant } from "./utils.ts";

interface Props {
  data: Bootstrap;
  connected: boolean;
  announce: (message: string) => void;
  refresh: (message?: string) => Promise<void>;
}

const emptyFilter: ReviewFilter = {
  preset: "all_time",
  start_date: null,
  end_date: null,
  project: null,
  activity: null,
};

type EntryEditor = { mode: "correct"; entryId: number } | { mode: "create" };

export function ReviewView({ data, connected, announce, refresh }: Props) {
  const [filter, setFilter] = useState<ReviewFilter>(emptyFilter);
  const [review, setReview] = useState<ReviewData | null>(null);
  const [mode, setMode] = useState<"completed" | "daily" | "range">(
    "completed",
  );
  const [selected, setSelected] = useState<Segment | null>(null);
  const [editor, setEditor] = useState<EntryEditor | null>(null);
  const [entry, setEntry] = useState({
    project: "",
    activity: "",
    started_at: "",
    stopped_at: "",
    note: "",
  });
  const [deletePending, setDeletePending] = useState(false);
  const [destination, setDestination] = useState("");
  const [overwritePending, setOverwritePending] = useState(false);
  const [queryBusy, setQueryBusy] = useState(false);
  const [mutationBusy, setMutationBusy] = useState(false);
  const querySequence = useRef(0);

  const query = async (nextFilter = filter, announceSuccess = false) => {
    const sequence = ++querySequence.current;
    setQueryBusy(true);
    try {
      const result = await post<ReviewData>("/api/review/query", nextFilter);
      if (sequence !== querySequence.current) return;
      setReview(result);
      if (
        selected &&
        !result.groups.some((group) =>
          group.segments.some((item) => item.entry_id === selected.entry_id),
        )
      )
        setSelected(null);
      if (announceSuccess) announce("Review refreshed.");
    } catch (error) {
      if (sequence === querySequence.current)
        announce(error instanceof Error ? error.message : "Review failed");
    } finally {
      if (sequence === querySequence.current) setQueryBusy(false);
    }
  };

  useEffect(() => {
    if (filter.preset === "custom" && (!filter.start_date || !filter.end_date))
      return;
    const timeout = window.setTimeout(() => void query(filter), 220);
    return () => window.clearTimeout(timeout);
  }, [
    filter.activity,
    filter.end_date,
    filter.preset,
    filter.project,
    filter.start_date,
  ]);

  const activities = useMemo(() => {
    if (!filter.project)
      return Array.from(new Set(data.completed.map((item) => item.activity)));
    return Array.from(
      new Set(
        data.completed
          .filter((item) => item.project === filter.project)
          .map((item) => item.activity),
      ),
    );
  }, [data.completed, filter.project]);

  const entryProjects = useMemo(
    () =>
      Array.from(
        new Set([
          ...data.projects,
          ...data.completed.map((item) => item.project),
        ]),
      ),
    [data.completed, data.projects],
  );
  const entryActivities = useMemo(() => {
    const choices: Record<string, string[]> = { ...data.activities };
    for (const item of data.completed) {
      choices[item.project] = Array.from(
        new Set([...(choices[item.project] ?? []), item.activity]),
      );
    }
    return choices;
  }, [data.activities, data.completed]);

  const loadSelected = () => {
    if (!selected) return;
    const source =
      data.completed.find((item) => item.entry_id === selected.entry_id) ??
      selected;
    setEntry({
      project: source.project,
      activity: source.activity,
      started_at: localInputValue(source.started_at),
      stopped_at: localInputValue(source.stopped_at ?? selected.stopped_at),
      note: source.note ?? "",
    });
    setEditor({ mode: "correct", entryId: selected.entry_id });
    setDeletePending(false);
  };

  const startCreate = () => {
    const now = new Date();
    const hourAgo = new Date(now.getTime() - 3_600_000);
    setEntry({
      project: "",
      activity: "",
      started_at: localInputValue(hourAgo.toISOString()),
      stopped_at: localInputValue(now.toISOString()),
      note: "",
    });
    setEditor({ mode: "create" });
  };

  const saveEntry = async () => {
    if (!editor) return;
    const currentEditor = editor;
    setMutationBusy(true);
    try {
      await post(
        currentEditor.mode === "correct"
          ? "/api/review/correct"
          : "/api/review/create",
        {
          ...(currentEditor.mode === "correct"
            ? { entry_id: currentEditor.entryId }
            : {}),
          project: entry.project,
          activity: entry.activity,
          started_at: offsetInstant(entry.started_at),
          stopped_at: offsetInstant(entry.stopped_at),
          note: entry.note || null,
        },
      );
      setEditor(null);
      setSelected(null);
      await refresh(
        currentEditor.mode === "correct"
          ? "Entry correction saved."
          : "Missed time added.",
      );
      await query(filter);
    } catch (error) {
      announce(error instanceof Error ? error.message : "Entry save failed");
    } finally {
      setMutationBusy(false);
    }
  };

  const deleteEntry = async () => {
    if (!selected) return;
    if (!deletePending) {
      setDeletePending(true);
      announce(
        `Confirm permanent deletion of ${selected.project} / ${selected.activity}.`,
      );
      return;
    }
    setMutationBusy(true);
    try {
      await post("/api/review/delete", { entry_id: selected.entry_id });
      setDeletePending(false);
      setSelected(null);
      await refresh("Completed entry permanently deleted.");
      await query(filter);
    } catch (error) {
      announce(error instanceof Error ? error.message : "Delete failed");
    } finally {
      setMutationBusy(false);
    }
  };

  const exportReview = async () => {
    setMutationBusy(true);
    try {
      const result = await post<{ count: number; destination: string }>(
        "/api/review/export",
        {
          ...filter,
          representation: mode,
          destination,
          overwrite: overwritePending,
        },
      );
      setOverwritePending(false);
      announce(
        `Exported ${result.count} row${result.count === 1 ? "" : "s"} to ${result.destination}.`,
      );
    } catch (error) {
      if (
        error instanceof Error &&
        "code" in error &&
        error.code === "destination_exists"
      ) {
        setOverwritePending(true);
        announce("Destination exists. Activate export again to replace it.");
      } else announce(error instanceof Error ? error.message : "Export failed");
    } finally {
      setMutationBusy(false);
    }
  };

  return (
    <div class="review-layout">
      <section class="panel filters">
        <div class="section-heading">
          <div>
            <span class="eyebrow">REVIEW</span>
            <h2>Completed time</h2>
          </div>
        </div>
        <div class="filter-grid">
          <label>
            Date range
            <select
              value={filter.preset}
              onChange={(event) =>
                setFilter({
                  ...filter,
                  preset: event.currentTarget.value as ReviewFilter["preset"],
                })
              }
            >
              <option value="all_time">All time</option>
              <option value="today">Today</option>
              <option value="this_week">This week</option>
              <option value="this_month">This month</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          {filter.preset === "custom" && (
            <>
              <label>
                From
                <input
                  type="date"
                  value={filter.start_date ?? ""}
                  onInput={(event) =>
                    setFilter({
                      ...filter,
                      start_date: event.currentTarget.value || null,
                    })
                  }
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  value={filter.end_date ?? ""}
                  onInput={(event) =>
                    setFilter({
                      ...filter,
                      end_date: event.currentTarget.value || null,
                    })
                  }
                />
              </label>
            </>
          )}
          <label>
            Project
            <select
              value={filter.project ?? ""}
              onChange={(event) =>
                setFilter({
                  ...filter,
                  project: event.currentTarget.value || null,
                  activity: null,
                })
              }
            >
              <option value="">All projects</option>
              {Array.from(
                new Set(data.completed.map((item) => item.project)),
              ).map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label>
            Activity
            <select
              value={filter.activity ?? ""}
              onChange={(event) =>
                setFilter({
                  ...filter,
                  activity: event.currentTarget.value || null,
                })
              }
            >
              <option value="">All activities</option>
              {activities.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
        </div>
        <div class="segmented" aria-label="Review representation">
          {(["completed", "daily", "range"] as const).map((item) => (
            <button
              key={item}
              class={mode === item ? "selected" : ""}
              onClick={() => {
                setMode(item);
                setSelected(null);
              }}
            >
              {item === "daily"
                ? "Daily summaries"
                : item === "range"
                  ? "Range totals"
                  : "Entries"}
            </button>
          ))}
        </div>
      </section>

      <section class="panel review-results" aria-busy={queryBusy}>
        {!review ? (
          <p>Loading review…</p>
        ) : mode === "completed" ? (
          <div class="entry-groups">
            {review.groups.length ? (
              review.groups.map((group) => (
                <section key={group.day} class="day-group">
                  <header>
                    <h3>{group.day}</h3>
                    <strong>{duration(group.duration_seconds)}</strong>
                  </header>
                  {group.segments.map((item) => (
                    <button
                      key={`${item.entry_id}-${item.started_at}`}
                      class={
                        selected?.entry_id === item.entry_id
                          ? "entry-card selected"
                          : "entry-card"
                      }
                      onClick={() => {
                        setSelected(item);
                        setDeletePending(false);
                      }}
                    >
                      <span>
                        <strong>
                          {item.project} / {item.activity}
                        </strong>
                        <small>
                          {new Date(item.started_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}{" "}
                          –{" "}
                          {new Date(item.stopped_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </small>
                        <small>{item.note || "No note"}</small>
                      </span>
                      <b>{duration(item.duration_seconds)}</b>
                    </button>
                  ))}
                </section>
              ))
            ) : (
              <p class="muted">No completed entries match this filter.</p>
            )}
          </div>
        ) : mode === "daily" ? (
          <SummaryTable rows={review.daily_summaries} day />
        ) : (
          <SummaryTable rows={review.range_summaries} />
        )}
        {mode === "completed" && (
          <div class="button-row">
            <button disabled={!selected} onClick={loadSelected}>
              Load selected entry
            </button>
            <button onClick={startCreate}>Add missed entry</button>
            <button
              class="danger"
              disabled={!selected || mutationBusy}
              onClick={() => void deleteEntry()}
            >
              {deletePending ? "Confirm permanent deletion" : "Delete selected"}
            </button>
          </div>
        )}
      </section>

      {editor && (
        <section
          class="panel editor"
          role="dialog"
          aria-modal="false"
          aria-labelledby="editor-title"
        >
          <h2 id="editor-title">
            {editor.mode === "correct" ? "Correct entry" : "Add missed time"}
          </h2>
          <div class="entry-form-grid">
            <ProjectActivityFields
              idPrefix="review-entry"
              project={entry.project}
              activity={entry.activity}
              projects={entryProjects}
              activities={entryActivities}
              onProjectChange={(project) => setEntry({ ...entry, project })}
              onActivityChange={(activity) => setEntry({ ...entry, activity })}
            />
            <label>
              Started
              <input
                type="datetime-local"
                value={entry.started_at}
                onInput={(event) =>
                  setEntry({ ...entry, started_at: event.currentTarget.value })
                }
              />
            </label>
            <label>
              Stopped
              <input
                type="datetime-local"
                value={entry.stopped_at}
                onInput={(event) =>
                  setEntry({ ...entry, stopped_at: event.currentTarget.value })
                }
              />
            </label>
            <label class="wide-field">
              Note <span>optional</span>
              <input
                value={entry.note}
                onInput={(event) =>
                  setEntry({ ...entry, note: event.currentTarget.value })
                }
              />
            </label>
          </div>
          <div class="button-row">
            <button
              class="primary"
              disabled={!connected || mutationBusy}
              onClick={() => void saveEntry()}
            >
              Save
            </button>
            <button onClick={() => setEditor(null)}>Cancel</button>
          </div>
        </section>
      )}

      <section class="panel export-panel">
        <span class="eyebrow">CSV EXPORT</span>
        <h2>Export this view</h2>
        <label>
          Server-local destination path
          <input
            value={destination}
            onInput={(event) => {
              setDestination(event.currentTarget.value);
              setOverwritePending(false);
            }}
            placeholder="/path/to/time.csv"
          />
        </label>
        <button
          class={overwritePending ? "danger" : "primary"}
          disabled={!connected || mutationBusy || !destination}
          onClick={() => void exportReview()}
        >
          {overwritePending ? "Confirm replace existing file" : "Export CSV"}
        </button>
      </section>
    </div>
  );
}

function SummaryTable({
  rows,
  day = false,
}: {
  rows: Array<{
    day?: string;
    project: string;
    activity: string;
    duration_seconds: number;
  }>;
  day?: boolean;
}) {
  return (
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            {day && <th>Day</th>}
            <th>Project</th>
            <th>Activity</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={`${row.day ?? "range"}-${row.project}-${row.activity}-${index}`}
            >
              {day && <td>{row.day}</td>}
              <td>{row.project}</td>
              <td>{row.activity}</td>
              <td>{duration(row.duration_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
