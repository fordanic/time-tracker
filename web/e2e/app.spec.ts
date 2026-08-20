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
  await expect(page.getByRole("combobox", { name: "Project" })).toHaveValue(
    "Launch work",
  );
  await expect(page.getByRole("combobox", { name: "Activity" })).toHaveValue(
    "Documentation",
  );
  const switchPreviews = page.getByText("Will switch from the current timer.");
  await expect(switchPreviews).toHaveCount(2);
  await expect(switchPreviews.first()).toBeVisible();
  await recent.focus();
  await page.keyboard.press("Tab");
  const quickNote = page.getByRole("textbox", {
    name: "Quick-switch note optional",
  });
  await expect(quickNote).toBeFocused();
  await quickNote.fill("Browser E2E");
  const quickPreview = page.locator(".deck-panel .action-preview");
  const quickApply = page.locator(".deck-panel > button.full");
  const [quickNoteBox, quickPreviewBox, quickApplyBox] = await Promise.all([
    quickNote.boundingBox(),
    quickPreview.boundingBox(),
    quickApply.boundingBox(),
  ]);
  expect(quickNoteBox).not.toBeNull();
  expect(quickPreviewBox).not.toBeNull();
  expect(quickApplyBox).not.toBeNull();
  expect(
    quickPreviewBox!.y - (quickNoteBox!.y + quickNoteBox!.height),
  ).toBeGreaterThanOrEqual(8);
  expect(
    quickApplyBox!.y - (quickPreviewBox!.y + quickPreviewBox!.height),
  ).toBeGreaterThanOrEqual(8);
  await quickNote.press("Escape");
  await page.keyboard.press("g");
  await expect(
    page.getByRole("heading", { name: "Launch work / Documentation" }),
  ).toBeVisible();
  await expect(page.getByText("Switch saved.")).toBeVisible();

  const project = page.getByRole("combobox", { name: "Project" });
  await project.focus();
  await project.press("Escape");
  await expect(page.getByText(/Shortcut ready/)).toBeVisible();
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
  await page
    .getByRole("button")
    .filter({ hasText: "Responsive shell" })
    .click();
  await page.getByRole("button", { name: "Load selected entry" }).click();
  const correctionEditor = page.getByRole("dialog", { name: "Correct entry" });
  await correctionEditor
    .getByRole("textbox", { name: /Note/ })
    .fill("Corrected in browser");
  await correctionEditor.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Entry correction saved.")).toBeVisible();

  await page.getByRole("button", { name: "Add missed entry" }).click();
  const creationEditor = page.getByRole("dialog", { name: "Add missed time" });
  await creationEditor
    .getByRole("combobox", { name: "Project" })
    .fill("Browser missed time");
  await creationEditor
    .getByRole("combobox", { name: "Activity" })
    .fill("Review");
  const [missedStart, missedStop] = await page.evaluate(() => {
    const localInput = (value: Date) => {
      const offset = value.getTimezoneOffset() * 60_000;
      return new Date(value.getTime() - offset).toISOString().slice(0, 16);
    };
    return [
      localInput(new Date(Date.now() - 5 * 60 * 60 * 1000)),
      localInput(new Date(Date.now() - 4 * 60 * 60 * 1000)),
    ];
  });
  await creationEditor.getByLabel("Started").fill(missedStart);
  await creationEditor.getByLabel("Stopped").fill(missedStop);
  await creationEditor.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Missed time added.")).toBeVisible();

  await page.getByRole("button", { name: "Range totals" }).click();
  await expect(page.getByRole("cell", { name: "Web GUI" })).toBeVisible();

  await page.getByRole("button", { name: "Manage" }).click();
  await expect(
    page.getByRole("heading", { name: "Projects and activities" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "New project" })
    .fill("Browser project");
  const newProject = page.getByRole("textbox", { name: "New project" });
  const newActivity = page.getByRole("textbox", { name: "New activity" });
  const createProject = page.getByRole("button", { name: "Create project" });
  const createActivity = page.getByRole("button", { name: "Create activity" });
  const [newProjectBox, createProjectBox, newActivityBox, createActivityBox] =
    await Promise.all([
      newProject.boundingBox(),
      createProject.boundingBox(),
      newActivity.boundingBox(),
      createActivity.boundingBox(),
    ]);
  expect(
    createProjectBox!.y - (newProjectBox!.y + newProjectBox!.height),
  ).toBeGreaterThanOrEqual(8);
  expect(
    createActivityBox!.y - (newActivityBox!.y + newActivityBox!.height),
  ).toBeGreaterThanOrEqual(8);
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
  await note.press("Escape");
  await page.keyboard.press("u");
  await expect(
    page.getByText("Active details updated without restarting time."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop" })).toBeEnabled();
  await note.focus();
  await note.press("Escape");
  await page.keyboard.press("x");
  await expect(
    page.getByRole("heading", { name: "No active timer" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "No active timer" }),
  ).toBeVisible();
});
