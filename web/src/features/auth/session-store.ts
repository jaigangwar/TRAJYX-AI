/**
 * Session persistence.
 *
 * The token is kept in `localStorage`, which is a deliberate trade-off worth
 * stating: it survives a page reload, and it is readable by any script running
 * on this origin, so an XSS bug would expose it. The alternative — an
 * HttpOnly cookie — is stronger, but it requires the API and the dashboard to
 * share a site and brings CSRF handling with it, and the API is designed to
 * be deployed separately and to serve the mobile client the same way.
 *
 * The mitigations that follow from that choice:
 *
 * - The stored token is the *only* thing trusted from storage. The role is
 *   re-fetched from `/auth/me` on every load, so tampering with the stored
 *   copy grants nothing: the server decides what the caller may do.
 * - Expiry is checked before use, so an obviously dead token is discarded
 *   rather than sent.
 * - `sessionStorage` is used instead when the user did not ask to be
 *   remembered, so the session ends with the tab.
 */

import { z } from "zod";

import { userSchema, type Session } from "@/features/auth/types";

const STORAGE_KEY = "trajyx.session";

const storedSessionSchema = z.object({
  token: z.string().min(1),
  user: userSchema,
  expiresAt: z.number(),
});

/** Treat a token as expired slightly early, so it is not sent mid-flight. */
const EXPIRY_SKEW_MS = 30_000;

function backends(): Storage[] {
  // Both are checked on read: the user may have chosen either last time.
  try {
    return [window.localStorage, window.sessionStorage];
  } catch {
    return [];
  }
}

export function loadSession(): Session | null {
  for (const storage of backends()) {
    let raw: string | null = null;
    try {
      raw = storage.getItem(STORAGE_KEY);
    } catch {
      continue;
    }
    if (!raw) continue;

    const parsed = storedSessionSchema.safeParse(safeJsonParse(raw));
    if (!parsed.success) {
      // Corrupt or from an older shape: drop it rather than guessing.
      try {
        storage.removeItem(STORAGE_KEY);
      } catch {
        /* nothing further to do */
      }
      continue;
    }

    if (parsed.data.expiresAt - EXPIRY_SKEW_MS <= Date.now()) {
      clearSession();
      continue;
    }
    return parsed.data;
  }
  return null;
}

export function saveSession(session: Session, remember: boolean): void {
  clearSession();
  try {
    const storage = remember ? window.localStorage : window.sessionStorage;
    storage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Private browsing or blocked storage. The session still works for this
    // page view; it simply will not survive a reload.
  }
}

export function clearSession(): void {
  for (const storage of backends()) {
    try {
      storage.removeItem(STORAGE_KEY);
    } catch {
      /* nothing further to do */
    }
  }
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/** Absolute expiry from a `expires_in` seconds value. */
export function expiryFromSeconds(seconds: number): number {
  return Date.now() + seconds * 1000;
}
