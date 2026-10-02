/** Screenshot the Reports page with a report open, and its export flow. */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const ORIGIN = process.env.WEB_ORIGIN ?? "http://localhost:5173";
const [outDir, email, password] = process.argv.slice(2);
await mkdir(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 2,
  acceptDownloads: true,
});
const page = await context.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

await page.goto(`${ORIGIN}/login`, { waitUntil: "networkidle" });
await page.fill("#email", email);
await page.fill("#password", password);
await page.click('button[type="submit"]');
await page.waitForSelector('nav[aria-label="Main navigation"]', { timeout: 20000 });

await page.goto(`${ORIGIN}/reports`, { waitUntil: "networkidle" });
await page.waitForTimeout(900);
await page.screenshot({ path: path.join(outDir, "reports-empty.png") });

// Open the newest stored report from the history list.
const history = page.locator("aside ul li button");
const count = await history.count();
console.log("history entries:", count);
if (count === 0) {
  console.log("aside text:", (await page.locator("aside").innerText()).slice(0, 500));
  await browser.close();
  process.exit(1);
}
await history.nth(0).click();
await page.waitForTimeout(1400);
await page.screenshot({ path: path.join(outDir, "reports-open.png"), fullPage: true });

// Exercise the CSV download through the real UI path.
const [download] = await Promise.all([
  page.waitForEvent("download", { timeout: 20000 }),
  page.getByRole("button", { name: "CSV" }).click(),
]);
console.log("downloaded:", download.suggestedFilename());

console.log(errors.length ? `console errors: ${errors.join(" | ").slice(0, 400)}` : "no console errors");
await browser.close();
