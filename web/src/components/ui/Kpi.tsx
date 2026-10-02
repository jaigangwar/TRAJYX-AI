/** KPI tile. A metric that cannot be computed shows a dash, never a zero. */

import type { Metric } from "@/features/dashboard/api";
import { Icon } from "@/components/ui/Icon";
import { cn } from "@/lib/cn";

interface KpiProps {
  label: string;
  /**
   * A counted integer, a `Metric` when availability matters, or an
   * already-formatted string for values a number cannot carry — a clock time
   * such as "19:00", for instance.
   */
  value: number | string | Metric | null | undefined;
  unit?: string;
  /** Small line under the value. */
  note?: string;
  tone?: "neutral" | "low" | "moderate" | "high" | "critical" | "accent";
  className?: string;
}

const TONE: Record<NonNullable<KpiProps["tone"]>, string> = {
  neutral: "text-ink",
  low: "text-risk-low",
  moderate: "text-risk-moderate",
  high: "text-risk-high",
  critical: "text-risk-critical",
  accent: "text-accent",
};

function isMetric(value: unknown): value is Metric {
  return typeof value === "object" && value !== null && "available" in value;
}

export function Kpi({ label, value, unit, note, tone = "neutral", className }: KpiProps) {
  let display: string;
  let unavailableReason: string | null = null;

  if (isMetric(value)) {
    if (value.available && value.value !== null) {
      display = formatNumber(value.value);
    } else {
      display = "—";
      unavailableReason = value.unavailable_reason ?? "Not available yet.";
    }
  } else if (typeof value === "number") {
    display = formatNumber(value);
  } else if (typeof value === "string") {
    display = value;
  } else {
    display = "—";
    unavailableReason = "Not available yet.";
  }

  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-center gap-1">
        <span className="field-label mb-0">{label}</span>
        {unavailableReason ? (
          <span title={unavailableReason} className="text-ink-subtle cursor-help">
            <Icon name="info" size={11} />
          </span>
        ) : null}
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span
          className={cn(
            "metric text-2xl leading-none",
            unavailableReason ? "text-ink-subtle" : TONE[tone],
          )}
        >
          {display}
        </span>
        {unit && !unavailableReason ? (
          <span className="text-ink-subtle text-2xs">{unit}</span>
        ) : null}
      </div>
      {note ? <p className="text-ink-subtle mt-1 truncate text-2xs">{note}</p> : null}
    </div>
  );
}

function formatNumber(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
