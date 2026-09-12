/** Auth context and hooks, kept out of the provider file for fast refresh. */

import { createContext, useContext } from "react";

import type { AuthStatus, User } from "@/features/auth/types";
import type { Role } from "@shared/domain";

export interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  role: Role | null;
  /** Error from the last sign-in attempt, cleared on the next attempt. */
  signInError: unknown;
  isSigningIn: boolean;
  signIn: (email: string, password: string, remember: boolean) => Promise<void>;
  signOut: () => void;
  /** Re-reads `/auth/me`, for after a profile or role change. */
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider.");
  return context;
}

/**
 * The signed-in user, or throw.
 *
 * For components rendered inside a guarded route, where an absent user is a
 * programming error rather than a state to handle.
 */
export function useCurrentUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("useCurrentUser requires an authenticated session.");
  return user;
}
