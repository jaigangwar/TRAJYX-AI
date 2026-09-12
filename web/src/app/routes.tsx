/**
 * Route table.
 *
 * Every dashboard section declared in `navigation.ts` has a route here, so the
 * menu and the router cannot drift apart — a test asserts the two agree.
 * Sections that are not implemented yet render `PhasePendingPage`, which says
 * so plainly instead of showing invented data.
 */

import { Navigate, type RouteObject } from "react-router-dom";

import { DashboardLayout } from "@/layouts/DashboardLayout";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { PhasePendingPage } from "@/pages/PhasePendingPage";

/**
 * Role of the signed-in user. Phase 1 replaces this with the auth context;
 * until then the shell renders the full staff navigation so the layout,
 * routing and permission tables can be exercised.
 */
const PHASE_0_ROLE = "ADMIN" as const;

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <DashboardLayout role={PHASE_0_ROLE} />,
    children: [
      { index: true, element: <Navigate to="/overview" replace /> },

      { path: "overview", element: <OverviewPage /> },

      {
        path: "monitoring",
        element: (
          <PhasePendingPage
            title="Live Monitoring"
            path="/monitoring"
            summary="A grid of configured cameras with live status, current traffic level and risk, opening into a single-camera view with its recent events and detections."
            planned={[
              "Camera grid with ONLINE / OFFLINE / PROCESSING / ALERT status",
              "Per-camera traffic level and current risk score",
              "Single-camera detail view with recent events and detections",
              "Video-file simulation for cameras without a live stream, clearly labeled",
            ]}
          />
        ),
      },
      {
        path: "analysis",
        element: (
          <PhasePendingPage
            title="Video Analysis"
            path="/analysis"
            summary="Upload CCTV footage, run the detection and tracking pipeline as a background job, and review the annotated result beside a live analysis panel and an event timeline."
            planned={[
              "Upload with type and size validation, and job progress",
              "Annotated playback with bounding boxes, track IDs and trajectories",
              "Analysis panel: counts, violations, near misses, collision risk, density",
              "Event timeline with click-to-seek",
            ]}
          />
        ),
      },
      {
        path: "cameras",
        element: (
          <PhasePendingPage
            title="Cameras"
            path="/cameras"
            summary="The camera registry: location, road segment, calibration and signal configuration for each installed unit."
            planned={[
              "Camera CRUD with location and road-segment assignment",
              "Stop line, lane direction and signal-phase configuration",
              "Calibration state, which gates speed estimation",
              "Per-camera processing history",
            ]}
          />
        ),
      },

      {
        path: "risk-map",
        element: (
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
          />
        ),
      },
      {
        path: "violations",
        element: (
          <PhasePendingPage
            title="Violations"
            path="/violations"
            summary="Every detected traffic violation, with the evidence snapshot, detection confidence and review status."
            planned={[
              "Table: timestamp, camera, vehicle, violation, confidence, status, snapshot",
              "Filters by type, date, camera, confidence and review status",
              "Evidence drawer with the source frame and detection metadata",
              "Operator review workflow: confirm or reject",
            ]}
          />
        ),
      },
      {
        path: "near-misses",
        element: (
          <PhasePendingPage
            title="Near Misses"
            path="/near-misses"
            summary="Conflicts that did not become collisions: the events that carry the most predictive value for road risk."
            planned={[
              "Event list with estimated TTC, risk score and contributing factors",
              "Involved track IDs and their trajectories",
              "Evidence clip and snapshot",
              "Severity-coloured risk presentation",
            ]}
          />
        ),
      },
      {
        path: "incidents",
        element: (
          <PhasePendingPage
            title="Incidents"
            path="/incidents"
            summary="Hazards and incidents reported by drivers from the mobile app, queued for operator review."
            planned={[
              "Driver hazard report queue with location and optional photo",
              "Review workflow: pending, reviewing, confirmed, rejected",
              "Map view of reported hazards",
              "Confirmed reports feed back into road-segment risk",
            ]}
          />
        ),
      },
      {
        path: "analytics",
        element: (
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
          />
        ),
      },

      {
        path: "reports",
        element: (
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
          />
        ),
      },
      {
        path: "model-health",
        element: (
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
          />
        ),
      },
      {
        path: "settings",
        element: (
          <PhasePendingPage
            title="Settings"
            path="/settings"
            summary="Deployment configuration: users and roles, alert thresholds, retention and demo mode."
            planned={[
              "User and role administration",
              "Driver alert thresholds, distances and cooldowns",
              "Data retention windows",
              "Demo mode control and demo-data purge",
            ]}
          />
        ),
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
