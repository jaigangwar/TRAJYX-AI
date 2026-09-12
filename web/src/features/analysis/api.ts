/** Video job and analysis queries. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { API_ROOT } from "@/lib/env";
import { api } from "@/lib/api-client";
import { DATAORIGIN_VALUES, JOBSTATUS_VALUES, RISKLEVEL_VALUES } from "@shared/domain";

const progress = z.object({
  stage: z.string(),
  percent: z.number(),
  frames_processed: z.number(),
  frames_total: z.number(),
  detections: z.number(),
  active_tracks: z.number(),
});

export const jobSchema = z.object({
  id: z.string(),
  status: z.enum(JOBSTATUS_VALUES),
  filename: z.string(),
  size_bytes: z.number(),
  content_type: z.string(),
  camera_id: z.string().nullable().optional(),
  camera_name: z.string().nullable().optional(),
  storage_key: z.string(),
  annotated_key: z.string().nullable().optional(),
  progress: progress.nullable().optional(),
  error: z.string().nullable().optional(),
  frame_stride: z.number().nullable().optional(),
  origin: z.enum(DATAORIGIN_VALUES),
  created_at: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  analysis_id: z.string().nullable().optional(),
});
export type VideoJob = z.infer<typeof jobSchema>;

export const trackSchema = z.object({
  track_id: z.number(),
  vehicle_class: z.string(),
  first_frame: z.number(),
  last_frame: z.number(),
  duration_s: z.number(),
  point_count: z.number(),
  mean_speed_kmh: z.number().nullable().optional(),
  heading_deg: z.number().nullable().optional(),
  path: z.array(z.array(z.number())),
});
export type AnalysisTrack = z.infer<typeof trackSchema>;

export const timelineSchema = z.object({
  timestamp_s: z.number(),
  frame_index: z.number(),
  event_type: z.string(),
  severity: z.string(),
  track_ids: z.array(z.number()),
  confidence: z.number().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  label: z.string(),
});
export type TimelineEntry = z.infer<typeof timelineSchema>;

export const analysisSchema = z.object({
  id: z.string(),
  job_id: z.string(),
  camera_id: z.string().nullable().optional(),
  frame_width: z.number(),
  frame_height: z.number(),
  frame_rate: z.number(),
  frame_count: z.number(),
  duration_s: z.number(),
  frames_analysed: z.number(),
  frame_stride: z.number(),
  detector_name: z.string(),
  detector_version: z.string(),
  tracker_name: z.string(),
  inference_ms_per_frame: z.number().nullable().optional(),
  wall_seconds: z.number(),
  detection_count: z.number(),
  vehicle_count: z.number(),
  pedestrian_count: z.number(),
  class_counts: z.record(z.string(), z.number()),
  unmapped_labels: z.record(z.string(), z.number()),
  track_count: z.number(),
  tracks: z.array(trackSchema),
  violation_count: z.number(),
  behaviour_count: z.number(),
  near_miss_count: z.number(),
  minimum_ttc_s: z.number().nullable().optional(),
  mean_interaction_score: z.number().nullable().optional(),
  risk_score: z.number().nullable().optional(),
  risk_level: z.enum(RISKLEVEL_VALUES).nullable().optional(),
  risk_confidence: z.number().nullable().optional(),
  risk_factors: z.array(
    z.object({
      name: z.string(),
      value: z.number(),
      weight: z.number(),
      contribution: z.number(),
      detail: z.string().nullable().optional(),
    }),
  ),
  top_risk_factors: z.array(z.string()),
  timeline: z.array(timelineSchema),
  unavailable_checks: z.array(z.object({ name: z.string(), reason: z.string() })),
  origin: z.enum(DATAORIGIN_VALUES),
  annotated_key: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
});
export type VideoAnalysis = z.infer<typeof analysisSchema>;

const jobsPage = z.object({
  items: z.array(jobSchema),
  next_cursor: z.string().nullable().optional(),
});

/** Jobs list. Polls while anything is running. */
export function useJobs() {
  return useQuery({
    queryKey: ["videos", "jobs"],
    queryFn: ({ signal }) => api.get("/videos", { query: { limit: 50 }, schema: jobsPage, signal }),
    refetchInterval: (query) => {
      const running = query.state.data?.items.some(
        (job) => job.status === "QUEUED" || job.status === "PROCESSING",
      );
      return running ? 2000 : false;
    },
  });
}

/** One job. Polls while it is running, stops when it settles. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["videos", "job", jobId],
    queryFn: ({ signal }) => api.get(`/videos/${jobId}`, { schema: jobSchema, signal }),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "QUEUED" || status === "PROCESSING" ? 1500 : false;
    },
  });
}

export function useAnalysis(jobId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["videos", "analysis", jobId],
    queryFn: ({ signal }) => api.get(`/videos/${jobId}/analysis`, { schema: analysisSchema, signal }),
    enabled: Boolean(jobId) && enabled,
  });
}

export function useUploadVideo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, cameraId }: { file: File; cameraId?: string }) => {
      const formData = new FormData();
      formData.append("file", file);
      if (cameraId) formData.append("camera_id", cameraId);
      return api.post("/videos/upload", { formData, schema: jobSchema });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["videos"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export interface AnalyseOptions {
  frame_stride?: number;
  max_frames?: number;
  speed_limit_kmh?: number;
  simulate?: boolean;
}

export function useAnalyseVideo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, options }: { jobId: string; options: AnalyseOptions }) =>
      api.post(`/videos/${jobId}/analyze`, { body: options, schema: jobSchema }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["videos"] }),
  });
}

export function useDeleteJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.delete(`/videos/${jobId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["videos"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

/**
 * URL for the annotated or source video.
 *
 * Footage is served through the authenticated API rather than a public link:
 * it is the most sensitive data in the system, and a public URL cannot be
 * revoked. The `<video>` element cannot set an Authorization header, so the
 * caller fetches this and hands the element a blob URL.
 */
export function mediaUrl(jobId: string, variant: "annotated" | "source" = "annotated"): string {
  return `${API_ROOT}/videos/${jobId}/media?variant=${variant}`;
}
