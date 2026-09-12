/**
 * Test harness.
 *
 * Renders the real provider stack — query client, auth provider, router — with
 * only `fetch` stubbed. Tests therefore exercise the genuine session
 * restoration, schema validation and guard logic rather than a simplified
 * stand-in, which is the only way the role checks get covered at all.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { ThemeProvider } from "@/app/ThemeProvider";
import { createQueryClient } from "@/app/queryClient";
import { routes } from "@/app/routes";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { setAuthToken } from "@/features/auth/token-holder";
import type { User } from "@/features/auth/types";
import type { Role } from "@shared/domain";

export const HEALTH_PAYLOAD = {
  status: "ok",
  service: "TRAJYX API",
  version: "0.1.0",
  environment: "test",
  contract_version: "1.0.0",
  capabilities: {
    data_backend: "local",
    auth_backend: "local",
    storage_backend: "local",
    demo_mode: true,
  },
  warnings: ["Data backend is LOCAL (on-disk JSON store)."],
};

export function userFor(role: Role, overrides: Partial<User> = {}): User {
  return {
    id: `user-${role.toLowerCase()}`,
    email: `${role.toLowerCase()}@trajyx.test`,
    display_name: null,
    role,
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    last_login_at: null,
    ...overrides,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export interface RouteStub {
  /** Substring matched against the request URL. */
  match: string;
  body: unknown;
  status?: number;
}

/**
 * Build a fetch stub that answers by URL substring.
 *
 * Unmatched requests reject loudly rather than returning an empty object: a
 * silent default would let a test pass while the component under test was
 * actually calling an endpoint nobody stubbed.
 */
export function stubFetch(stubs: RouteStub[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;

    for (const stub of stubs) {
      if (url.includes(stub.match)) return jsonResponse(stub.body, stub.status ?? 200);
    }
    throw new Error(`No stub matched ${url}. Add one to the test's stub list.`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Store a session the way `AuthProvider` expects to find one on mount. */
export function seedStoredSession(user: User, token = "test-token"): void {
  window.localStorage.setItem(
    "trajyx.session",
    JSON.stringify({
      token,
      user,
      // Comfortably in the future so the expiry timer never fires mid-test.
      expiresAt: Date.now() + 60 * 60 * 1000,
    }),
  );
}

export function resetAuthState(): void {
  try {
    window.localStorage.clear();
    window.sessionStorage.clear();
  } catch {
    /* storage unavailable in this environment */
  }
  // The token holder is module-scoped, so it survives unmount and would leak
  // into the next test.
  setAuthToken(null);
}

export function renderApp(path: string): RenderResult {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={createQueryClient({ retry: false })}>
      <AuthProvider>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

/** Render as a signed-in user of the given role. */
export function renderAsRole(role: Role, path: string, extraStubs: RouteStub[] = []): RenderResult {
  const user = userFor(role);
  seedStoredSession(user);
  stubFetch([
    { match: "/auth/me", body: user },
    { match: "/health", body: HEALTH_PAYLOAD },
    ...extraStubs,
  ]);
  return renderApp(path);
}
