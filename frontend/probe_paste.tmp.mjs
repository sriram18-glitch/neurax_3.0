import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";

const browser = await chromium.launch({ channel: "msedge" });
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
const errors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(msg.text().slice(0, 140));
});
await page.goto("http://localhost:4173/");
await page.getByText("ONLINE", { exact: true }).waitFor({ timeout: 30000 });
await page.getByText(/READY.*classes/i).first().waitFor({ timeout: 30000 });

// IMAGE SET mode, then simulate Ctrl+V with two real images
await page.getByRole("button", { name: /add inspection data/i }).first().click();
await page.waitForTimeout(400);
await page.evaluate(() => {
  const buttons = Array.from(document.querySelectorAll("button"));
  const target = buttons.find((b) => b.textContent && b.textContent.includes("IMAGE SET"));
  if (target) target.click();
});
await page.waitForTimeout(800);

const pasted = await page.evaluate(async () => {
  const readAsFile = async (dataUrl, name) => {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    return new File([blob], name, { type: blob.type });
  };
  const n1 = await (await fetch("/demo_files/normal_000.png")).blob();
  const s1 = await (await fetch("/demo_files/scratch_000.png")).blob();
  const dt = new DataTransfer();
  dt.items.add(new File([n1], "pasted_normal.png", { type: "image/png" }));
  dt.items.add(new File([s1], "pasted_scratch.png", { type: "image/png" }));
  const event = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true });
  window.dispatchEvent(event);
  return "dispatched";
});
console.log("paste dispatched:", pasted);
await page.getByText(/data health/i).waitFor({ timeout: 30000 });
console.log("1) paste -> data health report:", true);
const healthText = await page.locator("main").textContent();
console.log("2) shows pasted names:", healthText.includes("pasted_normal") || healthText.includes("pasted_scratch") || healthText.includes("2 files"));
console.log("3) valid count 2:", healthText.includes("valid2") || healthText.includes("2valid"));
console.log("ERRORS:", JSON.stringify(errors));
await browser.close();