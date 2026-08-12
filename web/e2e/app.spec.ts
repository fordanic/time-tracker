import { expect, test } from "@playwright/test";

test("responsive browser workflow stays durable across all four views", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Launch work / Web GUI" }),
  ).toBeVisible();

  for (const width of [320, 720, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const sizes = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(sizes.scroll).toBe(sizes.client);
  }

  const recent = page.getByRole("radio", { name: /Documentation/ });
  await recent.click();
  await expect(
    page.getByText("Will switch from the current timer."),
  ).toBeVisible();
  await recent.focus();
  await page.keyboard.press("Tab");
  const quickNote = page.getByRole("textbox", {
    name: "Quick-switch note optional",
  });
  await expect(quickNote).toBeFocused();
  await quickNote.fill("Browser E2E");
  await quickNote.press("Control+Enter");
  await expect(
    page.getByRole("heading", { name: "Launch work / Documentation" }),
  ).toBeVisible();
  await expect(page.getByText("Switch saved.")).toBeVisible();

  const project = page.getByRole("combobox", { name: "Project" });
  await project.focus();
  await project.press("Escape");
  await expect(page.getByText(/View shortcut ready/)).toBeVisible();
  await page.keyboard.press("r");
  await expect(
    page.getByRole("heading", { name: "Completed time" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply filters" })).toHaveCount(
    0,
  );
  await page
    .getByRole("combobox", { name: "Date range" })
    .selectOption("today");
  await expect(page.getByText("Responsive shell")).toBeVisible();
  await page.getByRole("button", { name: "Range totals" }).click();
  await expect(page.getByRole("cell", { name: "Web GUI" })).toBeVisible();

  await page.getByRole("button", { name: "Manage" }).click();
  await expect(
    page.getByRole("heading", { name: "Projects and activities" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "New project" })
    .fill("Browser project");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(
    page.getByText("Created project Browser project."),
  ).toBeVisible();

  await page.getByRole("button", { name: "Settings" }).click();
  await expect(
    page.getByRole("heading", { name: "Browser theme" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dark" }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-appearance", "dark");

  await page.getByRole("button", { name: "Track" }).click();
  const note = page.getByRole("textbox", { name: /^Note optional$/ });
  await note.focus();
  await note.press("Control+Shift+Enter");
  await expect(
    page.getByText("Active details updated without restarting time."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).toBeEnabled();
  await note.focus();
  await note.press("Control+Alt+Enter");
  await expect(
    page.getByRole("heading", { name: "No active timer" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "No active timer" }),
  ).toBeVisible();
});
