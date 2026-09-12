/**
 * End-to-end sign-in check against a running API and dev server.
 *
 * Drives a real browser: fills the login form, waits for the dashboard, and
 * asserts the session survives a reload. Screenshots each state.
 *
 * Usage:
 *   node scripts/e2e-login.mjs <out-dir> <email> <password>
 */

import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { chromium } from "playwright";

const WEB_ORIGIN = process.env.WEB_ORIGIN ?? "http://localhost:5173";
const [outDir, email, password] = process.argv.slice(2);

if (!outDir || !email || !password) {
  console.error("Usage: node scripts/e2e-login.mjs <out-dir> <email> <password>");
  process.exit(2);
}

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 2,
});
const page = await context.newPage();

const consoleErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});

const shot = (name) => page.screenshot({ path: path.join(outDir, `${name}.png`) });
const checks = [];
const check = (label, ok, detail = "") => {
  checks.push({ label, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? ` — ${detail}` : ""}`);
};

try {
  // 1. A protected route must bounce to the login page.
  await page.goto(`${WEB_ORIGIN}/overview`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  check("protected route redirects to /login", page.url().includes("/login"), page.url());
  await shot("01-login");

  // 2. Sign in.
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');

  await page.waitForSelector('nav[aria-label="Main navigation"]', { timeout: 15_000 });
  await page.waitForTimeout(900);
  check("sign-in reaches the dashboard", page.url().includes("/overview"), page.url());
  await shot("02-dashboard");

  // 3. Live API data, not placeholders.
  const serviceVisible = await page.getByText("TRAJYX API").first().isVisible();
  check("dashboard shows live API data", serviceVisible);

  // 4. The session must survive a reload without re-authenticating.
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector('nav[aria-label="Main navigation"]', { timeout: 15_000 });
  check("session survives a page reload", !page.url().includes("/login"), page.url());

  // 5. The profile menu reports the signed-in identity.
  await page.click('button[aria-label*="Account menu"]');
  await page.waitForSelector('[role="menu"]');
  const menuText = await page.locator('[role="menu"]').innerText();
  check("profile menu shows the signed-in account", menuText.includes(email), menuText.split("\n")[0]);
  await shot("03-profile-menu");

  // 6. Sign out returns to the login page and clears the stored session.
  await page.click('[role="menuitem"]');
  await page.waitForSelector("text=Sign in", { timeout: 10_000 });
  const stored = await page.evaluate(() => window.localStorage.getItem("trajyx.session"));
  check("sign-out clears the stored session", stored === null, String(stored));

  // 7. After signing out, the protected route is protected again.
  await page.goto(`${WEB_ORIGIN}/overview`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  check("protected route is protected after sign-out", page.url().includes("/login"), page.url());
  await shot("04-signed-out");
} catch (error) {
  check("run completed without throwing", false, error.message);
  await shot("99-failure");
}

if (consoleErrors.length > 0) {
  console.error("\nconsole errors:");
  for (const entry of consoleErrors) console.error(`  ${entry}`);
}

await browser.close();

const failed = checks.filter((entry) => !entry.ok).length;
console.log(`\n${checks.length - failed}/${checks.length} checks passed`);
process.exit(failed > 0 || consoleErrors.length > 0 ? 1 : 0);
