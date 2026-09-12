/**
 * Dashboard chrome for a signed-in user.
 *
 * A thin adapter that feeds the session's role into `DashboardLayout`, so the
 * layout stays a pure presentational component and remains renderable in tests
 * without an auth provider.
 */

import { useAuth } from "@/features/auth/auth-context";
import { DashboardLayout } from "@/layouts/DashboardLayout";

export function AuthenticatedDashboard() {
  const { role } = useAuth();
  return <DashboardLayout role={role} />;
}
