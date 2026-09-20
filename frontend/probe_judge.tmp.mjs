import { chromium } from "@playwright/test";

const browser = await chromium.launch({ channel: "msedge" });
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
await page.goto("http://localhost:4173/");
await page.getByText("ONLINE", { exact: true }).waitFor({ timeout: 30000 });

// select product-quality-control from the dropdown -> should auto-open Process Intelligence
await page.getByRole("button", { name: /process dataset/i }).first().click();
await page.waitForTimeout(500);
const options = page.locator('[role="option"]');
await options.filter({ hasText: "quality-control" }).first().click();
await page.waitForTimeout(5000);

const piText = await page.locator("main").textContent().catch(() => "");
console.log("1) auto-navigated to Process Intelligence:", /what did the data contain|current constraint/i.test(piText));
console.log("2) dataset loaded:", piText.includes("product-quality-control") || piText.includes("quality-control"));
console.log("3) honest bottleneck state:", /no candidate constraint/i.test(piText));
console.log("4) observed output rate section:", /observed output rate/i.test(piText));

// recommendations in the ACTION stage
await page.getByRole("button", { name: /^05 action/i }).click();
await page.waitForTimeout(2000);
const actionText = await page.locator("main").textContent().catch(() => "");
console.log("5) advisory actions present:", /advisory actions/i.test(actionText));
console.log("6) recommendation cards:", (actionText.match(/priority/i) || []).length > 0);

// upload modal now has a browse button
await page.getByRole("button", { name: /process data/i }).first().click();
await page.waitForTimeout(500);
console.log("7) upload modal browse button:", await page.getByRole("button", { name: /browse files/i }).isVisible().catch(() => false));

await browser.close();