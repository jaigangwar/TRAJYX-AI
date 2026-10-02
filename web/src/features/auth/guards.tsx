/**
 * Route guards.
 *
 * These control what the dashboard *renders*. They are not access control —
 * the API enforces every role boundary independently, and a hand-written
 * request from a browser console is refused there. Guards exist so a user is
 * never shown a screen that would only produce 403s.
 */

import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { defaultRouteForRole } from "@/app/navigation";
import { TrajyxMark } from "@/components/brand/Logo";
import { useAuth } from "@/features/auth/auth-context";
import { isStaff } from "@/features/auth/types";
import type { Role } from "@shared/domain";

/** Shown while a stored session is being verified against the API. */
function SessionLoading() {
  return (
    <div
      className="bg-ground flex h-dvh flex-col items-center justify-center gap-3"
      role="status"
      aria-live="polite"
    >
      <TrajyxMark size={30} className="text-ink-subtle" title="TRAJYX" />
      <p className="text-ink-subtle text-xs">Verifying session…</p>
    </div>
  );
}

/** Requires any authenticated session. */
export function RequireAuth({ children }: { children?: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <SessionLoading />;
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return children ? <>{children}</> : <Outlet />;
}

/** Requires a role that can use the dashboard. */
export function RequireStaff({ children }: { children?: ReactNode }) {
  const { status, role } = useAuth();
  const location = useLocation();
  if (status === "loading") return <SessionLoading />;
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  if (!isStaff(role)) return <Navigate to="/driver-notice" replace />;
  return children ? <>{children}</> : <Outlet />;
}

interface RequireRoleProps {
  roles: readonly Role[];
  children?: ReactNode;
}

/** Requires one of the listed roles. */
export function RequireRole({ roles, children }: RequireRoleProps) {
  const { status, role } = useAuth();
  const location = useLocation();
  if (status === "loading") return <SessionLoading />;
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  if (!role || !roles.includes(role)) return <Navigate to={defaultRouteForRole(role)} replace />;
  return children ? <>{children}</> : <Outlet />;
}
