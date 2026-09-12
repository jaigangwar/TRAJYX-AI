/**
 * Fetch an authenticated media URL into a blob URL a `<video>` can play.
 *
 * The video element cannot send an Authorization header, and footage is
 * deliberately not served from a public URL, so it is fetched with the bearer
 * token and handed to the element as a blob.
 */

import { useEffect, useState } from "react";

import { getAuthToken } from "@/features/auth/token-holder";

interface Loaded {
  /** The source this result belongs to, so a stale result is never shown. */
  source: string;
  url: string | null;
  error: unknown;
}

interface State {
  url: string | null;
  isLoading: boolean;
  error: unknown;
}

export function useAuthedMedia(source: string | null): State {
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!source) return;

    let objectUrl: string | null = null;
    let cancelled = false;
    const controller = new AbortController();

    const load = async () => {
      try {
        const token = getAuthToken();
        const response = await fetch(source, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`Media request failed (${response.status})`);

        const blob = await response.blob();
        if (cancelled) return;

        objectUrl = URL.createObjectURL(blob);
        setLoaded({ source, url: objectUrl, error: null });
      } catch (error) {
        if (cancelled || (error instanceof DOMException && error.name === "AbortError")) return;
        setLoaded({ source, url: null, error });
      }
    };

    void load();

    return () => {
      cancelled = true;
      controller.abort();
      // Revoking is required: a few unreleased video blobs is tens of MB held
      // in memory for the life of the tab.
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source]);

  // Derived rather than stored, so changing the source does not need a
  // synchronous setState inside the effect.
  const current = loaded?.source === source ? loaded : null;

  return {
    url: current?.url ?? null,
    isLoading: source !== null && current === null,
    error: current?.error ?? null,
  };
}
