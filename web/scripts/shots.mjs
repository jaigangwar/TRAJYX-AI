/**
 * Sign in, then screenshot dashboard pages.
 *
 * Usage: node scripts/shots.mjs <out-dir> <email> <password> <path> [path...]
 * Paths may be given with or without a leading slash.
 */

import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { chromium } from "playwright";

const WEB_ORIGIN = process.env.WEB_ORIGIN ?? "http://localhost:5173";
const [outDir, email, password, ...rawTargets] = process.argv.slice(2);

if (!outDir || !email || !password || rawTargets.length === 0) {
  console.error("Usage: node scripts/shots.mjs <out-dir> <email> <password> <path> [path...]");
  process.exit(2);
}

const targets = rawTargets.map((t) => (t.startsWith("/") ? t : `/${t}`));
await mkdir(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 2,
});
const page = await context.newPage();

const consoleErrors = [];
page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(m.text());
});

await page.goto(`${WEB_ORIGIN}/login`, { waitUntil: "networkidle" });
await page.fill("#email", email);
await page.fill("#password", password);
await page.click('button[type="submit"]');
await page.waitForSelector('nav[aria-label="Main navigation"]', { timeout: 20_000 });
console.log("signed in");

let failures = 0;
for (const target of targets) {
  try {
    await page.goto(`${WEB_ORIGIN}${target}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1100);
    const name = target.replace(/^\//, "").replace(/\//g, "-") || "root";
    await page.screenshot({ path: path.join(outDir, `${name}.png`) });
    console.log(`captured ${target}`);
  } catch (error) {
    failures += 1;
    console.error(`FAILED ${target}: ${error.message}`);
  }
}

if (consoleErrors.length > 0) {
  failures += 1;
  console.error("console errors:");
  for (const entry of consoleErrors) console.error(`  ${entry}`);
}

await browser.close();
process.exit(failures > 0 ? 1 : 0);
