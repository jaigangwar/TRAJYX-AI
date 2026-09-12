import { QueryClientProvider } from "@tanstack/react-query";
import { useMemo } from "react";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import { AppErrorBoundary } from "@/app/ErrorBoundary";
import { ThemeProvider } from "@/app/ThemeProvider";
import { createQueryClient } from "@/app/queryClient";
import { routes } from "@/app/routes";
import { AuthProvider } from "@/features/auth/AuthProvider";

export function App() {
  // Created once per mount rather than at module scope, so tests get a clean
  // cache per render and hot reload does not resurrect stale data.
  const queryClient = useMemo(() => createQueryClient(), []);
  const router = useMemo(() => createBrowserRouter(routes), []);

  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        {/* AuthProvider sits inside QueryClientProvider because sign-out needs
            to clear cached queries, and outside RouterProvider because the
            route guards read the session. */}
        <AuthProvider>
          <ThemeProvider>
            <RouterProvider router={router} />
          </ThemeProvider>
        </AuthProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}

export default App;
