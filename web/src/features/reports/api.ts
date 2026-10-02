/** Report generation, history and export. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { getAuthToken } from "@/features/auth/token-holder";
import { api } from "@/lib/api-client";
import { API_ROOT } from "@/lib/env";

export const REPORT_TYPES = ["DAILY", "WEEKLY", "ROAD_SAFETY", "VIOLATION", "HOTSPOT"] as const;
export type ReportType = (typeof REPORT_TYPES)[number];

const reportTypeInfo = z.object({
  type: z.enum(REPORT_TYPES),
  label: z.string(),
  description: z.string(),
  default_window_hours: z.number(),
});
export type ReportTypeInfo = z.infer<typeof reportTypeInfo>;

const reportColumn = z.object({
  key: z.string(),
  label: z.string(),
  numeric: z.boolean(),
});
export type ReportColumn = z.infer<typeof reportColumn>;

const reportSection = z.object({
  title: z.string(),
  note: z.string().nullable().optional(),
  columns: z.array(reportColumn),
  rows: z.array(z.record(z.string(), z.unknown())),
  available: z.boolean(),
  unavailable_reason: z.string().nullable().optional(),
});
export type ReportSection = z.infer<typeof reportSection>;

export const reportSchema = z.object({
  id: z.string(),
  type: z.enum(REPORT_TYPES),
  title: z.string(),
  subtitle: z.string(),
  generated_at: z.string(),
  generated_by: z.string(),
  window_hours: z.number(),
  window_label: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  parameters: z.record(z.string(), z.unknown()),
  record_count: z.number(),
  demo_record_count: z.number(),
  sections: z.array(reportSection),
});
export type Report = z.infer<typeof reportSchema>;

export function useReportTypes() {
  return useQuery({
    queryKey: ["reports", "types"],
    queryFn: ({ signal }) =>
      api.get("/reports/types", { schema: z.array(reportTypeInfo), signal }),
    // The catalogue is a property of the build, not of the data.
    staleTime: Infinity,
  });
}

export function useReports() {
  return useQuery({
    queryKey: ["reports", "list"],
    queryFn: ({ signal }) =>
      api.get("/reports", { query: { limit: 30 }, schema: z.array(reportSchema), signal }),
  });
}

export function useGenerateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { type: ReportType; window_hours: number }) =>
      api.post("/reports", { body, schema: reportSchema }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reports", "list"] });
    },
  });
}

/**
 * Download a report as CSV or JSON.
 *
 * Fetched with the bearer token rather than linked to directly: the export
 * endpoint is authenticated, and a plain anchor navigation would not send the
 * header. The blob is handed to a temporary anchor so the browser's own save
 * dialog handles the file, and the object URL is revoked afterwards — an
 * unreleased blob holds the whole export in memory for the life of the tab.
 */
export async function downloadReport(reportId: string, format: "csv" | "json"): Promise<void> {
  const token = getAuthToken();
  const response = await fetch(`${API_ROOT}/reports/${reportId}/export?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`Export failed with status ${response.status}.`);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] ?? `trajyx-report.${format}`;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
