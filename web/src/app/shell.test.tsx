/**
 * Shell render test.
 *
 * Verifies the dashboard actually mounts, that the navigation reflects the
 * signed-in role, and that the four data states are driven by the API rather
 * than hardcoded. The fetch layer is stubbed at the network boundary so this
 * exercises the real query client, the real schema validation and the real
 * components.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/app/ThemeProvider";
import { createQueryClient } from "@/app/queryClient";
import { routes } from "@/app/routes";

const HEALTH_PAYLOAD = {
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={createQueryClient({ retry: false })}>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dashboard shell", () => {
  it("renders the navigation groups for a staff role", async () => {
    fetchMock.mockResolvedValue(jsonResponse(HEALTH_PAYLOAD));
    renderAt("/overview");

    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(nav).toBeInTheDocument();

    for (const group of ["Operations", "Intelligence", "Administration"]) {
      expect(screen.getByRole("heading", { name: group })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Risk Map" })).toBeInTheDocument();
  });

  it("shows live platform state from the API, not hardcoded values", async () => {
    fetchMock.mockResolvedValue(jsonResponse(HEALTH_PAYLOAD));
    renderAt("/overview");

    await waitFor(() => {
      expect(screen.getByText("TRAJYX API")).toBeInTheDocument();
    });
    // The contract version rendered must be the one the API reported.
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
    expect(screen.getByText(/Data backend is LOCAL/)).toBeInTheDocument();
  });

  it("surfaces demo mode in the chrome so synthetic data is never mistaken for real", async () => {
    fetchMock.mockResolvedValue(jsonResponse(HEALTH_PAYLOAD));
    renderAt("/overview");

    // The chip lives in the top bar; the Overview panel also has a "Demo mode"
    // field, so scope the query to the header to assert the right one.
    const header = screen.getByRole("banner", { name: "Page header" });
    await waitFor(() => {
      expect(within(header).getByText("Demo mode")).toBeInTheDocument();
    });
    expect(within(header).getByText("Local store")).toBeInTheDocument();
  });

  it("renders an actionable error state when the API is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderAt("/overview");

    expect(await screen.findByText("Cannot reach the TRAJYX API")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry|try again/i })).toBeInTheDocument();
  });

  it("renders the API error envelope's code and message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "FORBIDDEN", message: "Role is not permitted." } }, 403),
    );
    renderAt("/overview");

    expect(await screen.findByText("FORBIDDEN")).toBeInTheDocument();
    expect(screen.getByText("Role is not permitted.")).toBeInTheDocument();
  });

  it("states plainly that an unimplemented section is not built yet", async () => {
    fetchMock.mockResolvedValue(jsonResponse(HEALTH_PAYLOAD));
    renderAt("/risk-map");

    expect(
      await screen.findByText(/This section is not implemented yet/i),
    ).toBeInTheDocument();
    // Honesty check: a placeholder must not fabricate metrics.
    expect(
      screen.getByText(/does not display numbers it has not actually computed/i),
    ).toBeInTheDocument();
  });

  it("redirects the index route to overview", async () => {
    fetchMock.mockResolvedValue(jsonResponse(HEALTH_PAYLOAD));
    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("renders a not-found page for an unknown route", async () => {
    fetchMock.mockResolvedValue(jsonResponse(HEALTH_PAYLOAD));
    renderAt("/no-such-page");

    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});
