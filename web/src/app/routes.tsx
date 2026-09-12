/**
 * Route table.
 *
 * Every dashboard section declared in `navigation.ts` has a route here, so the
 * menu and the router cannot drift apart — a test asserts the two agree.
 * Sections that are not implemented yet render `PhasePendingPage`, which says
 * so plainly instead of showing invented data.
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
import { CamerasPage } from "@/pages/CamerasPage";
import { DriverNoticePage } from "@/pages/DriverNoticePage";
import { EventsPage } from "@/pages/EventsPage";
import { MonitoringPage } from "@/pages/MonitoringPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { PhasePendingPage } from "@/pages/PhasePendingPage";
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
        path: "analysis",
        element: guarded("/analysis", <AnalysisPage />),
      },
      {
        path: "cameras",
        element: guarded("/cameras", <CamerasPage />),
      },

      {
        path: "risk-map",
        element: guarded(
          "/risk-map",
          <PhasePendingPage
            title="Risk Map"
            path="/risk-map"
            summary="A full-screen GIS view of road-segment risk, risk zones, cameras and events, with filters and a detail panel for any selected hotspot."
            planned={[
              "Road segments and risk zones coloured by risk level",
              "Camera, violation and near-miss layers",
              "Filters: risk level, event type, time range, camera, road",
              "Hotspot detail: score, contributing factors, peak time, recent events",
            ]}
          />,
        ),
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
        element: guarded(
          "/analytics",
          <PhasePendingPage
            title="Analytics"
            path="/analytics"
            summary="Aggregate road-safety analysis across time, location and vehicle class."
            planned={[
              "Risk by hour, day and weekday",
              "Violations by category and near misses by hour",
              "Traffic composition by vehicle class",
              "Helmet compliance, hard-braking and wrong-way frequency",
            ]}
          />,
        ),
      },

      {
        path: "reports",
        element: guarded(
          "/reports",
          <PhasePendingPage
            title="Reports"
            path="/reports"
            summary="Generated road-safety reporting for operators and traffic authorities."
            planned={[
              "Daily, weekly, road-safety, violation and risk-hotspot reports",
              "CSV and JSON export",
              "PDF rendering where practical",
              "Report history with the parameters each run used",
            ]}
          />,
        ),
      },
      {
        path: "model-health",
        element: guarded(
          "/model-health",
          <PhasePendingPage
            title="Model Health"
            path="/model-health"
            summary="The model registry and its measured performance. Only metrics produced by an actual training or evaluation run are ever displayed."
            planned={[
              "Registered model versions with dataset version and training date",
              "Precision, recall and F1 from the evaluation run that produced them",
              "Measured inference latency",
              "Health state: healthy, warning, needs attention",
            ]}
          />,
        ),
      },
      {
        path: "settings",
        element: guarded("/settings", <SettingsPage />),
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
