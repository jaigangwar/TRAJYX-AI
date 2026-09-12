/**
 * Session and guard behaviour.
 *
 * These assert what the dashboard *renders*. The API enforces the same role
 * boundaries independently (see tests/backend/test_authorization.py) — a guard
 * that is wrong here shows a user a screen they cannot use, but it does not
 * grant access.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
import { ROLE_VALUES, type Role } from "@shared/domain";

beforeEach(() => {
  resetAuthState();
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetAuthState();
});

describe("unauthenticated access", () => {
  it("redirects a protected route to the login page", async () => {
    stubFetch([{ match: "/health", body: HEALTH_PAYLOAD }]);
    renderApp("/overview");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows the product identity and the deployment auth backend", async () => {
    stubFetch([{ match: "/health", body: HEALTH_PAYLOAD }]);
    renderApp("/login");

    expect(await screen.findByRole("heading", { name: "TRAJYX", level: 1 })).toBeInTheDocument();
    // The operator must be able to see they are on local development auth.
    expect(await screen.findByText("Local auth")).toBeInTheDocument();
    expect(screen.getByText(/seed_admin\.py/)).toBeInTheDocument();
  });

  it("discards a stored session the API rejects", async () => {
    seedStoredSession(userFor("ADMIN"));
    stubFetch([
      { match: "/auth/me", body: { error: { code: "UNAUTHENTICATED", message: "Expired." } }, status: 401 },
      { match: "/health", body: HEALTH_PAYLOAD },
    ]);
    renderApp("/overview");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(window.localStorage.getItem("trajyx.session")).toBeNull();
  });

  it("fails closed when the session cannot be verified", async () => {
    // A dashboard whose permissions could not be confirmed must not render.
    seedStoredSession(userFor("ADMIN"));
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    renderApp("/overview");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("ignores a corrupt stored session without crashing", async () => {
    window.localStorage.setItem("trajyx.session", "{not json");
    stubFetch([{ match: "/health", body: HEALTH_PAYLOAD }]);
    renderApp("/overview");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("discards a stored session whose token has already expired", async () => {
    window.localStorage.setItem(
      "trajyx.session",
      JSON.stringify({ token: "old", user: userFor("ADMIN"), expiresAt: Date.now() - 1000 }),
    );
    stubFetch([{ match: "/health", body: HEALTH_PAYLOAD }]);
    renderApp("/overview");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("sign-in", () => {
  it("signs in and lands on the overview", async () => {
    const user = userFor("ADMIN");
    stubFetch([
      { match: "/auth/login", body: { access_token: "t", token_type: "bearer", expires_in: 3600, user } },
      { match: "/auth/me", body: user },
      { match: "/health", body: HEALTH_PAYLOAD },
    ]);
    renderApp("/login");

    await screen.findByRole("heading", { name: "Sign in" });
    await userEvent.type(screen.getByLabelText("Email address"), user.email);
    await userEvent.type(screen.getByLabelText("Password"), "Bootstrap-Admin-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("reports the API error message on a failed attempt", async () => {
    stubFetch([
      {
        match: "/auth/login",
        body: { error: { code: "UNAUTHENTICATED", message: "Incorrect email address or password." } },
        status: 401,
      },
      { match: "/health", body: HEALTH_PAYLOAD },
    ]);
    renderApp("/login");

    await screen.findByRole("heading", { name: "Sign in" });
    await userEvent.type(screen.getByLabelText("Email address"), "admin@trajyx.test");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Incorrect email address or password.");
    // Still on the login form, not a half-rendered dashboard.
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("keeps the sign-in button disabled until both fields are filled", async () => {
    stubFetch([{ match: "/health", body: HEALTH_PAYLOAD }]);
    renderApp("/login");

    await screen.findByRole("heading", { name: "Sign in" });
    const submit = screen.getByRole("button", { name: "Sign in" });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Email address"), "admin@trajyx.test");
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Password"), "Bootstrap-Admin-1");
    expect(submit).toBeEnabled();
  });
});

describe("role-based rendering", () => {
  it("shows an administrator every section", async () => {
    renderAsRole("ADMIN", "/overview");

    await screen.findByRole("navigation", { name: "Main navigation" });
    for (const label of ["Overview", "Live Monitoring", "Analytics", "Settings"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("hides administration from a traffic operator", async () => {
    renderAsRole("TRAFFIC_OPERATOR", "/overview");

    await screen.findByRole("navigation", { name: "Main navigation" });
    expect(screen.getByRole("link", { name: "Live Monitoring" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
  });

  it("hides live monitoring from an analyst", async () => {
    renderAsRole("ANALYST", "/overview");

    await screen.findByRole("navigation", { name: "Main navigation" });
    expect(screen.getByRole("link", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Live Monitoring" })).not.toBeInTheDocument();
  });

  it("redirects a deep link the role cannot open", async () => {
    // An operator following a link to an analyst-only section lands on their
    // own default section rather than an error page.
    renderAsRole("TRAFFIC_OPERATOR", "/analytics");

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("redirects a non-admin deep link to settings", async () => {
    renderAsRole("ANALYST", "/settings");

    await waitFor(() => {
      expect(screen.queryByText(/Deployment configuration/)).not.toBeInTheDocument();
    });
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("sends a driver to an explanation rather than into the console", async () => {
    renderAsRole("DRIVER", "/overview");

    expect(
      await screen.findByRole("heading", { name: "This console is for operators" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main navigation" })).not.toBeInTheDocument();
  });

  it("gives every role a landing section it can actually open", async () => {
    // Guards against a role whose default route redirects to itself forever.
    for (const role of ROLE_VALUES) {
      resetAuthState();
      vi.unstubAllGlobals();

      const { unmount } = renderAsRole(role as Role, "/");
      if (role === "DRIVER") {
        expect(
          await screen.findByRole("heading", { name: "This console is for operators" }),
        ).toBeInTheDocument();
      } else {
        expect(await screen.findByRole("navigation", { name: "Main navigation" })).toBeInTheDocument();
      }
      unmount();
    }
  });
});

describe("profile menu", () => {
  it("shows the signed-in identity and role", async () => {
    renderAsRole("TRAFFIC_OPERATOR", "/overview");

    const trigger = await screen.findByRole("button", { name: /account menu/i });
    await userEvent.click(trigger);

    expect(screen.getByText("traffic_operator@trajyx.test")).toBeInTheDocument();
    expect(screen.getByText("Traffic operator")).toBeInTheDocument();
  });

  it("signs out and returns to the login page", async () => {
    renderAsRole("ADMIN", "/overview", [{ match: "/auth/logout", body: { ok: true } }]);

    await userEvent.click(await screen.findByRole("button", { name: /account menu/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(window.localStorage.getItem("trajyx.session")).toBeNull();
  });

  it("closes on Escape", async () => {
    renderAsRole("ADMIN", "/overview");

    await userEvent.click(await screen.findByRole("button", { name: /account menu/i }));
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
