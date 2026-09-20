import { chromium } from "@playwright/test";

const browser = await chromium.launch({ channel: "msedge" });
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
await page.goto("http://localhost:4173/");
await page.getByText("ONLINE", { exact: true }).waitFor({ timeout: 30000 });

await page.getByRole("button", { name: /process data/i }).first().click();
await page.waitForTimeout(1000);
console.log("dialog count:", await page.locator('[role="dialog"]').count());
const browse = page.getByRole("button", { name: /browse files/i });
console.log("browse button count:", await browse.count());
console.log("browse visible:", await browse.first().isVisible().catch(() => false));
await browser.close();