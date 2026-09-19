import { expect, test } from "@playwright/test";

/**
 * Phase 12 smoke test - the inspection-first judge flow against the real
 * backend, real trained vision model and real image dataset.
 *
 * Uses the system-installed Microsoft Edge (no browser download required).
 */

const DATASET = "../train/train";
const DEFECT_IMAGE = `${DATASET}/scratch/scratch_00000.png`;
const NORMAL_IMAGE = `${DATASET}/normal/normal_00000.png`;

test("inspection-first flow: image -> decision -> console -> decision chain", async ({ page }) => {
  await page.goto("/");

  // 1-2) backend reachable, vision model ready
  await expect(page.getByText("ONLINE", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/READY.*classes/i).first()).toBeVisible({ timeout: 30_000 });

  // 3) four primary areas only
  for (const label of ["Inspect", "Console", "Decision", "Control Room"]) {
    await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
  }

  // 4) upload a real defect image
  const uploadInput = page.locator('input[type="file"]');
  await uploadInput.setInputFiles(DEFECT_IMAGE);

  // 4b) the live pipeline streams stages (LIVE chip / stage rail appear)
  await expect(page.getByText(/live pipeline/i)).toBeVisible({ timeout: 30_000 });

  // 5) real decision appears (PASS/DEFECT/REVIEW from the backend)
  await expect(page.getByText(/^(PASS|DEFECT|REVIEW)$/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/model-derived region/i).first()).toBeVisible();
  await expect(page.getByText(/PROCESS LINK NOT AVAILABLE/i).first()).toBeVisible();

  // 5b) recorded artifacts: original -> preprocessed -> anomaly map
  await expect(page.getByText(/recorded artifacts/i)).toBeVisible();
  await expect(page.getByText("ORIGINAL", { exact: true })).toBeVisible();
  await expect(page.getByText("PREPROCESSED", { exact: true })).toBeVisible();
  await expect(page.getByText("MODEL ANOMALY MAP", { exact: true })).toBeVisible();

  // 6) AI console shows the real trace with a visual pipeline
  await page.getByRole("button", { name: "Console", exact: true }).click();
  await expect(page.getByText("Processing pipeline")).toBeVisible();
  await expect(page.getByText(/AI inspection console/i).first()).toBeVisible();
  await expect(page.getByText(/feature extraction/i).first()).toBeVisible();
  await expect(page.getByText(/not private model chain-of-thought/i).first()).toBeVisible();

  // 7) decision chain
  await page.getByRole("button", { name: "Decision", exact: true }).click();
  await expect(page.getByText("WHAT", { exact: true })).toBeVisible();
  await expect(page.getByText("WHERE", { exact: true })).toBeVisible();
  await expect(page.getByText("HOW CERTAIN", { exact: true })).toBeVisible();
  await expect(page.getByText("WHY", { exact: true })).toBeVisible();
  await expect(page.getByText(/false accept rate/i)).toBeVisible();

  // 8) normal image -> PASS
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await uploadInput.setInputFiles(NORMAL_IMAGE);
  await expect(page.getByText(/^PASS$/).first()).toBeVisible({ timeout: 60_000 });
});

test("control room: real process dataset, flow and constraint", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Control Room", exact: true }).click();

  // select a previously processed real dataset
  const selector = page.getByRole("button", { name: /process dataset/i }).first();
  await selector.click();
  const datasetOption = page.locator('[role="option"]').first();
  if ((await datasetOption.count()) > 0) {
    await datasetOption.click();
    await expect(page.getByText(/current constraint/i)).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/process flow/i).first()).toBeVisible();
    await expect(page.getByText(/advisory action/i).first()).toBeVisible();
  } else {
    // honest empty state when no process dataset has ever been processed
    await expect(page.getByText(/no process dataset loaded/i)).toBeVisible();
  }
});

test("mobile viewport + reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Inspect", exact: true })).toBeVisible({ timeout: 30_000 });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(2);
});
