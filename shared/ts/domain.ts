/**
 * TRAJYX generated file - DO NOT EDIT BY HAND.
 * Source: shared/contracts/domain.json
 * Regenerate: python scripts/gen_contracts.py
 */

export const CONTRACT_VERSION = "1.0.0";

/** Authorization roles. Ordered from most to least privileged. */
export const ROLE_VALUES = [
  "ADMIN",
  "TRAFFIC_OPERATOR",
  "ANALYST",
  "DRIVER",
] as const;
export type Role = (typeof ROLE_VALUES)[number];

/** Coarse risk band derived from a 0-100 risk score. */
export const RISKLEVEL_VALUES = [
  "LOW",
  "MODERATE",
  "HIGH",
  "CRITICAL",
] as const;
export type RiskLevel = (typeof RISKLEVEL_VALUES)[number];

/** Event severity, independent of the numeric risk score. */
export const SEVERITY_VALUES = [
  "INFO",
  "MINOR",
  "MAJOR",
  "CRITICAL",
] as const;
export type Severity = (typeof SEVERITY_VALUES)[number];

/** Canonical event taxonomy emitted by the safety, interaction and risk engines. */
export const EVENTTYPE_VALUES = [
  "HELMET_VIOLATION",
  "SEATBELT_VIOLATION",
  "TRIPLE_RIDING",
  "WRONG_WAY",
  "RED_LIGHT_VIOLATION",
  "STOP_LINE_VIOLATION",
  "DANGEROUS_LANE_CHANGE",
  "OVERSPEED",
  "HARD_BRAKING",
  "SUDDEN_ACCELERATION",
  "DISTRACTED_RIDING",
  "PEDESTRIAN_CONFLICT",
  "NEAR_MISS",
  "COLLISION_RISK",
  "HAZARD_REPORT",
] as const;
export type EventType = (typeof EVENTTYPE_VALUES)[number];

/** Grouping used by dashboard navigation and reporting. */
export const EVENTCATEGORY_VALUES = [
  "VIOLATION",
  "BEHAVIOR",
  "INTERACTION",
  "REPORT",
] as const;
export type EventCategory = (typeof EVENTCATEGORY_VALUES)[number];

/** Detector output classes. Extend by adding here and retraining/remapping the detector. */
export const VEHICLECLASS_VALUES = [
  "CAR",
  "MOTORCYCLE",
  "SCOOTER",
  "BUS",
  "TRUCK",
  "AUTO_RICKSHAW",
  "VAN",
  "BICYCLE",
  "PEDESTRIAN",
] as const;
export type VehicleClass = (typeof VEHICLECLASS_VALUES)[number];

/** Operational state of a camera as shown in Live Monitoring. */
export const CAMERASTATUS_VALUES = [
  "ONLINE",
  "OFFLINE",
  "PROCESSING",
  "ALERT",
] as const;
export type CameraStatus = (typeof CAMERASTATUS_VALUES)[number];

/** Lifecycle of an asynchronous video analysis job. */
export const JOBSTATUS_VALUES = [
  "QUEUED",
  "PROCESSING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
] as const;
export type JobStatus = (typeof JOBSTATUS_VALUES)[number];

/** Band for an ESTIMATED time-to-collision value. Always presented as an estimate. */
export const TTCBAND_VALUES = [
  "LOW",
  "MEDIUM",
  "HIGH",
  "CRITICAL",
] as const;
export type TtcBand = (typeof TTCBAND_VALUES)[number];

/** Tri-state result for any visual check. UNABLE_TO_DETERMINE is a first-class outcome and must never be collapsed into a negative. */
export const DETERMINATION_VALUES = [
  "DETECTED",
  "NOT_DETECTED",
  "UNABLE_TO_DETERMINE",
] as const;
export type Determination = (typeof DETERMINATION_VALUES)[number];

/** Driver alert escalation tiers. */
export const ALERTLEVEL_VALUES = [
  "LEVEL_1",
  "LEVEL_2",
  "LEVEL_3",
] as const;
export type AlertLevel = (typeof ALERTLEVEL_VALUES)[number];

/** Provenance label. Every record carries one so simulated and estimated values are never displayed as measured ground truth. */
export const DATAORIGIN_VALUES = [
  "MEASURED",
  "ESTIMATED",
  "DEMO",
] as const;
export type DataOrigin = (typeof DATAORIGIN_VALUES)[number];

/** Hazard categories a driver can report from the mobile app. */
export const HAZARDTYPE_VALUES = [
  "ACCIDENT",
  "POTHOLE",
  "BROKEN_SIGNAL",
  "ROAD_BLOCKAGE",
  "WRONG_WAY_VEHICLE",
  "DANGEROUS_CROSSING",
  "POOR_VISIBILITY",
  "ROAD_DAMAGE",
  "OTHER",
] as const;
export type HazardType = (typeof HAZARDTYPE_VALUES)[number];

/** Review workflow state for driver hazard reports and flagged violations. */
export const REPORTSTATUS_VALUES = [
  "PENDING",
  "REVIEWING",
  "CONFIRMED",
  "REJECTED",
] as const;
export type ReportStatus = (typeof REPORTSTATUS_VALUES)[number];

/** Operational health of a registered model version. */
export const MODELHEALTH_VALUES = [
  "HEALTHY",
  "WARNING",
  "NEEDS_ATTENTION",
  "UNKNOWN",
] as const;
export type ModelHealth = (typeof MODELHEALTH_VALUES)[number];

/** Traffic signal phase used by the red-light violation detector. UNKNOWN suppresses red-light detection entirely. */
export const SIGNALSTATE_VALUES = [
  "RED",
  "AMBER",
  "GREEN",
  "UNKNOWN",
] as const;
export type SignalState = (typeof SIGNALSTATE_VALUES)[number];

export interface RiskBand { level: RiskLevel; min: number; max: number }
export const RISK_BANDS: readonly RiskBand[] = [
  { level: "LOW", min: 0, max: 25 },
  { level: "MODERATE", min: 26, max: 50 },
  { level: "HIGH", min: 51, max: 75 },
  { level: "CRITICAL", min: 76, max: 100 },
] as const;

export interface TtcBandSpec { band: TtcBand; minSeconds: number; maxSeconds: number | null }
export const TTC_BANDS: readonly TtcBandSpec[] = [
  { band: "LOW", minSeconds: 5.0, maxSeconds: null },
  { band: "MEDIUM", minSeconds: 2.0, maxSeconds: 5.0 },
  { band: "HIGH", minSeconds: 1.0, maxSeconds: 2.0 },
  { band: "CRITICAL", minSeconds: 0.0, maxSeconds: 1.0 },
] as const;

export const EVENT_CATEGORY: Readonly<Record<EventType, EventCategory>> = {
  HELMET_VIOLATION: "VIOLATION",
  SEATBELT_VIOLATION: "VIOLATION",
  TRIPLE_RIDING: "VIOLATION",
  WRONG_WAY: "VIOLATION",
  RED_LIGHT_VIOLATION: "VIOLATION",
  STOP_LINE_VIOLATION: "VIOLATION",
  DANGEROUS_LANE_CHANGE: "VIOLATION",
  OVERSPEED: "VIOLATION",
  HARD_BRAKING: "BEHAVIOR",
  SUDDEN_ACCELERATION: "BEHAVIOR",
  DISTRACTED_RIDING: "BEHAVIOR",
  PEDESTRIAN_CONFLICT: "INTERACTION",
  NEAR_MISS: "INTERACTION",
  COLLISION_RISK: "INTERACTION",
  HAZARD_REPORT: "REPORT",
};

export const COLLECTIONS = {
  users: "users",
  cameras: "cameras",
  videoJobs: "video_jobs",
  videoAnalysis: "video_analysis",
  detections: "detections",
  trackingEvents: "tracking_events",
  violations: "violations",
  nearMisses: "near_misses",
  riskEvents: "risk_events",
  roadSegments: "road_segments",
  riskZones: "risk_zones",
  alerts: "alerts",
  driverReports: "driver_reports",
  notifications: "notifications",
  modelVersions: "model_versions",
  analytics: "analytics",
  settings: "settings",
  trips: "trips",
} as const;

export const ALERT_DEFAULTS = {
  "level_1_min_risk": 50,
  "level_2_min_risk": 75,
  "level_3_min_risk": 90,
  "max_lateral_distance_m": 120,
  "approach_distance_m": {
    "LEVEL_1": 400,
    "LEVEL_2": 600,
    "LEVEL_3": 900
  },
  "bearing_tolerance_deg": 60,
  "cooldown_seconds": {
    "LEVEL_1": 300,
    "LEVEL_2": 180,
    "LEVEL_3": 120
  },
  "min_speed_kmh": 5
} as const;

/** Map a 0-100 risk score onto its band. Scores are clamped into range. */
export function riskLevelFromScore(score: number): RiskLevel {
  const s = Math.max(0, Math.min(100, score));
  for (const band of RISK_BANDS) if (s <= band.max) return band.level;
  return "CRITICAL";
}
