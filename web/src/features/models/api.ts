/** Model registry and measured performance. */

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/lib/api-client";
import { MODELHEALTH_VALUES } from "@shared/domain";

const metric = z.object({
  value: z.number().nullable(),
  available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
  unit: z.string().nullable().optional(),
});
export type Metric = z.infer<typeof metric>;

const modelVersion = z.object({
  name: z.string(),
  /** Null when the analysis record stores no version for this component. */
  version: z.string().nullable(),
  role: z.string(),
  health: z.enum(MODELHEALTH_VALUES),
  health_reason: z.string(),
  first_seen_at: z.string().nullable().optional(),
  last_seen_at: z.string().nullable().optional(),
  runs: z.number(),
  frames_processed: z.number(),
  detections: z.number(),
  latency: z.object({
    mean_ms: metric,
    median_ms: metric,
    p95_ms: metric,
    slowest_ms: metric,
    samples: z.number(),
  }),
  accuracy: z.object({
    precision: metric,
    recall: metric,
    f1: metric,
    dataset_version: z.string().nullable().optional(),
    evaluated_at: z.string().nullable().optional(),
  }),
  jobs_succeeded: z.number(),
  jobs_failed: z.number(),
  failure_rate: metric,
  registered: z.boolean(),
  notes: z.array(z.string()),
});
export type ModelVersion = z.infer<typeof modelVersion>;

export const modelHealthSchema = z.object({
  generated_at: z.string(),
  window_hours: z.number(),
  models: z.array(modelVersion),
  evaluation_available: z.boolean(),
  evaluation_note: z.string(),
});
export type ModelHealthReport = z.infer<typeof modelHealthSchema>;

export function useModelHealth(windowHours: number) {
  return useQuery({
    queryKey: ["models", "health", windowHours],
    queryFn: ({ signal }) =>
      api.get("/models/health", {
        query: { window_hours: windowHours },
        schema: modelHealthSchema,
        signal,
      }),
  });
}
