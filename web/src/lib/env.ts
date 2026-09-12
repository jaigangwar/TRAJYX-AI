/**
 * Typed, validated access to build-time configuration.
 *
 * Nothing in the app reads `import.meta.env` directly. Every value is declared
 * here with an explicit default, so a missing variable surfaces as a clear
 * startup message rather than `undefined` reaching a fetch call.
 */

import { z } from "zod";

const schema = z.object({
  /** Base URL of the TRAJYX API, without a trailing slash. */
  VITE_API_BASE_URL: z
    .string()
    .url()
    .default("http://127.0.0.1:8000")
    .transform((value) => value.replace(/\/+$/, "")),

  /** API version prefix, kept separate so it can be bumped independently. */
  VITE_API_PREFIX: z.string().startsWith("/").default("/api/v1"),

  /**
   * MapLibre-compatible style URL. The default is a no-key raster style so the
   * risk map renders on a clean checkout. Point this at a vector style (or a
   * Mapbox style with a token) for production cartography.
   */
  VITE_MAP_STYLE_URL: z.string().default("/map-styles/trajyx-dark.json"),

  /** Optional Mapbox token. When absent the app stays on MapLibre + the style above. */
  VITE_MAPBOX_TOKEN: z.string().optional(),

  /** Firebase web config. All optional: absent means the local auth path is used. */
  VITE_FIREBASE_API_KEY: z.string().optional(),
  VITE_FIREBASE_AUTH_DOMAIN: z.string().optional(),
  VITE_FIREBASE_PROJECT_ID: z.string().optional(),
  VITE_FIREBASE_STORAGE_BUCKET: z.string().optional(),
  VITE_FIREBASE_APP_ID: z.string().optional(),
});

type RawEnv = Record<string, string | undefined>;

function readEnv(): z.infer<typeof schema> {
  const source = import.meta.env as unknown as RawEnv;

  // Drop empty strings so `.default()` and `.optional()` behave as intended;
  // an unset variable in a .env file arrives as "" rather than undefined.
  const cleaned: RawEnv = {};
  for (const [key, value] of Object.entries(source)) {
    if (typeof value === "string" && value.trim() === "") continue;
    cleaned[key] = value;
  }

  const parsed = schema.safeParse(cleaned);
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((issue) => `  ${issue.path.join(".")}: ${issue.message}`)
      .join("\n");
    throw new Error(
      `Invalid web configuration. Check web/.env against web/.env.example:\n${issues}`,
    );
  }
  return parsed.data;
}

export const env = readEnv();

/** Fully-qualified API root, e.g. `http://127.0.0.1:8000/api/v1`. */
export const API_ROOT = `${env.VITE_API_BASE_URL}${env.VITE_API_PREFIX}`;

/**
 * True when a Firebase web app is configured. The auth layer uses this to pick
 * between Firebase Authentication and the local development token flow.
 */
export const firebaseConfigured = Boolean(
  env.VITE_FIREBASE_API_KEY && env.VITE_FIREBASE_PROJECT_ID && env.VITE_FIREBASE_AUTH_DOMAIN,
);
