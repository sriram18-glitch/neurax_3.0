import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

/**
 * V2 smoke test against the REAL backend, trained vision model and image
 * dataset. Verifies the automation-first flow: stream → inspection → decision
 * → automatic investigation → replay → process intelligence → batch inspection.
 */

test("automation flow: stream → real inspection → auto investigation → replay", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");

  // 1) backend + model ready, four areas
  await expect(page.getByText("ONLINE", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/READY.*classes/i).first()).toBeVisible({ timeout: 30_000 });
  for (const label of ["Command Center", "Inspection", "Process Intelligence", "Investigation History"]) {
    await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
  }

  // 2) honest data coverage is visible
  await expect(page.getByText(/image → process join/i)).toBeVisible();
  await expect(page.getByText(/no per-image batch\/station\/unit\/timestamp metadata/i)).toBeVisible();

  // 3) start the automated inspection stream
  await page.getByRole("button", { name: /start automated inspection/i }).click();
  await expect(page.getByText(/automation running/i)).toBeVisible({ timeout: 30_000 });

  // 4) a real decision arrives from the stream (PASS/DEFECT/REVIEW)
  await expect(page.getByText(/^(PASS|DEFECT|REVIEW)$/).first()).toBeVisible({ timeout: 90_000 });

  // 5) automatic investigation runs on actionable decisions
  await expect(page.getByText(/automatic investigation triggered/i).first()).toBeVisible({ timeout: 90_000 });

  // stop the stream so the rest of the flow is stable
  await page.getByRole("button", { name: /^pause$/i }).click();

  // 6) inspection: real localization/robustness/quality evidence
  await page.getByRole("button", { name: "Inspection", exact: true }).click();
  await expect(page.getByText(/ai inference pipeline/i)).toBeVisible();
  await expect(page.getByText(/embedding projection/i)).toBeVisible();
  await expect(page.getByText(/ground truth: not available/i).first()).toBeVisible();
  await expect(page.getByText(/known distribution/i).first()).toBeVisible();
  await expect(page.getByText(/pass ≥ 0\.80/).first()).toBeVisible();
  await expect(page.getByText(/evidence graph/i)).toBeVisible();

  // 7) pipeline: plain language + technical evidence drawer
  await page.getByRole("button", { name: /^Classify/i }).first().click();
  await expect(page.getByText(/calibrated probability/i).first()).toBeVisible();
  await page.getByRole("button", { name: /view technical evidence/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");

  // 8) investigation history: stored record + replay
  await page.getByRole("button", { name: "Investigation History", exact: true }).click();
  await expect(page.getByText(/investigation replay/i)).toBeVisible();
  await page.getByRole("button", { name: /play investigation/i }).click();
  await expect(page.getByText(/inspection received/i).first()).toBeVisible();
  await page.getByRole("button", { name: /next stage/i }).click();
  await expect(page.getByText(/classification/i).first()).toBeVisible();
});

test("process intelligence: real dataset, timeline and bottleneck evidence", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");
  await page.getByRole("button", { name: "Process Intelligence", exact: true }).click();

  const selector = page.getByRole("button", { name: /process dataset/i }).first();
  await selector.click();
  const option = page.locator('[role="option"]').first();
  if ((await option.count()) > 0) {
    await option.click();
    await expect(page.getByText(/current constraint/i)).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText(/observed output rate/i)).toBeVisible();
    await page.getByRole("button", { name: /^01 process/i }).click();
    await expect(page.getByText(/process timeline/i)).toBeVisible();
    await expect(page.getByText(/station series/i).first()).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: /^03 flow/i }).click();
    await expect(page.getByText(/bottleneck evidence/i)).toBeVisible();
    await page.getByRole("button", { name: /^04 impact/i }).click();
    await expect(page.getByText(/impact flow/i)).toBeVisible();
    await expect(page.getByText(/user assumptions/i).first()).toBeVisible();
  } else {
    await expect(page.getByText(/process data not loaded/i)).toBeVisible();
  }
});

test("batch inspection: add data → validate → auto check → per-image results", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/");

  // add a batch with class-folder names so ground truth is available
  await page.getByRole("button", { name: /add inspection data/i }).click();
  await page.getByRole("button", { name: /add batch \/ dataset/i }).click();
  const batchInput = page.getByLabel("Add inspection images");
  await batchInput.setInputFiles([
    { name: "normal/normal_00000.png", mimeType: "image/png", buffer: readFileSync("../train/train/normal/normal_00000.png") },
    { name: "normal/normal_00003.png", mimeType: "image/png", buffer: readFileSync("../train/train/normal/normal_00003.png") },
    { name: "scratch/scratch_00000.png", mimeType: "image/png", buffer: readFileSync("../train/train/scratch/scratch_00000.png") },
    { name: "scratch/scratch_00001.png", mimeType: "image/png", buffer: readFileSync("../train/train/scratch/scratch_00001.png") },
  ]);

  // data health report with real validation numbers
  await expect(page.getByText(/data health/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/labels/i).first()).toBeVisible();
  await expect(page.getByText(/localization annotations/i)).toBeVisible();

  // automatic batch inspection with real progress
  await page.getByRole("button", { name: /start auto check/i }).click();
  await expect(page.getByText(/dataset inspection complete/i)).toBeVisible({ timeout: 120_000 });

  // measured decision quality vs class-folder ground truth
  await expect(page.getByText(/measured against class-folder ground truth/i)).toBeVisible();
  await expect(page.getByText(/TP 2 · TN 2 · FP 0 · FN 0/)).toBeVisible({ timeout: 10_000 });

  // per-image gallery with confidence bars
  await expect(page.getByText(/inspection gallery/i)).toBeVisible();
  await expect(page.getByText(/scratch_00000\.png/i).first()).toBeVisible();
  await expect(page.getByText("100.0%").first()).toBeVisible();
});

test("human review: banner → queue with actual images → resolve → counter updates", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/");

  // the review banner appears when REVIEW items are pending (real backend state)
  const banner = page.getByText(/inspection\(s\) require human review/i).first();
  const hasBanner = await banner
    .waitFor({ state: "visible", timeout: 20_000 })
    .then(() => true)
    .catch(() => false);

  if (!hasBanner) {
    // nothing pending: verify the honest empty state of the review workspace
    await page.getByRole("button", { name: "Investigation History", exact: true }).click();
    await page.getByRole("button", { name: /human review/i }).click();
    await expect(page.getByRole("heading", { name: /human review queue/i })).toBeVisible();
    await expect(page.getByText(/review queue empty/i)).toBeVisible();
    await expect(page.getByText(/automatic decision is blocked/i)).toBeVisible();
    return;
  }

  // open the actual review queue
  await page.getByRole("button", { name: /review queue/i }).click();
  await expect(page.getByRole("heading", { name: /human review queue/i })).toBeVisible();
  await expect(page.getByText(/why human review\?/i).first()).toBeVisible();
  await expect(page.getByText(/^AI decision$/i).first()).toBeVisible();

  // a real image is shown for the selected item
  const reviewImage = page.locator('img[alt="Inspection under review"]');
  await expect(reviewImage).toBeVisible();

  // resolve one item: MARK PASS resolves it and the counter updates
  const before = await page.getByText(/inspection\(s\) require human review/i).first().textContent().catch(() => null);
  const match = before?.match(/(\d+) inspection/);
  const count = match ? Number(match[1]) : 0;
  if (count > 0) {
    await page.getByRole("button", { name: /^mark pass$/i }).click();
    if (count === 1) {
      // queue emptied: the header disappears entirely (no stale banner at zero)
      await expect(page.getByText(/review queue empty/i)).toBeVisible({ timeout: 15_000 });
    } else {
      await expect(page.getByText(`${count - 1} inspection(s) require human review`).first()).toBeVisible({ timeout: 15_000 });
    }
  }
});

test("mobile viewport + reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Inspection", exact: true })).toBeVisible({ timeout: 30_000 });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(2);
});
