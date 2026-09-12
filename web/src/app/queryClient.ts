/** React Query configuration. */

import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api-client";

export interface QueryClientOptions {
  /**
   * Disable retries. Tests assert on the error state directly, and waiting out
   * the real backoff would make every error-path test slow and flaky.
   */
  retry?: boolean;
}

export function createQueryClient({ retry = true }: QueryClientOptions = {}): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: retry
          ? (failureCount, error) => {
              // Never retry a client error: a 403 or a contract mismatch will not
              // fix itself, and retrying a 401 fights the sign-out path.
              if (error instanceof ApiError && !error.isRetryable) return false;
              return failureCount < 2;
            }
          : false,
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
      mutations: {
        retry: false,
      },
    },
  });
}
