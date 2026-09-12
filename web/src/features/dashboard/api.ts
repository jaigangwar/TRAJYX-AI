/** Dashboard, camera and event queries. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/lib/api-client";
import {
  CAMERASTATUS_VALUES,
  DATAORIGIN_VALUES,
  EVENTCATEGORY_VALUES,
  EVENTTYPE_VALUES,
  REPORTSTATUS_VALUES,
  RISKLEVEL_VALUES,
  SEVERITY_VALUES,
  SIGNALSTATE_VALUES,
} from "@shared/domain";

/* ------------------------------------------------------------------ schemas */

const geoPoint = z.object({ latitude: z.number(), longitude: z.number() });

const metric = z.object({
  value: z.number().nullable(),
  available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  unit: z.string().nullable().optional(),
});
export type Metric = z.infer<typeof metric>;

export const cameraSchema = z.object({
  id: z.string(),
  name: z.string(),
  location: geoPoint,
  description: z.string().nullable().optional(),
  road_segment_id: z.string().nullable().optional(),
  road_name: z.string().nullable().optional(),
  status: z.enum(CAMERASTATUS_VALUES),
  signal_state: z.enum(SIGNALSTATE_VALUES),
  stream_url: z.string().nullable().optional(),
  frame_width: z.number().nullable().optional(),
  frame_height: z.number().nullable().optional(),
  frame_rate: z.number().nullable().optional(),
  stop_line: z
    .object({
      start: z.object({ x: z.number(), y: z.number() }),
      end: z.object({ x: z.number(), y: z.number() }),
    })
    .nullable()
    .optional(),
  lane_directions: z.array(
    z.object({
      lane_index: z.number(),
      heading_deg: z.number(),
      label: z.string().nullable().optional(),
    }),
  ),
  calibration: z
    .object({
      metres_per_pixel_at_reference: z.number(),
      reference_y: z.number(),
      notes: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  capabilities: z.object({
    speed_estimation: z.boolean(),
    wrong_way_detection: z.boolean(),
    stop_line_violation: z.boolean(),
    red_light_violation: z.boolean(),
  }),
  current_risk_score: z.number().nullable().optional(),
  current_risk_level: z.enum(RISKLEVEL_VALUES).nullable().optional(),
  last_event_at: z.string().nullable().optional(),
  last_seen_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type Camera = z.infer<typeof cameraSchema>;

export const eventSchema = z.object({
  id: z.string(),
  event_type: z.enum(EVENTTYPE_VALUES),
  category: z.enum(EVENTCATEGORY_VALUES),
  timestamp: z.string(),
  camera_id: z.string().nullable().optional(),
  camera_name: z.string().nullable().optional(),
  road_segment_id: z.string().nullable().optional(),
  location: geoPoint.nullable().optional(),
  severity: z.enum(SEVERITY_VALUES),
  confidence: z.number().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  risk_level: z.enum(RISKLEVEL_VALUES).nullable().optional(),
  origin: z.enum(DATAORIGIN_VALUES),
  model_version: z.string().nullable().optional(),
  track_ids: z.array(z.number()),
  details: z.record(z.string(), z.unknown()),
  video_analysis_id: z.string().nullable().optional(),
  frame_index: z.number().nullable().optional(),
  evidence_key: z.string().nullable().optional(),
  review_status: z.enum(REPORTSTATUS_VALUES).nullable().optional(),
});
export type SafetyEvent = z.infer<typeof eventSchema>;

export const summarySchema = z.object({
  generated_at: z.string(),
  window_hours: z.number(),
  demo_mode: z.boolean(),
  cameras: z.object({
    total: z.number(),
    online: z.number(),
    offline: z.number(),
    processing: z.number(),
    alert: z.number(),
  }),
  events: z.object({
    window_hours: z.number(),
    total: z.number(),
    violations: z.number(),
    behaviour: z.number(),
    interactions: z.number(),
    reports: z.number(),
    near_misses: z.number(),
    critical: z.number(),
    demo: z.number(),
  }),
  risk: z.object({
    average_risk: metric,
    highest_risk_level: z.enum(RISKLEVEL_VALUES).nullable().optional(),
    high_risk_zones: metric,
    zones_by_level: z.record(z.string(), z.number()),
  }),
  pipeline: z.object({
    vehicles_detected: metric,
    pedestrians_detected: metric,
    videos_analysed: metric,
  }),
  recent_events: z.array(eventSchema),
});
export type DashboardSummary = z.infer<typeof summarySchema>;

const page = <T extends z.ZodTypeAny>(item: T) =>
  z.object({
    items: z.array(item),
    next_cursor: z.string().nullable().optional(),
    total: z.number().nullable().optional(),
  });

/* -------------------------------------------------------------------- hooks */

export const keys = {
  summary: (hours: number) => ["dashboard", "summary", hours] as const,
  cameras: (filters?: unknown) => ["cameras", filters ?? null] as const,
  camera: (id: string) => ["cameras", id] as const,
  cameraGrid: ["dashboard", "camera-grid"] as const,
  events: (filters?: unknown) => ["events", filters ?? null] as const,
  event: (id: string) => ["events", id] as const,
};

export function useDashboardSummary(windowHours = 24) {
  return useQuery({
    queryKey: keys.summary(windowHours),
    queryFn: ({ signal }) =>
      api.get("/dashboard/summary", {
        query: { window_hours: windowHours },
        schema: summarySchema,
        signal,
      }),
    refetchInterval: 30_000,
  });
}

export function useCameras(filters: { status?: string; road_segment_id?: string } = {}) {
  return useQuery({
    queryKey: keys.cameras(filters),
    queryFn: ({ signal }) =>
      api.get("/cameras", { query: filters, schema: page(cameraSchema), signal }),
  });
}

export function useCamera(id: string | null) {
  return useQuery({
    queryKey: keys.camera(id ?? ""),
    queryFn: ({ signal }) => api.get(`/cameras/${id}`, { schema: cameraSchema, signal }),
    enabled: Boolean(id),
  });
}

export function useCameraGrid() {
  return useQuery({
    queryKey: keys.cameraGrid,
    queryFn: ({ signal }) =>
      api.get("/dashboard/camera-grid", {
        schema: z.object({ items: z.array(cameraSchema), total: z.number() }),
        signal,
      }),
    refetchInterval: 15_000,
  });
}

export interface EventFilters {
  [key: string]: string | number | undefined;
  event_type?: string;
  category?: string;
  camera_id?: string;
  review_status?: string;
  origin?: string;
  min_confidence?: number;
  min_risk_score?: number;
  since?: string;
  limit?: number;
}

export function useEvents(filters: EventFilters = {}) {
  return useQuery({
    queryKey: keys.events(filters),
    queryFn: ({ signal }) =>
      api.get("/events", { query: filters, schema: page(eventSchema), signal }),
  });
}

export function useCreateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: unknown) => api.post("/cameras", { body, schema: cameraSchema }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cameras"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useUpdateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: unknown }) =>
      api.patch(`/cameras/${id}`, { body, schema: cameraSchema }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cameras"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useDeleteCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/cameras/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cameras"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useReviewEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, note }: { id: string; status: string; note?: string }) =>
      api.patch(`/events/${id}/review`, { query: { status, note }, schema: eventSchema }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["events"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
