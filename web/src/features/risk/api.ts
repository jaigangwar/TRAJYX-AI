/** Road segment, risk zone and alert queries. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/lib/api-client";
import { ALERTLEVEL_VALUES, EVENTTYPE_VALUES, RISKLEVEL_VALUES } from "@shared/domain";

const geoPoint = z.object({ latitude: z.number(), longitude: z.number() });

export const segmentSchema = z.object({
  id: z.string(),
  name: z.string(),
  road_name: z.string().nullable().optional(),
  path: z.array(geoPoint),
  length_m: z.number(),
  bearing_deg: z.number().nullable().optional(),
  speed_limit_kmh: z.number().nullable().optional(),
  lanes: z.number().nullable().optional(),
  one_way: z.boolean(),
  risk_score: z.number().nullable().optional(),
  risk_level: z.enum(RISKLEVEL_VALUES).nullable().optional(),
  risk_confidence: z.number().nullable().optional(),
  event_count: z.number(),
  near_miss_count: z.number(),
  violation_count: z.number(),
  top_risk_factors: z.array(z.string()),
  peak_hour: z.number().nullable().optional(),
  last_event_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
});
export type RoadSegment = z.infer<typeof segmentSchema>;

export const zoneSchema = z.object({
  id: z.string(),
  road_segment_id: z.string().nullable().optional(),
  road_name: z.string().nullable().optional(),
  centre: geoPoint,
  radius_m: z.number(),
  risk_score: z.number(),
  risk_level: z.enum(RISKLEVEL_VALUES),
  confidence: z.number(),
  top_risk_factors: z.array(z.string()),
  event_count: z.number(),
  near_miss_count: z.number(),
  violation_count: z.number(),
  dominant_event_type: z.enum(EVENTTYPE_VALUES).nullable().optional(),
  peak_hour: z.number().nullable().optional(),
  bearing_deg: z.number().nullable().optional(),
  computed_at: z.string().nullable().optional(),
  window_hours: z.number().nullable().optional(),
  origin: z.string(),
});
export type RiskZone = z.infer<typeof zoneSchema>;

export const segmentDetailSchema = z.object({
  segment: segmentSchema,
  risk_by_hour: z.array(
    z.object({
      hour: z.number(),
      risk_score: z.number(),
      risk_level: z.enum(RISKLEVEL_VALUES),
      event_count: z.number(),
    }),
  ),
  event_breakdown: z.record(z.string(), z.number()),
  recent_events: z.array(z.record(z.string(), z.unknown())),
  cameras: z.array(z.record(z.string(), z.unknown())),
});
export type SegmentDetail = z.infer<typeof segmentDetailSchema>;

export const alertEvaluationSchema = z.object({
  evaluated_at: z.string(),
  position: geoPoint,
  heading_deg: z.number().nullable().optional(),
  current_segment_id: z.string().nullable().optional(),
  current_segment_name: z.string().nullable().optional(),
  nearby: z.array(
    z.object({
      zone: zoneSchema,
      distance_m: z.number(),
      bearing_deg: z.number(),
      is_ahead: z.boolean(),
      eta_seconds: z.number().nullable().optional(),
    }),
  ),
  alert: z
    .object({
      zone_id: z.string(),
      level: z.enum(ALERTLEVEL_VALUES),
      risk_score: z.number(),
      risk_level: z.enum(RISKLEVEL_VALUES),
      distance_m: z.number(),
      road_name: z.string().nullable().optional(),
      headline: z.string(),
      detail: z.string().nullable().optional(),
      factors: z.array(z.string()),
      recommendations: z.array(z.string()),
      cooldown_seconds: z.number(),
      origin: z.string(),
    })
    .nullable()
    .optional(),
  suppressed_reason: z.string().nullable().optional(),
});
export type AlertEvaluation = z.infer<typeof alertEvaluationSchema>;

export function useSegments(minimumRisk?: number) {
  return useQuery({
    queryKey: ["risk", "segments", minimumRisk ?? null],
    queryFn: ({ signal }) =>
      api.get("/risk/segments", {
        query: minimumRisk !== undefined ? { minimum_risk: minimumRisk } : {},
        schema: z.array(segmentSchema),
        signal,
      }),
  });
}

export function useZones(minimumLevel?: string) {
  return useQuery({
    queryKey: ["risk", "zones", minimumLevel ?? null],
    queryFn: ({ signal }) =>
      api.get("/risk/zones", {
        query: minimumLevel ? { minimum_level: minimumLevel } : {},
        schema: z.array(zoneSchema),
        signal,
      }),
  });
}

export function useSegmentDetail(segmentId: string | null) {
  return useQuery({
    queryKey: ["risk", "segment", segmentId],
    queryFn: ({ signal }) =>
      api.get(`/risk/segments/${segmentId}`, { schema: segmentDetailSchema, signal }),
    enabled: Boolean(segmentId),
  });
}

export function useAggregateRisk() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (windowHours: number) =>
      api.post("/risk/aggregate", {
        query: { window_hours: windowHours },
        schema: z.object({ segments_scored: z.number(), zones_created: z.number() }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["risk"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

/** Evaluate the alert engine at an arbitrary point, for operator inspection. */
export function useEvaluateAlert() {
  return useMutation({
    mutationFn: (body: {
      latitude: number;
      longitude: number;
      heading_deg?: number;
      speed_kmh?: number;
      radius_m?: number;
    }) =>
      api.post("/risk/nearby", {
        body,
        query: { record: false },
        schema: alertEvaluationSchema,
      }),
  });
}
