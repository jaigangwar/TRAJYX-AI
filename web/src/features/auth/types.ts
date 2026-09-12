/**
 * Session contracts.
 *
 * Responses are validated with Zod rather than cast, so a backend change
 * surfaces as a named contract mismatch instead of `undefined` reaching a
 * role check.
 */

import { z } from "zod";

import { ROLE_VALUES, type Role } from "@shared/domain";

export const userSchema = z.object({
  id: z.string(),
  email: z.string(),
  display_name: z.string().nullable().optional(),
  role: z.enum(ROLE_VALUES),
  status: z.string(),
  created_at: z.string().nullable().optional(),
  last_login_at: z.string().nullable().optional(),
});

export type User = z.infer<typeof userSchema>;

export const tokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
  refresh_token: z.string().nullable().optional(),
  user: userSchema,
});

export type TokenResponse = z.infer<typeof tokenResponseSchema>;

/** Roles that may use the dashboard at all. Drivers use the mobile app. */
export const STAFF_ROLES: readonly Role[] = ["ADMIN", "TRAFFIC_OPERATOR", "ANALYST"];

export function isStaff(role: Role | null | undefined): boolean {
  return role != null && STAFF_ROLES.includes(role);
}

/** Human-readable role names, used in the profile menu and user administration. */
export const ROLE_LABELS: Record<Role, string> = {
  ADMIN: "Administrator",
  TRAFFIC_OPERATOR: "Traffic operator",
  ANALYST: "Analyst",
  DRIVER: "Driver",
};

export interface Session {
  token: string;
  user: User;
  /** Epoch milliseconds at which the token stops being accepted. */
  expiresAt: number;
}

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";
