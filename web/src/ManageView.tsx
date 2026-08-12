import { useState } from "preact/hooks";
import { post } from "./api.ts";
import type { Bootstrap } from "./types.ts";

interface Props {
  data: Bootstrap;
  connected: boolean;
  announce: (message: string) => void;
  refresh: (message?: string) => Promise<void>;
}

type Confirmation =
  | { kind: "project"; project: string }
  | { kind: "activity"; project: string; activity: string };

export function ManageView({ data, connected, announce, refresh }: Props) {
  const [project, setProject] = useState("");
  const [activity, setActivity] = useState("");
  const [newProject, setNewProject] = useState("");
  const [newActivity, setNewActivity] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [busy, setBusy] = useState(false);

  const mutate = async (path: string, body: object, success: string) => {
    setBusy(true);
    try {
      await post(path, body);
      setConfirmation(null);
      await refresh(success);
    } catch (error) {
      announce(
        error instanceof Error ? error.message : "Management action failed",
      );
    } finally {
      setBusy(false);
    }
  };

  const archiveProject = async () => {
    if (confirmation?.kind === "project" && confirmation.project === project) {
      await mutate(
        "/api/manage/archive-project",
        { project },
        `Archived ${project}.`,
      );
      setProject("");
      setActivity("");
      return;
    }
    setBusy(true);
    try {
      const target = await post<{ project: string }>(
        "/api/manage/archive-project-target",
        { project },
      );
      setConfirmation({ kind: "project", project: target.project });
      announce(`Confirm archive of project ${target.project}.`);
    } catch (error) {
      announce(
        error instanceof Error ? error.message : "Archive target invalid",
      );
    } finally {
      setBusy(false);
    }
  };

  const archiveActivity = async () => {
    if (
      confirmation?.kind === "activity" &&
      confirmation.project === project &&
      confirmation.activity === activity
    ) {
      await mutate(
        "/api/manage/archive-activity",
        { project, activity },
        `Archived ${project} / ${activity}.`,
      );
      setActivity("");
      return;
    }
    setBusy(true);
    try {
      const target = await post<{ project: string; activity: string }>(
        "/api/manage/archive-activity-target",
        { project, activity },
      );
      setConfirmation({ kind: "activity", ...target });
      announce(`Confirm archive of ${target.project} / ${target.activity}.`);
    } catch (error) {
      announce(
        error instanceof Error ? error.message : "Archive target invalid",
      );
    } finally {
      setBusy(false);
    }
  };

  const availableActivities = data.activities[project] ?? [];

  return (
    <div class="manage-grid">
      <section class="panel">
        <span class="eyebrow">SELECTABLE WORK</span>
        <h2>Projects and activities</h2>
        <div class="hierarchy">
          {data.projects.length ? (
            data.projects.map((item) => (
              <div key={item} class="project-block">
                <strong>{item}</strong>
                <ul>
                  {(data.activities[item] ?? []).map((child) => (
                    <li key={child}>{child}</li>
                  ))}
                </ul>
              </div>
            ))
          ) : (
            <p class="muted">No selectable projects yet.</p>
          )}
        </div>
      </section>

      <section class="panel">
        <span class="eyebrow">PREPARE WORK</span>
        <h2>Create without tracking</h2>
        <label>
          New project
          <input
            value={newProject}
            onInput={(event) => setNewProject(event.currentTarget.value)}
          />
        </label>
        <button
          class="primary"
          disabled={!connected || busy || !newProject}
          onClick={() =>
            void mutate(
              "/api/manage/create-project",
              { project: newProject },
              `Created project ${newProject}.`,
            ).then(() => setNewProject(""))
          }
        >
          Create project
        </button>
        <hr />
        <label>
          Parent project
          <select
            value={project}
            onChange={(event) => {
              setProject(event.currentTarget.value);
              setActivity("");
              setConfirmation(null);
            }}
          >
            <option value="">Select project</option>
            {data.projects.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          New activity
          <input
            value={newActivity}
            onInput={(event) => setNewActivity(event.currentTarget.value)}
          />
        </label>
        <button
          class="primary"
          disabled={!connected || busy || !project || !newActivity}
          onClick={() =>
            void mutate(
              "/api/manage/create-activity",
              { project, activity: newActivity },
              `Created ${project} / ${newActivity}.`,
            ).then(() => setNewActivity(""))
          }
        >
          Create activity
        </button>
      </section>

      <section class="panel">
        <span class="eyebrow">ARCHIVE</span>
        <h2>Hide selectable work</h2>
        <label>
          Project
          <select
            value={project}
            onChange={(event) => {
              setProject(event.currentTarget.value);
              setActivity("");
              setConfirmation(null);
            }}
          >
            <option value="">Select project</option>
            {data.projects.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          Activity
          <select
            value={activity}
            onChange={(event) => {
              setActivity(event.currentTarget.value);
              setConfirmation(null);
            }}
          >
            <option value="">Select activity</option>
            {availableActivities.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <div class="button-row">
          <button
            class={confirmation?.kind === "project" ? "danger" : ""}
            disabled={!connected || busy || !project}
            onClick={() => void archiveProject()}
          >
            {confirmation?.kind === "project"
              ? `Confirm archive ${confirmation.project}`
              : "Archive project"}
          </button>
          <button
            class={confirmation?.kind === "activity" ? "danger" : ""}
            disabled={!connected || busy || !project || !activity}
            onClick={() => void archiveActivity()}
          >
            {confirmation?.kind === "activity"
              ? `Confirm archive ${confirmation.activity}`
              : "Archive activity"}
          </button>
        </div>
      </section>

      <section class="panel archived">
        <span class="eyebrow">ARCHIVED</span>
        <h2>Restore work</h2>
        <h3>Projects</h3>
        {data.archived_projects.length ? (
          <ul class="restore-list">
            {data.archived_projects.map((item) => (
              <li key={item}>
                <span>{item}</span>
                <button
                  disabled={!connected || busy}
                  onClick={() =>
                    void mutate(
                      "/api/manage/unarchive-project",
                      { project: item },
                      `Restored project ${item}.`,
                    )
                  }
                >
                  Restore
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p class="muted">No archived projects.</p>
        )}
        <h3>Activities</h3>
        {data.archived_activities.length ? (
          <ul class="restore-list">
            {data.archived_activities.map((item) => (
              <li key={`${item.project}/${item.activity}`}>
                <span>
                  {item.project} / {item.activity}
                  {item.project_archived && (
                    <small>Parent project is archived</small>
                  )}
                </span>
                <button
                  disabled={!connected || busy || item.project_archived}
                  onClick={() =>
                    void mutate(
                      "/api/manage/unarchive-activity",
                      { project: item.project, activity: item.activity },
                      `Restored ${item.project} / ${item.activity}.`,
                    )
                  }
                >
                  Restore
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p class="muted">No archived activities.</p>
        )}
      </section>
    </div>
  );
}
