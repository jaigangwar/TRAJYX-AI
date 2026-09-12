/**
 * Shell render test.
 *
 * Verifies the dashboard mounts for a signed-in user, that live API values
 * reach the screen, and that the four data states are driven by the API rather
 * than hardcoded. Only `fetch` is stubbed, so this exercises the real query
 * client, schema validation and components.
 */

import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  HEALTH_PAYLOAD,
  renderApp,
  renderAsRole,
  resetAuthState,
  seedStoredSession,
  stubFetch,
  userFor,
} from "@/test/harness";

beforeEach(() => {
  resetAuthState();
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetAuthState();
});

describe("dashboard shell", () => {
  it("renders the navigation groups for a staff role", async () => {
    renderAsRole("ADMIN", "/overview");

    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(nav).toBeInTheDocument();

    for (const group of ["Operations", "Intelligence", "Administration"]) {
      expect(screen.getByRole("heading", { name: group })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Risk Map" })).toBeInTheDocument();
  });

  it("shows counted KPIs from the API, not hardcoded values", async () => {
    renderAsRole("ADMIN", "/overview");

    await waitFor(() => {
      // cameras.online = 1 from the stubbed summary
      expect(screen.getByText("Cameras online")).toBeInTheDocument();
    });
    expect(screen.getByText("2 registered")).toBeInTheDocument();
    // "Violations" is also a sidebar link, so scope to the KPI panel.
    expect(screen.getByRole("main")).toHaveTextContent("Violations");
  });

  it("shows a dash rather than a zero for a metric it cannot compute", async () => {
    // "no analysis has run" and "zero vehicles detected" are different facts.
    renderAsRole("ADMIN", "/overview");

    await screen.findByText("Vehicles detected");
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("discloses how much of the total is synthetic demo data", async () => {
    renderAsRole("ADMIN", "/overview");

    expect(
      await screen.findByText(/1 of 3 events in this window are synthetic demo records/),
    ).toBeInTheDocument();
  });

  it("surfaces demo mode in the chrome so synthetic data is never mistaken for real", async () => {
    renderAsRole("ADMIN", "/overview");

    const header = await screen.findByRole("banner", { name: "Page header" });
    await waitFor(() => {
      expect(within(header).getByText("Demo mode")).toBeInTheDocument();
    });
    expect(within(header).getByText("Local store")).toBeInTheDocument();
  });

  it("renders an actionable error state when the API is unreachable", async () => {
    const user = userFor("ADMIN");
    seedStoredSession(user);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/auth/me")) {
          return new Response(JSON.stringify(user), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        throw new TypeError("Failed to fetch");
      }),
    );

    renderApp("/overview");

    expect(await screen.findByText("Cannot reach the TRAJYX API")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /retry|try again/i }).length).toBeGreaterThan(0);
  });

  it("renders the API error envelope's code and message", async () => {
    const user = userFor("ADMIN");
    seedStoredSession(user);
    stubFetch([
      { match: "/auth/me", body: user },
      { match: "/health", body: HEALTH_PAYLOAD },
      {
        match: "/dashboard/summary",
        body: { error: { code: "DEPENDENCY_UNAVAILABLE", message: "Firestore is unavailable." } },
        status: 503,
      },
    ]);

    renderApp("/overview");

    // Both the KPI panel and the recent-events panel surface the failure.
    expect((await screen.findAllByText("DEPENDENCY_UNAVAILABLE")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Firestore is unavailable.").length).toBeGreaterThan(0);
  });

  it("states plainly that an unimplemented section is not built yet", async () => {
    renderAsRole("ADMIN", "/risk-map");

    expect(
      await screen.findByText(/This section is not implemented yet/i),
    ).toBeInTheDocument();
    // Honesty check: a placeholder must not fabricate metrics.
    expect(
      screen.getByText(/does not display numbers it has not actually computed/i),
    ).toBeInTheDocument();
  });

  it("redirects the index route to overview", async () => {
    renderAsRole("ADMIN", "/");

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("renders a not-found page for an unknown route", async () => {
    stubFetch([{ match: "/health", body: HEALTH_PAYLOAD }]);
    renderApp("/no-such-page");

    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});
