/** Aggregate analytics query. */

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/lib/api-client";

const metric = z.object({
  value: z.number().nullable(),
  available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  unit: z.string().nullable().optional(),
});

const bucket = z.object({
  key: z.string(),
  label: z.string(),
  events: z.number(),
  near_misses: z.number(),
  violations: z.number(),
  /** Null when no event in the bucket carried a score. Never coerced to 0. */
  mean_risk: z.number().nullable().optional(),
  scored_events: z.number(),
});
export type Bucket = z.infer<typeof bucket>;

const slice = z.object({
  key: z.string(),
  label: z.string(),
  count: z.number(),
  share: z.number(),
});

const breakdown = z.object({
  slices: z.array(slice),
  total: z.number(),
  available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
});
export type Breakdown = z.infer<typeof breakdown>;

const coverageRow = z.object({
  check: z.string(),
  label: z.string(),
  analyses_supported: z.number(),
  analyses_total: z.number(),
  reasons: z.array(z.string()),
});
export type CoverageRow = z.infer<typeof coverageRow>;

const segmentRow = z.object({
  id: z.string(),
  name: z.string(),
  road_name: z.string().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  risk_level: z.string().nullable().optional(),
  events: z.number(),
  near_misses: z.number(),
  violations: z.number(),
  peak_hour: z.number().nullable().optional(),
});
export type SegmentRow = z.infer<typeof segmentRow>;

export const analyticsSchema = z.object({
  generated_at: z.string(),
  window_hours: z.number(),
  window_label: z.string(),
  demo_mode: z.boolean(),
  totals: z.object({
    events: z.number(),
    violations: z.number(),
    behaviour: z.number(),
    interactions: z.number(),
    reports: z.number(),
    near_misses: z.number(),
    critical: z.number(),
    scored_events: z.number(),
    mean_risk: metric,
    demo_events: z.number(),
  }),
  by_hour: z.array(bucket),
  by_weekday: z.array(bucket),
  by_day: z.array(bucket),
  by_event_type: breakdown,
  by_category: breakdown,
  by_severity: breakdown,
  by_origin: breakdown,
  traffic_composition: breakdown,
  peak_hour: metric,
  peak_hour_events: metric,
  helmet_violations: metric,
  helmet_compliance_rate: metric,
  mean_inference_ms: metric,
  detector_coverage: z.array(coverageRow),
  top_segments: z.array(segmentRow),
});
export type Analytics = z.infer<typeof analyticsSchema>;

export function useAnalytics(windowHours: number) {
  return useQuery({
    queryKey: ["analytics", "summary", windowHours],
    queryFn: ({ signal }) =>
      api.get("/analytics/summary", {
        query: { window_hours: windowHours },
        schema: analyticsSchema,
        signal,
      }),
  });
}
