import { useEffect, useState } from "preact/hooks";
import { post } from "./api.ts";
import type { Bootstrap, ReminderSettings } from "./types.ts";

interface Props {
  data: Bootstrap;
  connected: boolean;
  announce: (message: string) => void;
  refresh: (message?: string) => Promise<void>;
}

type Appearance = "system" | "light" | "dark";
const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function initialAppearance(): Appearance {
  const stored = localStorage.getItem("time-tracker-appearance");
  return stored === "light" || stored === "dark" ? stored : "system";
}

export function SettingsView({ data, connected, announce, refresh }: Props) {
  const [settings, setSettings] = useState<ReminderSettings>(data.settings);
  const [delimiter, setDelimiter] = useState<"," | "|">(data.export_delimiter);
  const [appearance, setAppearance] = useState<Appearance>(initialAppearance);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.appearance = appearance;
    localStorage.setItem("time-tracker-appearance", appearance);
  }, [appearance]);

  const applyAppearance = (value: Appearance) => {
    document.documentElement.dataset.appearance = value;
    localStorage.setItem("time-tracker-appearance", value);
    setAppearance(value);
  };

  const setNumber = (field: keyof ReminderSettings, value: string) => {
    setSettings({ ...settings, [field]: Number(value) });
  };

  const save = async () => {
    setBusy(true);
    try {
      await post("/api/settings", { ...settings, export_delimiter: delimiter });
      await refresh("Settings saved and reminder schedule reloaded.");
    } catch (error) {
      announce(error instanceof Error ? error.message : "Settings save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="settings-grid">
      <section class="panel settings-main">
        <span class="eyebrow">REMINDERS</span>
        <h2>Schedule and intervals</h2>
        <div class="setting-row">
          <label class="check">
            <input
              type="checkbox"
              checked={settings.inactive_enabled}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  inactive_enabled: event.currentTarget.checked,
                })
              }
            />
            Inactive reminder
          </label>
          <label>
            After (minutes)
            <input
              type="number"
              min="0.01"
              step="any"
              value={settings.inactive_interval_minutes}
              onInput={(event) =>
                setNumber(
                  "inactive_interval_minutes",
                  event.currentTarget.value,
                )
              }
            />
          </label>
        </div>
        <div class="setting-row">
          <label class="check">
            <input
              type="checkbox"
              checked={settings.active_enabled}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  active_enabled: event.currentTarget.checked,
                })
              }
            />
            Active reminder
          </label>
          <label>
            Every (minutes)
            <input
              type="number"
              min="0.01"
              step="any"
              value={settings.active_interval_minutes}
              onInput={(event) =>
                setNumber("active_interval_minutes", event.currentTarget.value)
              }
            />
          </label>
        </div>
        <div class="setting-row">
          <label class="check">
            <input
              type="checkbox"
              checked={settings.idle_enabled}
              disabled={!data.idle_detection.available}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  idle_enabled: event.currentTarget.checked,
                })
              }
            />
            Idle-triggered active reminder
          </label>
          <label>
            Idle threshold (minutes)
            <input
              type="number"
              min="0.01"
              step="any"
              value={settings.idle_threshold_minutes}
              disabled={!data.idle_detection.available}
              onInput={(event) =>
                setNumber("idle_threshold_minutes", event.currentTarget.value)
              }
            />
          </label>
        </div>
        <p class="hint">
          Idle detection:{" "}
          {data.idle_detection.available
            ? "available this session"
            : "unavailable on this host"}
        </p>
        <label>
          Snooze duration (minutes)
          <input
            type="number"
            min="0.01"
            step="any"
            value={settings.snooze_minutes}
            onInput={(event) =>
              setNumber("snooze_minutes", event.currentTarget.value)
            }
          />
        </label>
        <hr />
        <label class="check">
          <input
            type="checkbox"
            checked={settings.window_enabled}
            onChange={(event) =>
              setSettings({
                ...settings,
                window_enabled: event.currentTarget.checked,
              })
            }
          />
          Limit reminders to a weekly window
        </label>
        <fieldset disabled={!settings.window_enabled}>
          <legend>Reminder weekdays</legend>
          <div class="weekday-row">
            {weekdays.map((day, index) => (
              <label key={day} class="weekday">
                <input
                  type="checkbox"
                  checked={settings.window_weekdays.includes(index)}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      window_weekdays: event.currentTarget.checked
                        ? [...settings.window_weekdays, index].sort()
                        : settings.window_weekdays.filter(
                            (item) => item !== index,
                          ),
                    })
                  }
                />
                {day}
              </label>
            ))}
          </div>
          <div class="field-row">
            <label>
              Window starts
              <input
                type="time"
                value={settings.window_start}
                onInput={(event) =>
                  setSettings({
                    ...settings,
                    window_start: event.currentTarget.value,
                  })
                }
              />
            </label>
            <label>
              Window ends
              <input
                type="time"
                value={settings.window_end}
                onInput={(event) =>
                  setSettings({
                    ...settings,
                    window_end: event.currentTarget.value,
                  })
                }
              />
            </label>
          </div>
        </fieldset>
      </section>

      <aside class="settings-side">
        <section class="panel">
          <span class="eyebrow">APPEARANCE</span>
          <h2>Browser theme</h2>
          <div class="segmented vertical" aria-label="Appearance">
            {(["system", "light", "dark"] as const).map((item) => (
              <button
                key={item}
                class={appearance === item ? "selected" : ""}
                onClick={() => applyAppearance(item)}
              >
                {item[0]?.toUpperCase()}
                {item.slice(1)}
              </button>
            ))}
          </div>
          <p class="hint">
            Stored in this browser only. The TUI palette is unchanged.
          </p>
        </section>
        <section class="panel">
          <span class="eyebrow">EXPORT</span>
          <h2>CSV delimiter</h2>
          <label>
            Delimiter
            <select
              value={delimiter}
              onChange={(event) =>
                setDelimiter(event.currentTarget.value as "," | "|")
              }
            >
              <option value=",">Comma (,)</option>
              <option value="|">Pipe (|)</option>
            </select>
          </label>
        </section>
        <section class="panel">
          <span class="eyebrow">CONFIGURATION</span>
          <h2>Local file</h2>
          <code class="path">{data.configuration_path}</code>
        </section>
      </aside>

      <div class="save-bar">
        <button
          class="primary"
          disabled={!connected || busy}
          onClick={() => void save()}
        >
          Save settings
        </button>
      </div>
    </div>
  );
}
