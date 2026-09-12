/** Display formatting shared across pages. */

import type { CameraStatus, EventType, Severity } from "@shared/domain";

export const EVENT_LABELS: Record<EventType, string> = {
  HELMET_VIOLATION: "Helmet violation",
  SEATBELT_VIOLATION: "Seatbelt violation",
  TRIPLE_RIDING: "Triple riding",
  WRONG_WAY: "Wrong way",
  RED_LIGHT_VIOLATION: "Red-light violation",
  STOP_LINE_VIOLATION: "Stop-line violation",
  DANGEROUS_LANE_CHANGE: "Dangerous lane change",
  OVERSPEED: "Overspeed",
  HARD_BRAKING: "Hard braking",
  SUDDEN_ACCELERATION: "Sudden acceleration",
  DISTRACTED_RIDING: "Distracted riding",
  PEDESTRIAN_CONFLICT: "Pedestrian conflict",
  NEAR_MISS: "Near miss",
  COLLISION_RISK: "Collision risk",
  HAZARD_REPORT: "Hazard report",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  INFO: "Info",
  MINOR: "Minor",
  MAJOR: "Major",
  CRITICAL: "Critical",
};

export const CAMERA_STATUS_LABELS: Record<CameraStatus, string> = {
  ONLINE: "Online",
  OFFLINE: "Offline",
  PROCESSING: "Processing",
  ALERT: "Alert",
};

/** Compact relative time: "12s", "4m", "3h", "2d". */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";

  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

/** Absolute timestamp for tables: "12 Sep 14:32". */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Confidence as a percentage, or a dash when the producer reported none. */
export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatCoordinate(latitude: number, longitude: number): string {
  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}

/** Compass heading to a cardinal label. */
export function formatHeading(degrees: number): string {
  const points = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  const index = Math.round(((degrees % 360) / 45)) % 8;
  return `${Math.round(degrees)}° ${points[index]}`;
}
