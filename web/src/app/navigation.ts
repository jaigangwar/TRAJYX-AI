/**
 * The dashboard's information architecture, declared once.
 *
 * The sidebar, the router and the role checks all read this list, so a section
 * cannot exist in the menu without a route or be reachable by a role that is
 * not allowed to see it.
 */

import type { Role } from "@shared/domain";

export type IconName =
  | "overview"
  | "monitor"
  | "video"
  | "map"
  | "violation"
  | "nearmiss"
  | "incident"
  | "camera"
  | "analytics"
  | "report"
  | "model"
  | "settings";

export interface NavItem {
  /** Route path, relative to the dashboard root. */
  path: string;
  label: string;
  icon: IconName;
  /** Roles permitted to see and open this section. */
  roles: readonly Role[];
  /** Grouping heading in the sidebar. */
  group: NavGroup;
  /** Phase that delivers the section's functionality, for honest placeholders. */
  deliveredInPhase: number;
}

export type NavGroup = "Operations" | "Intelligence" | "Administration";

export const NAV_GROUPS: readonly NavGroup[] = ["Operations", "Intelligence", "Administration"];

const ALL_STAFF: readonly Role[] = ["ADMIN", "TRAFFIC_OPERATOR", "ANALYST"];
const OPERATIONS: readonly Role[] = ["ADMIN", "TRAFFIC_OPERATOR"];
const ANALYSIS: readonly Role[] = ["ADMIN", "ANALYST"];

export const NAV_ITEMS: readonly NavItem[] = [
  {
    path: "/overview",
    label: "Overview",
    icon: "overview",
    roles: ALL_STAFF,
    group: "Operations",
    deliveredInPhase: 2,
  },
  {
    path: "/monitoring",
    label: "Live Monitoring",
    icon: "monitor",
    roles: OPERATIONS,
    group: "Operations",
    deliveredInPhase: 2,
  },
  {
    path: "/analysis",
    label: "Video Analysis",
    icon: "video",
    roles: OPERATIONS,
    group: "Operations",
    deliveredInPhase: 3,
  },
  {
    path: "/cameras",
    label: "Cameras",
    icon: "camera",
    roles: ALL_STAFF,
    group: "Operations",
    deliveredInPhase: 2,
  },
  {
    path: "/risk-map",
    label: "Risk Map",
    icon: "map",
    roles: ALL_STAFF,
    group: "Intelligence",
    deliveredInPhase: 10,
  },
  {
    path: "/violations",
    label: "Violations",
    icon: "violation",
    roles: ALL_STAFF,
    group: "Intelligence",
    deliveredInPhase: 6,
  },
  {
    path: "/near-misses",
    label: "Near Misses",
    icon: "nearmiss",
    roles: ALL_STAFF,
    group: "Intelligence",
    deliveredInPhase: 8,
  },
  {
    path: "/incidents",
    label: "Incidents",
    icon: "incident",
    roles: ALL_STAFF,
    group: "Intelligence",
    deliveredInPhase: 15,
  },
  {
    path: "/analytics",
    label: "Analytics",
    icon: "analytics",
    roles: ANALYSIS,
    group: "Intelligence",
    deliveredInPhase: 11,
  },
  {
    path: "/reports",
    label: "Reports",
    icon: "report",
    roles: ANALYSIS,
    group: "Administration",
    deliveredInPhase: 16,
  },
  {
    path: "/model-health",
    label: "Model Health",
    icon: "model",
    roles: ANALYSIS,
    group: "Administration",
    deliveredInPhase: 9,
  },
  {
    path: "/settings",
    label: "Settings",
    icon: "settings",
    roles: ["ADMIN"],
    group: "Administration",
    deliveredInPhase: 2,
  },
];

/** Sections a role may open, preserving declaration order. */
export function navItemsForRole(role: Role | null): readonly NavItem[] {
  if (!role) return [];
  return NAV_ITEMS.filter((item) => item.roles.includes(role));
}

/** Grouped for sidebar rendering; groups with no visible item are dropped. */
export function groupedNavForRole(role: Role | null): { group: NavGroup; items: readonly NavItem[] }[] {
  const visible = navItemsForRole(role);
  return NAV_GROUPS.map((group) => ({
    group,
    items: visible.filter((item) => item.group === group),
  })).filter((entry) => entry.items.length > 0);
}

/** Landing route after sign-in. Drivers use the mobile app, not this dashboard. */
export function defaultRouteForRole(role: Role | null): string {
  if (role === "DRIVER") return "/driver-notice";
  const first = navItemsForRole(role)[0];
  return first ? first.path : "/overview";
}
