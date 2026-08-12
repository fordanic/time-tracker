import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App.tsx";
import type { Bootstrap } from "./types.ts";

const bootstrap: Bootstrap = {
  active: null,
  reminder: null,
  projects: ["Client"],
  activities: { Client: ["Build"] },
  recent: [{ project: "Client", activity: "Build" }],
  completed: [],
  today_completed_seconds: 0,
  archived_projects: [],
  archived_activities: [],
  settings: {
    inactive_enabled: true,
    inactive_interval_minutes: 5,
    active_enabled: true,
    active_interval_minutes: 30,
    window_enabled: false,
    window_weekdays: [0, 1, 2, 3, 4],
    window_start: "09:00",
    window_end: "17:00",
    snooze_minutes: 10,
    idle_enabled: false,
    idle_threshold_minutes: 15,
  },
  export_delimiter: ",",
  idle_detection: { available: true },
  configuration_path: "/tmp/config.toml",
};

function json(data: object): Response {
  return new Response(JSON.stringify({ data }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (input) => {
      const path = String(input);
      if (path === "/api/bootstrap") return json(bootstrap);
      if (path === "/api/state") return json({ active: null, reminder: null });
      if (path === "/api/track/classify") return json({ action: "start" });
      if (path === "/api/timer/start")
        return json({ active: { ...bootstrap.recent[0] } });
      if (path === "/api/review/query")
        return json({
          groups: [],
          daily_summaries: [],
          range_summaries: [],
          projects: [],
          activities: [],
        });
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("navigates all persistent views without a server round trip", async () => {
    render(<App />);
    expect(await screen.findByText("Recent work")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByRole("heading", { name: "Browser theme" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement.dataset.appearance).toBe("dark");
    expect(localStorage.getItem("time-tracker-appearance")).toBe("dark");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("previews selected work, tabs to its note, and confirms with Enter", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Recent work");
    const apply = screen.getByRole("button", { name: "Apply selected work" });
    expect((apply as HTMLButtonElement).disabled).toBe(true);

    const recent = screen.getByRole("radio", { name: /1ClientBuild/ });
    await user.click(recent);
    await screen.findByText("Will start a new timer.");
    expect((apply as HTMLButtonElement).disabled).toBe(false);

    recent.focus();
    await user.tab();
    const quickNote = screen.getByRole("textbox", {
      name: "Quick-switch note optional",
    });
    expect(document.activeElement).toBe(quickNote);
    await user.type(quickNote, "Focused work{Enter}");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/track/classify",
        expect.objectContaining({ method: "POST" }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/timer/start",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("uses browser-safe view shortcuts outside editable fields", async () => {
    render(<App />);
    await screen.findByText("Recent work");

    fireEvent.keyDown(window, { key: "r" });
    expect(
      screen.getByRole("heading", { name: "Completed time" }),
    ).toBeTruthy();
    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByText("select recent work")).toBeTruthy();

    const destination = screen.getByRole("textbox", {
      name: "Server-local destination path",
    });
    destination.focus();
    fireEvent.keyDown(destination, { key: "t" });
    expect(
      screen.getByRole("heading", { name: "Completed time" }),
    ).toBeTruthy();
  });

  it("confirms an already-selected deck item with Enter", async () => {
    render(<App />);
    await screen.findByText("Recent work");
    const recent = screen.getByRole("radio", { name: /1ClientBuild/ });
    fireEvent.click(recent);
    await screen.findByText("Will start a new timer.");
    fireEvent.keyDown(recent, { key: "Enter" });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/timer/start",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("previews manual capture and submits its note with Enter", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Recent work");
    await user.type(
      screen.getByRole("combobox", { name: "Project" }),
      "Client",
    );
    await user.type(
      screen.getByRole("combobox", { name: "Activity" }),
      "Build",
    );
    await screen.findByText("Will start a new timer.");
    await user.type(
      screen.getByRole("textbox", { name: "Note optional" }),
      "Manual note{Enter}",
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/timer/start",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("applies review filters automatically without an apply button", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Recent work");
    await user.click(screen.getByRole("button", { name: "Review" }));

    expect(screen.queryByRole("button", { name: "Apply filters" })).toBeNull();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/review/query",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const before = fetchMock.mock.calls.length;
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Date range" }),
      "today",
    );
    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBeGreaterThan(before),
    );
    const request = fetchMock.mock.calls.at(-1)?.[1];
    expect(JSON.parse(String(request?.body))).toMatchObject({
      preset: "today",
    });

    await user.click(screen.getByRole("button", { name: "Add missed entry" }));
    const editor = screen.getByRole("dialog", { name: "Add missed time" });
    expect(
      within(editor)
        .getByRole("combobox", { name: "Project" })
        .getAttribute("list"),
    ).toBe("review-entry-project-options");
    expect(
      within(editor)
        .getByRole("combobox", { name: "Activity" })
        .getAttribute("list"),
    ).toBe("review-entry-activity-options");
  });
});
