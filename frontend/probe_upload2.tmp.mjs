import { chromium } from "@playwright/test";

const browser = await chromium.launch({ channel: "msedge" });
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
const errors = [];
page.on("pageerror", (error) => errors.push(String(error).slice(0, 300)));
await page.goto("http://localhost:4173/");
await page.getByText("ONLINE", { exact: true }).waitFor({ timeout: 30000 });
await page.waitForTimeout(3000); // let busy states settle

const processData = page.getByRole("button", { name: /^process data$/i });
console.log("process data enabled:", await processData.isEnabled().catch(() => false));
await processData.click({ timeout: 5000 });
await page.waitForTimeout(1500);
console.log("dialog count:", await page.locator('[role="dialog"]').count());
const texts = await page.locator("body").textContent();
console.log("body contains 'Upload process dataset':", texts.includes("Upload process dataset"));
console.log("ERRORS:", JSON.stringify(errors));
await browser.close();