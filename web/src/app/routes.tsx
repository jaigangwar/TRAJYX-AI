/**
 * Route table.
 *
 * Every dashboard section declared in `navigation.ts` has a route here, so the
 * menu and the router cannot drift apart — a test asserts the two agree. Every
 * section now resolves to a real page; the placeholder that stood in for
 * unbuilt sections has been removed along with the last of them.
 *
 * Each section is additionally wrapped in `RequireRole` with the same role list
 * `navigation.ts` declares, so a deep link cannot reach a section the sidebar
 * hides. The API enforces the same boundaries independently — these guards
 * decide what is *rendered*, not what is *permitted*.
 */

import { Navigate, type RouteObject } from "react-router-dom";

import { NAV_ITEMS } from "@/app/navigation";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireRole, RequireStaff } from "@/features/auth/guards";
import { AuthenticatedDashboard } from "@/layouts/AuthenticatedDashboard";
import { AnalysisPage } from "@/pages/AnalysisPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { CamerasPage } from "@/pages/CamerasPage";
import { DriverNoticePage } from "@/pages/DriverNoticePage";
import { EventsPage } from "@/pages/EventsPage";
import { ModelHealthPage } from "@/pages/ModelHealthPage";
import { MonitoringPage } from "@/pages/MonitoringPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SimulationPage } from "@/pages/SimulationPage";
import { RiskMapPage } from "@/pages/RiskMapPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { SettingsPage } from "@/pages/SettingsPage";

/**
 * Wrap a section in the role list `navigation.ts` declares for it.
 *
 * Reading the roles from the nav table rather than repeating them here means
 * the menu and the guard cannot disagree — if they could, one of them would
 * eventually be wrong, and the wrong one to trust is the guard.
 */
function guarded(path: string, element: React.ReactNode): React.ReactNode {
  const item = NAV_ITEMS.find((entry) => entry.path === path);
  if (!item) {
    throw new Error(`Route ${path} has no entry in NAV_ITEMS; add one or remove the route.`);
  }
  return <RequireRole roles={item.roles}>{element}</RequireRole>;
}

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  { path: "/driver-notice", element: <DriverNoticePage /> },
  {
    path: "/",
    element: (
      <RequireStaff>
        <AuthenticatedDashboard />
      </RequireStaff>
    ),
    children: [
      { index: true, element: <Navigate to="/overview" replace /> },

      { path: "overview", element: guarded("/overview", <OverviewPage />) },

      {
        path: "monitoring",
        element: guarded("/monitoring", <MonitoringPage />),
      },
      {
        path: "simulation",
        element: guarded("/simulation", <SimulationPage />),
      },
      {
        path: "analysis",
        element: guarded("/analysis", <AnalysisPage />),
      },
      {
        path: "cameras",
        element: guarded("/cameras", <CamerasPage />),
      },

      {
        path: "risk-map",
        element: guarded("/risk-map", <RiskMapPage />),
      },
      {
        path: "violations",
        element: guarded(
          "/violations",
          <EventsPage
            title="Violations"
            subtitle="Detected traffic violations and their review state"
            preset={{ category: "VIOLATION" }}
            emptyMessage="No violations recorded for these filters."
            emptyHint="Violations appear once footage has been analysed. Each camera can only report the violations its configured geometry supports."
          />,
        ),
      },
      {
        path: "near-misses",
        element: guarded(
          "/near-misses",
          <EventsPage
            title="Near Misses"
            subtitle="Conflicts that did not become collisions"
            preset={{ event_type: "NEAR_MISS" }}
            showTtc
            emptyMessage="No near misses recorded for these filters."
            emptyHint="Near misses are produced by the interaction and collision-risk engines in phase 8."
          />,
        ),
      },
      {
        path: "incidents",
        element: guarded(
          "/incidents",
          <EventsPage
            title="Incidents"
            subtitle="Hazards reported by drivers, queued for review"
            preset={{ event_type: "HAZARD_REPORT" }}
            emptyMessage="No hazard reports submitted."
            emptyHint="Drivers submit these from the mobile app; reporting lands in phase 15."
          />,
        ),
      },
      {
        path: "analytics",
        element: guarded("/analytics", <AnalyticsPage />),
      },

      {
        path: "reports",
        element: guarded("/reports", <ReportsPage />),
      },
      {
        path: "model-health",
        element: guarded("/model-health", <ModelHealthPage />),
      },
      {
        path: "settings",
        element: guarded("/settings", <SettingsPage />),
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
