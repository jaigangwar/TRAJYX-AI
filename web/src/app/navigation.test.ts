import { describe, expect, it } from "vitest";

import {
  NAV_ITEMS,
  defaultRouteForRole,
  groupedNavForRole,
  navItemsForRole,
} from "@/app/navigation";
import { routes } from "@/app/routes";
import { ROLE_VALUES } from "@shared/domain";

/** Collect the dashboard child paths declared in the router, as "/path". */
function routerPaths(): string[] {
  const dashboard = routes.find((route) => route.path === "/");
  const children = dashboard?.children ?? [];
  return children
    .map((child) => child.path)
    .filter((path): path is string => typeof path === "string")
    .map((path) => `/${path}`);
}

describe("navigation and routing agree", () => {
  it("gives every navigation entry a route", () => {
    const paths = routerPaths();
    for (const item of NAV_ITEMS) {
      expect(paths, `${item.label} (${item.path}) has no route`).toContain(item.path);
    }
  });

  it("does not expose a dashboard route that is missing from the menu", () => {
    const navPaths = new Set(NAV_ITEMS.map((item) => item.path));
    for (const path of routerPaths()) {
      expect(navPaths, `${path} is routable but not in the navigation table`).toContain(path);
    }
  });

  it("uses unique paths", () => {
    const paths = NAV_ITEMS.map((item) => item.path);
    expect(new Set(paths).size).toBe(paths.length);
  });
});

describe("role-based navigation", () => {
  it("restricts settings to administrators", () => {
    for (const role of ROLE_VALUES) {
      const canSeeSettings = navItemsForRole(role).some((item) => item.path === "/settings");
      expect(canSeeSettings).toBe(role === "ADMIN");
    }
  });

  it("keeps operators out of analyst-only sections", () => {
    const operatorPaths = navItemsForRole("TRAFFIC_OPERATOR").map((item) => item.path);
    expect(operatorPaths).not.toContain("/analytics");
    expect(operatorPaths).not.toContain("/reports");
    expect(operatorPaths).not.toContain("/model-health");
  });

  it("keeps analysts out of operator-only sections", () => {
    const analystPaths = navItemsForRole("ANALYST").map((item) => item.path);
    expect(analystPaths).not.toContain("/monitoring");
    expect(analystPaths).not.toContain("/analysis");
  });

  it("gives drivers no dashboard sections", () => {
    expect(navItemsForRole("DRIVER")).toHaveLength(0);
    expect(groupedNavForRole("DRIVER")).toHaveLength(0);
  });

  it("gives administrators every section", () => {
    expect(navItemsForRole("ADMIN")).toHaveLength(NAV_ITEMS.length);
  });

  it("drops empty groups", () => {
    for (const { items } of groupedNavForRole("ANALYST")) {
      expect(items.length).toBeGreaterThan(0);
    }
  });

  it("lands each role on a section that role can open", () => {
    for (const role of ROLE_VALUES) {
      const destination = defaultRouteForRole(role);
      if (role === "DRIVER") {
        expect(destination).toBe("/driver-notice");
        continue;
      }
      const permitted = navItemsForRole(role).map((item) => item.path);
      expect(permitted).toContain(destination);
    }
  });

  it("returns nothing for an unauthenticated visitor", () => {
    expect(navItemsForRole(null)).toHaveLength(0);
  });
});
