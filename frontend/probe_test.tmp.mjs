import { chromium } from "@playwright/test";

const browser = await chromium.launch({ channel: "msedge" });
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(msg.text().slice(0, 160));
});

await page.goto("http://localhost:4173/");
await page.getByText("ONLINE", { exact: true }).waitFor({ timeout: 30000 });

// ---- TEST 1: IMAGE SET browse button opens the file picker ----
await page.getByRole("button", { name: /add inspection data/i }).first().click();
await page.waitForTimeout(400);
await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll("button"));
  const target = buttons.find((b) => b.textContent && b.textContent.includes("IMAGE SET"));
  if (target) target.click();
});
await page.waitForTimeout(800);

let chooserFired = false;
page.once("filechooser", () => {
  chooserFired = true;
});
const browseBtn = page.getByRole("button", { name: /browse files/i });
console.log("1) IMAGE SET browse button visible:", await browseBtn.isVisible().catch(() => false));
if (await browseBtn.isVisible().catch(() => false)) {
  await browseBtn.click({ timeout: 5000 }).catch(() => console.log("   click failed"));
  await page.waitForTimeout(1000);
  console.log("2) file picker fired (filechooser event):", chooserFired);
}

// ---- TEST 2: FOLDER DATASET browse button ----
await page.getByRole("button", { name: /folder dataset/i }).click();
await page.waitForTimeout(800);
chooserFired = false;
page.once("filechooser", () => {
  chooserFired = true;
});
const folderBrowse = page.getByRole("button", { name: /browse folder/i });
console.log("3) FOLDER browse button visible:", await folderBrowse.isVisible().catch(() => false));
if (await folderBrowse.isVisible().catch(() => false)) {
  await folderBrowse.click({ timeout: 5000 }).catch(() => console.log("   click failed"));
  await page.waitForTimeout(1000);
  console.log("4) folder picker fired:", chooserFired);
}

// ---- TEST 3: process dataset selection -> where does analysis show? ----
await page.getByRole("button", { name: /no process dataset/i }).click();
await page.waitForTimeout(500);
const option = page.locator('[role="option"]').first();
console.log("5) dataset dropdown options:", await option.count());
if (await option.count()) {
  console.log("   first option label:", (await option.textContent()).trim().slice(0, 60));
  await option.click();
  await page.waitForTimeout(4000);
  // after selecting, what view are we on and does the analysis load?
  const currentView = await page.locator("main").textContent().catch(() => "");
  console.log("6) after dataset selection, page shows:", currentView.slice(0, 120).replace(/\s+/g, " "));
  await page.getByRole("button", { name: "Process Intelligence", exact: true }).click();
  await page.waitForTimeout(3000);
  const piText = await page.locator("main").textContent().catch(() => "");
  console.log("7) Process Intelligence shows dataset name:", piText.includes("product-quality-control") || piText.includes("quality-control"));
  console.log("   shows Current constraint:", /current constraint/i.test(piText));
  console.log("   shows Observed output rate:", /observed output rate/i.test(piText));
}

console.log("CONSOLE ERRORS:", JSON.stringify(errors));
await browser.close();