import { QueryClientProvider } from "@tanstack/react-query";
import { useMemo } from "react";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { AppErrorBoundary } from "@/app/ErrorBoundary";
import { ThemeProvider } from "@/app/ThemeProvider";
import { createQueryClient } from "@/app/queryClient";
import { routes } from "@/app/routes";

export function App() {
  // Created once per mount rather than at module scope, so tests get a clean
  // cache per render and hot reload does not resurrect stale data.
  const queryClient = useMemo(() => createQueryClient(), []);
  const router = useMemo(() => createBrowserRouter(routes), []);

  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}

export default App;
