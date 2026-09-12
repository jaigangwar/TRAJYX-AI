/**
 * Session lifecycle.
 *
 * On mount, a stored token is verified against `/auth/me` before the app is
 * shown. That round trip is the point: the role that drives every permission
 * check comes from the server on each load, never from the stored copy, so a
 * tampered `localStorage` entry grants nothing.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { AuthContext, type AuthContextValue } from "@/features/auth/auth-context";
import {
  clearSession,
  expiryFromSeconds,
  loadSession,
  saveSession,
} from "@/features/auth/session-store";
import { getAuthToken, setAuthToken } from "@/features/auth/token-holder";
import {
  tokenResponseSchema,
  userSchema,
  type AuthStatus,
  type Session,
  type User,
} from "@/features/auth/types";
import { ApiError, api, setTokenProvider, setUnauthorizedHandler } from "@/lib/api-client";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [signInError, setSignInError] = useState<unknown>(null);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const queryClient = useQueryClient();

  const endSession = useCallback(() => {
    clearSession();
    setAuthToken(null);
    setSession(null);
    setStatus("unauthenticated");
    // Drop every cached response: the next user must not see the previous
    // user's data, and a 403 should not be served from cache either.
    queryClient.clear();
  }, [queryClient]);

  // Registered before any request can be made, so nothing races ahead of it.
  // The client reads the token from the module-scoped holder rather than from
  // React state, so it always sees the current value.
  useEffect(() => {
    setTokenProvider(getAuthToken);
    setUnauthorizedHandler(endSession);
    return () => {
      setTokenProvider(() => null);
      setUnauthorizedHandler(null);
    };
  }, [endSession]);

  // Restore and verify a stored session on mount.
  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      const stored = loadSession();
      if (!stored) {
        setStatus("unauthenticated");
        return;
      }

      // Make the token available to the verification request itself.
      setAuthToken(stored.token);

      try {
        const user = await api.get<User>("/auth/me", { schema: userSchema });
        if (cancelled) return;

        // Trust the server's copy of the profile, not the stored one.
        setSession({ ...stored, user });
        setStatus("authenticated");
      } catch (error) {
        if (cancelled) return;
        // A 401 or 403 means the token is dead or the account was suspended.
        // Any other failure (the API being down) also fails closed: showing a
        // dashboard whose permissions could not be confirmed would be worse
        // than asking the user to sign in again.
        if (!(error instanceof ApiError)) {
          console.error("Session verification failed", error);
        }
        endSession();
      }
    };

    void restore();
    return () => {
      cancelled = true;
    };
  }, [endSession]);

  const signIn = useCallback(
    async (email: string, password: string, remember: boolean) => {
      setIsSigningIn(true);
      setSignInError(null);
      try {
        const response = await api.post("/auth/login", {
          body: { email, password },
          schema: tokenResponseSchema,
          anonymous: true,
        });

        const next: Session = {
          token: response.access_token,
          user: response.user,
          expiresAt: expiryFromSeconds(response.expires_in),
        };

        saveSession(next, remember);
        setAuthToken(next.token);
        // Anything cached while signed out, or as a previous user, is stale.
        queryClient.clear();
        setSession(next);
        setStatus("authenticated");
      } catch (error) {
        setSignInError(error);
        throw error;
      } finally {
        setIsSigningIn(false);
      }
    },
    [queryClient],
  );

  const signOut = useCallback(() => {
    // Fire and forget: the server revokes what it can, but the local session
    // must end even if that request fails.
    void api.post("/auth/logout").catch(() => undefined);
    endSession();
  }, [endSession]);

  const refresh = useCallback(async () => {
    if (!getAuthToken()) return;
    try {
      const user = await api.get<User>("/auth/me", { schema: userSchema });
      setSession((current) => (current ? { ...current, user } : current));
    } catch (error) {
      if (error instanceof ApiError && (error.isAuthFailure || error.status === 403)) {
        endSession();
      }
    }
  }, [endSession]);

  // End the session client-side at the token's deadline, so the user is told
  // plainly rather than meeting 401s on their next action. `loadSession` and
  // `signIn` both reject an already-expired token, so the timer only ever
  // schedules into the future.
  useEffect(() => {
    if (!session) return undefined;
    const remaining = Math.max(0, session.expiresAt - Date.now());
    const timer = window.setTimeout(endSession, remaining);
    return () => window.clearTimeout(timer);
  }, [session, endSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: session?.user ?? null,
      role: session?.user.role ?? null,
      signInError,
      isSigningIn,
      signIn,
      signOut,
      refresh,
    }),
    [status, session, signInError, isSigningIn, signIn, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
