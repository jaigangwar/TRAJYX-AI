/** Inspect the live MapLibre instance after the risk map loads. */

import process from "node:process";

import { chromium } from "playwright";

const WEB_ORIGIN = process.env.WEB_ORIGIN ?? "http://localhost:5173";
const [email, password] = process.argv.slice(2);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

page.on("console", (message) => {
  if (message.type() === "error" || message.type() === "warning") {
    console.log(`[${message.type()}] ${message.text()}`);
  }
});

// Expose the map for inspection.
await page.addInitScript(() => {
  const original = window.HTMLCanvasElement.prototype.getContext;
  void original;
});

await page.goto(`${WEB_ORIGIN}/login`, { waitUntil: "networkidle" });
await page.fill("#email", email);
await page.fill("#password", password);
await page.click('button[type="submit"]');
await page.waitForSelector('nav[aria-label="Main navigation"]', { timeout: 20_000 });

await page.goto(`${WEB_ORIGIN}/risk-map`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

const report = await page.evaluate(() => {
  const map = window.__trajyxMap;
  if (!map) return { error: "map not exposed" };
  const sourceIds = ["trajyx-segments", "trajyx-zones", "trajyx-cameras", "trajyx-probe"];
  return {
    styleLoaded: map.isStyleLoaded(),
    loaded: map.loaded(),
    center: map.getCenter(),
    zoom: map.getZoom(),
    layers: map.getStyle().layers.map((l) => l.id),
    sources: sourceIds.map((id) => {
      const source = map.getSource(id);
      const data = source?._data;
      return { id, present: Boolean(source), features: data?.features?.length ?? null };
    }),
    renderedSegments: map.queryRenderedFeatures({ layers: ["segment-line"] }).length,
  };
});
console.log("map:", JSON.stringify(report, null, 2));

// Inject a feature by hand: if this renders, the layer paint is fine and the
// problem is upstream in the React sync. If it does not, the layer is wrong.
const manual = await page.evaluate(() => {
  const map = window.__trajyxMap;
  const source = map.getSource("trajyx-segments");
  source.setData({
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [77.209, 28.6139],
            [77.2128, 28.6152],
            [77.2171, 28.6168],
          ],
        },
        properties: { id: "manual", colour: "#e5484d", scored: true, selected: false },
      },
    ],
  });
  return new Promise((resolve) => {
    map.once("idle", () =>
      resolve({ rendered: map.queryRenderedFeatures({ layers: ["segment-line"] }).length }),
    );
  });
});
console.log("manual setData ->", JSON.stringify(manual));

// Read the API directly from the page session to confirm shape.
const api = await page.evaluate(async () => {
  const raw = window.localStorage.getItem("trajyx.session");
  const token = raw ? JSON.parse(raw).token : null;
  const response = await fetch("http://127.0.0.1:8000/api/v1/risk/segments", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const segments = await response.json();
  return {
    status: response.status,
    count: Array.isArray(segments) ? segments.length : null,
    first: Array.isArray(segments) && segments[0]
      ? {
          name: segments[0].name,
          risk_level: segments[0].risk_level,
          pathLength: segments[0].path?.length,
          firstPoint: segments[0].path?.[0],
        }
      : null,
  };
});
console.log("api:", JSON.stringify(api, null, 2));

await page.screenshot({ path: "../.verify/phase10/debug-map.png" });
await browser.close();
