/**
 * Presentation rules for the risk vocabulary.
 *
 * The mapping from a risk level to a colour lives here and nowhere else, so
 * the whole product — tables, map, charts, 3D view, mobile parity — speaks one
 * visual language. Risk is always rendered as colour *plus* a text label;
 * colour alone is never the only carrier of meaning.
 */

import {
  riskLevelFromScore,
  type RiskLevel,
  type Severity,
  type TtcBand,
} from "@shared/domain";

export { riskLevelFromScore };
export type { RiskLevel };

interface RiskPresentation {
  /** Human label as shown in the UI. */
  label: string;
  /** CSS colour for text, strokes and chart marks. */
  color: string;
  /** Tinted background for badges and table row emphasis. */
  background: string;
  /** Tailwind text-colour class, for JSX that prefers utilities. */
  textClass: string;
  /** Tailwind background class for the tinted fill. */
  bgClass: string;
  /** Tailwind border class. */
  borderClass: string;
}

export const RISK_PRESENTATION: Record<RiskLevel, RiskPresentation> = {
  LOW: {
    label: "Low",
    color: "var(--color-risk-low)",
    background: "var(--color-risk-low-dim)",
    textClass: "text-risk-low",
    bgClass: "bg-risk-low-dim",
    borderClass: "border-risk-low/40",
  },
  MODERATE: {
    label: "Moderate",
    color: "var(--color-risk-moderate)",
    background: "var(--color-risk-moderate-dim)",
    textClass: "text-risk-moderate",
    bgClass: "bg-risk-moderate-dim",
    borderClass: "border-risk-moderate/40",
  },
  HIGH: {
    label: "High",
    color: "var(--color-risk-high)",
    background: "var(--color-risk-high-dim)",
    textClass: "text-risk-high",
    bgClass: "bg-risk-high-dim",
    borderClass: "border-risk-high/40",
  },
  CRITICAL: {
    label: "Critical",
    color: "var(--color-risk-critical)",
    background: "var(--color-risk-critical-dim)",
    textClass: "text-risk-critical",
    bgClass: "bg-risk-critical-dim",
    borderClass: "border-risk-critical/40",
  },
};

export function riskPresentation(level: RiskLevel): RiskPresentation {
  return RISK_PRESENTATION[level];
}

/** Convenience for the common case of having a score rather than a level. */
export function riskPresentationForScore(score: number): RiskPresentation {
  return RISK_PRESENTATION[riskLevelFromScore(score)];
}

/** Ordered low-to-high, for legends, filter lists and sort comparators. */
export const RISK_LEVELS_ASCENDING: readonly RiskLevel[] = ["LOW", "MODERATE", "HIGH", "CRITICAL"];

export function compareRiskLevel(a: RiskLevel, b: RiskLevel): number {
  return RISK_LEVELS_ASCENDING.indexOf(a) - RISK_LEVELS_ASCENDING.indexOf(b);
}

/** Severity reuses the risk ramp; INFO is informational rather than a risk band. */
export const SEVERITY_PRESENTATION: Record<Severity, { label: string; color: string; background: string }> = {
  INFO: { label: "Info", color: "var(--color-info)", background: "var(--color-info-dim)" },
  MINOR: {
    label: "Minor",
    color: "var(--color-risk-moderate)",
    background: "var(--color-risk-moderate-dim)",
  },
  MAJOR: { label: "Major", color: "var(--color-risk-high)", background: "var(--color-risk-high-dim)" },
  CRITICAL: {
    label: "Critical",
    color: "var(--color-risk-critical)",
    background: "var(--color-risk-critical-dim)",
  },
};

/**
 * TTC bands read inversely to risk: a *long* time to collision is safe.
 * Keeping this mapping explicit avoids the easy mistake of colouring
 * `TtcBand.LOW` red because "LOW" is first in the enum.
 */
export const TTC_PRESENTATION: Record<TtcBand, { label: string; color: string }> = {
  LOW: { label: "Low", color: "var(--color-risk-low)" },
  MEDIUM: { label: "Medium", color: "var(--color-risk-moderate)" },
  HIGH: { label: "High", color: "var(--color-risk-high)" },
  CRITICAL: { label: "Critical", color: "var(--color-risk-critical)" },
};
