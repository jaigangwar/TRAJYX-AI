/**
 * Capture dashboard screenshots for visual verification.
 *
 * Usage:
 *   node scripts/screenshot.mjs <out-dir> <path> [path...]
 *
 * Requires the web dev server (or a preview server) to be running on
 * WEB_ORIGIN, default http://localhost:5173. Console errors and failed
 * requests are reported, because a page that renders but logs errors is not
 * actually passing.
 */

import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { chromium } from "playwright";

const WEB_ORIGIN = process.env.WEB_ORIGIN ?? "http://localhost:5173";
const VIEWPORT = { width: 1600, height: 1000 };

const [outDir, ...rawTargets] = process.argv.slice(2);

if (!outDir || rawTargets.length === 0) {
  console.error("Usage: node scripts/screenshot.mjs <out-dir> <path> [path...]");
  process.exit(2);
}

/**
 * Accept `overview` and `/overview` alike. Git Bash on Windows rewrites a
 * leading-slash argument into a filesystem path, so route arguments are
 * passed without one and normalised here.
 */
const targets = rawTargets.map((target) => (target.startsWith("/") ? target : `/${target}`));

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });

let failures = 0;

for (const target of targets) {
  const page = await context.newPage();
  const consoleErrors = [];
  const failedRequests = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.method()} ${request.url()} — ${request.failure()?.errorText}`);
  });

  const url = `${WEB_ORIGIN}${target}`;
  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });
    // Let async panels settle past their loading state.
    await page.waitForTimeout(900);

    const name = target.replace(/^\//, "").replace(/\//g, "-") || "root";
    const file = path.join(outDir, `${name}.png`);
    await page.screenshot({ path: file, fullPage: false });
    console.log(`captured ${target} -> ${file}`);
  } catch (error) {
    failures += 1;
    console.error(`FAILED ${target}: ${error.message}`);
  }

  if (consoleErrors.length > 0) {
    failures += 1;
    console.error(`console errors on ${target}:`);
    for (const entry of consoleErrors) console.error(`  ${entry}`);
  }
  if (failedRequests.length > 0) {
    console.warn(`failed requests on ${target}:`);
    for (const entry of failedRequests) console.warn(`  ${entry}`);
  }

  await page.close();
}

await browser.close();
process.exit(failures > 0 ? 1 : 0);
