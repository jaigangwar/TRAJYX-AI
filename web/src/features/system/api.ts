/**
 * System health queries.
 *
 * The dashboard surfaces the backend's resolved capability set so an operator
 * always knows whether they are looking at Firebase-backed data or the local
 * development store. Hiding that distinction is how demo output gets mistaken
 * for real measurement.
 */

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/lib/api-client";

export const capabilitiesSchema = z.object({
  data_backend: z.string(),
  auth_backend: z.string(),
  storage_backend: z.string(),
  demo_mode: z.boolean(),
});

export const healthSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
  version: z.string(),
  environment: z.string(),
  contract_version: z.string(),
  capabilities: capabilitiesSchema,
  warnings: z.array(z.string()),
});

export type Health = z.infer<typeof healthSchema>;

export const systemKeys = {
  health: ["system", "health"] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: systemKeys.health,
    queryFn: ({ signal }) => api.get("/health", { schema: healthSchema, signal, anonymous: true }),
    // The capability banner must not go stale while an operator watches a screen
    // for an hour, but this is cheap and needs no urgency.
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
