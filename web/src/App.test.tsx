import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
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

  it("requires selection before applying recent work and uses shared classification", async () => {
    render(<App />);
    await screen.findByText("Recent work");
    const apply = screen.getByRole("button", { name: "Apply selected work" });
    expect((apply as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /ClientBuild/ }));
    await waitFor(() =>
      expect((apply as HTMLButtonElement).disabled).toBe(false),
    );
    fireEvent.click(apply);

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
});
