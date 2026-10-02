/**
 * Analytics.
 *
 * Aggregate road-safety analysis over a rolling window. Every figure is
 * counted from stored records; nothing is modelled or extrapolated.
 *
 * Three honesty rules are load-bearing in this page:
 *
 *  - An hour in which no event carried a risk score shows an empty slot in
 *    the risk chart, not a zero bar. "Nothing was scored" and "everything
 *    scored zero" are different facts about a road.
 *  - A breakdown the platform cannot compute states why, in words, instead of
 *    rendering an empty chart that implies a measured zero.
 *  - When any record in the window is synthetic, the page says so at the top.
 *    An operator must never have to guess whether they are looking at traffic
 *    or at a demo.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { ColumnChart, ShareList, TrendLine, Unavailable } from "@/components/charts/Charts";
import { Badge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Kpi } from "@/components/ui/Kpi";
import { Panel } from "@/components/ui/Panel";
import { AsyncBoundary } from "@/components/ui/StateBlock";
import { useAnalytics, type Analytics, type Breakdown } from "@/features/analytics/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { RISK_PRESENTATION, riskLevelFromScore } from "@/lib/risk";

const WINDOWS = [
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
  { hours: 24 * 90, label: "90d" },
];

/** Colour a bar by the risk band its value falls in. */
function riskColour(score: number | null): string | undefined {
  if (score === null) return undefined;
  return RISK_PRESENTATION[riskLevelFromScore(score)].color;
}

export function AnalyticsPage() {
  const [windowHours, setWindowHours] = useState(24 * 7);
  const analytics = useAnalytics(windowHours);

  usePageHeader(
    "Analytics",
    "Aggregate road-safety analysis across time, location and vehicle class",
    <div className="flex items-center gap-1.5">
      <div className="border-line-strong flex overflow-hidden rounded-sm border">
        {WINDOWS.map((option) => (
          <button
            key={option.hours}
            type="button"
            onClick={() => setWindowHours(option.hours)}
            className={
              windowHours === option.hours
                ? "bg-accent-dim text-accent px-2 py-1 text-2xs font-semibold"
                : "text-ink-muted hover:bg-surface-hover px-2 py-1 text-2xs"
            }
          >
            {option.label}
          </button>
        ))}
      </div>
      <Button
        size="sm"
        variant="ghost"
        icon={<Icon name="refresh" size={13} />}
        onClick={() => void analytics.refetch()}
        loading={analytics.isFetching}
      >
        Refresh
      </Button>
    </div>,
  );

  return (
    <div className="p-4">
      <AsyncBoundary
        isLoading={analytics.isLoading}
        error={analytics.error}
        data={analytics.data}
        errorTitle="Cannot reach the TRAJYX API"
        onRetry={() => void analytics.refetch()}
      >
        {(data) => <AnalyticsBody data={data} />}
      </AsyncBoundary>
    </div>
  );
}

function AnalyticsBody({ data }: { data: Analytics }) {
  const { totals } = data;
  const allSynthetic = totals.events > 0 && totals.demo_events === totals.events;

  if (totals.events === 0) {
    return (
      <Unavailable
        reason={`No events are stored in the last ${data.window_label}. Analyse footage from the Video Analysis page, widen the window, or seed demo data with scripts/seed_demo.py.`}
      >
        <Link to="/analysis" className="text-accent mt-2 inline-block text-xs hover:underline">
          Go to Video Analysis →
        </Link>
      </Unavailable>
    );
  }

  return (
    <div className="space-y-3">
      {totals.demo_events > 0 ? (
        <div className="border-line-strong bg-surface-raised flex items-start gap-2 rounded-sm border px-3 py-2">
          <Icon name="info" size={13} className="text-ink-subtle mt-0.5 shrink-0" />
          <p className="text-ink-muted text-xs leading-relaxed">
            <span className="text-ink font-semibold">
              {allSynthetic
                ? "Every record below is synthetic."
                : `${totals.demo_events.toLocaleString()} of ${totals.events.toLocaleString()} records below are synthetic.`}
            </span>{" "}
            Demo data is seeded to exercise the risk engine and is not a measurement of any real
            road. Figures are not operational until measured footage replaces it.
          </p>
          <Badge tone="accent">Demo</Badge>
        </div>
      ) : null}

      {/* ---------------------------------------------------------- indicators */}
      <Panel title="Key indicators" meta={data.window_label}>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4 lg:grid-cols-7">
          <Kpi label="Events" value={totals.events} note={`${totals.scored_events} scored`} />
          <Kpi
            label="Violations"
            value={totals.violations}
            tone={totals.violations > 0 ? "moderate" : "neutral"}
          />
          <Kpi
            label="Near misses"
            value={totals.near_misses}
            tone={totals.near_misses > 0 ? "high" : "neutral"}
          />
          <Kpi
            label="Critical-scored"
            value={totals.critical}
            tone={totals.critical > 0 ? "critical" : "neutral"}
          />
          <Kpi
            label="Mean risk"
            value={totals.mean_risk}
            note={
              totals.mean_risk.available && totals.mean_risk.value !== null
                ? RISK_PRESENTATION[riskLevelFromScore(totals.mean_risk.value)].label
                : undefined
            }
            tone={
              totals.mean_risk.available && totals.mean_risk.value !== null
                ? (riskLevelFromScore(totals.mean_risk.value).toLowerCase() as
                    | "low"
                    | "moderate"
                    | "high"
                    | "critical")
                : "neutral"
            }
          />
          <Kpi
            label="Peak hour"
            value={
              data.peak_hour.available && data.peak_hour.value !== null
                ? `${String(data.peak_hour.value).padStart(2, "0")}:00`
                : data.peak_hour
            }
            note={
              data.peak_hour_events.available
                ? `${data.peak_hour_events.value?.toLocaleString()} events`
                : undefined
            }
          />
          <Kpi label="Inference" value={data.mean_inference_ms} unit="ms/frame" />
        </div>
      </Panel>

      {/* ------------------------------------------------------------- by hour */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Panel
          title="Activity by hour of day"
          meta={`${data.window_label}, all days combined`}
        >
          <ColumnChart
            data={data.by_hour.map((bucket) => ({
              key: bucket.key,
              label: bucket.label.slice(0, 2),
              hoverLabel: bucket.label,
              value: bucket.events,
              secondary: bucket.near_misses,
              note: `${bucket.violations} violations`,
            }))}
            labelEvery={3}
            secondaryLabel="near misses"
            height={112}
          />
          <Legend
            items={[
              { label: "Events", color: "var(--color-accent)" },
              { label: "Near misses", color: "var(--color-risk-critical)" },
            ]}
          />
        </Panel>

        <Panel title="Mean risk by hour of day" meta="empty slot = nothing scored that hour">
          <ColumnChart
            data={data.by_hour.map((bucket) => ({
              key: bucket.key,
              label: bucket.label.slice(0, 2),
              hoverLabel: bucket.label,
              // Null stays null: the chart draws a hatched slot, not a zero bar.
              value: bucket.mean_risk ?? null,
              color: riskColour(bucket.mean_risk ?? null),
              note:
                bucket.scored_events > 0
                  ? `${bucket.scored_events} scored of ${bucket.events} events`
                  : `${bucket.events} events, none carried a score`,
            }))}
            max={100}
            labelEvery={3}
            height={112}
          />
          <p className="text-ink-subtle mt-2 text-2xs leading-relaxed">
            Bars are coloured by risk band. A hatched column is an hour in which events were
            recorded but none carried a risk score — not an hour of zero risk.
          </p>
        </Panel>
      </div>

      {/* -------------------------------------------------------------- trends */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Panel title="Daily trend" meta="events per day" className="xl:col-span-2">
          <TrendLine
            data={data.by_day.map((bucket) => ({
              key: bucket.key,
              label: bucket.label,
              value: bucket.events,
            }))}
            height={128}
          />
          <div className="border-line-subtle mt-2 grid grid-cols-3 gap-3 border-t pt-2">
            <DayStat label="Busiest day" buckets={data.by_day} pick="max" />
            <DayStat label="Quietest day" buckets={data.by_day} pick="min" />
            <div>
              <span className="field-label mb-0">Days covered</span>
              <p className="text-ink mono mt-1 text-sm">{data.by_day.length}</p>
            </div>
          </div>
        </Panel>

        <Panel title="Activity by weekday" meta="Monday first">
          <ColumnChart
            data={data.by_weekday.map((bucket) => ({
              key: bucket.key,
              label: bucket.label,
              value: bucket.events,
              secondary: bucket.near_misses,
            }))}
            secondaryLabel="near misses"
            height={128}
          />
        </Panel>
      </div>

      {/* --------------------------------------------------------- breakdowns */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Panel title="Events by type" meta={`${data.by_event_type.total} total`}>
          <BreakdownBlock breakdown={data.by_event_type} limit={8} />
        </Panel>

        <Panel title="By severity">
          <BreakdownBlock
            breakdown={data.by_severity}
            colors={{
              CRITICAL: "var(--color-risk-critical)",
              MAJOR: "var(--color-risk-high)",
              MINOR: "var(--color-risk-moderate)",
              INFO: "var(--color-ink-subtle)",
            }}
          />
        </Panel>

        <Panel title="Traffic composition" meta="from detections">
          <BreakdownBlock breakdown={data.traffic_composition} limit={8} />
        </Panel>

        <Panel title="Record origin" meta="measured vs synthetic">
          <BreakdownBlock
            breakdown={data.by_origin}
            colors={{
              MEASURED: "var(--color-risk-low)",
              ESTIMATED: "var(--color-risk-moderate)",
              DEMO: "var(--color-accent)",
            }}
          />
          <p className="text-ink-subtle mt-2 text-2xs leading-relaxed">
            Every stored record carries its origin, so the share of the dataset that is measured
            is always auditable.
          </p>
        </Panel>
      </div>

      {/* ------------------------------------------------- segments & coverage */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Panel title="Road segments by risk" meta="score from the geospatial aggregator" flush>
          {data.top_segments.length === 0 ? (
            <div className="p-3">
              <Unavailable reason="No road segment has a risk score or any events in this window." />
            </div>
          ) : (
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-line-strong border-b">
                  <th className="text-ink-subtle px-2.5 py-1.5 text-left text-2xs font-semibold tracking-wide uppercase">
                    Segment
                  </th>
                  <th className="text-ink-subtle px-2.5 py-1.5 text-right text-2xs font-semibold tracking-wide uppercase">
                    Risk
                  </th>
                  <th className="text-ink-subtle px-2.5 py-1.5 text-right text-2xs font-semibold tracking-wide uppercase">
                    Events
                  </th>
                  <th className="text-ink-subtle px-2.5 py-1.5 text-right text-2xs font-semibold tracking-wide uppercase">
                    Near miss
                  </th>
                  <th className="text-ink-subtle px-2.5 py-1.5 text-right text-2xs font-semibold tracking-wide uppercase">
                    Peak
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.top_segments.map((segment) => (
                  <tr key={segment.id} className="border-line-subtle border-b last:border-0">
                    <td className="px-2.5 py-1.5">
                      <Link
                        to="/risk-map"
                        className="text-ink hover:text-accent font-medium transition-colors"
                      >
                        {segment.name}
                      </Link>
                      {segment.road_name ? (
                        <span className="text-ink-subtle ml-1.5 text-2xs">
                          {segment.road_name}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-2.5 py-1.5 text-right">
                      {segment.risk_score !== null && segment.risk_score !== undefined ? (
                        <RiskBadge score={segment.risk_score} showScore />
                      ) : (
                        <span
                          className="text-ink-subtle text-2xs"
                          title="This segment has never been scored by the geospatial aggregator."
                        >
                          not scored
                        </span>
                      )}
                    </td>
                    <td className="text-ink-muted px-2.5 py-1.5 text-right tabular-nums">
                      {segment.events.toLocaleString()}
                    </td>
                    <td className="text-ink-muted px-2.5 py-1.5 text-right tabular-nums">
                      {segment.near_misses.toLocaleString()}
                    </td>
                    <td className="text-ink-subtle mono px-2.5 py-1.5 text-right text-2xs">
                      {segment.peak_hour !== null && segment.peak_hour !== undefined
                        ? `${String(segment.peak_hour).padStart(2, "0")}:00`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel title="Detector coverage" meta="what the cameras could actually check">
          {data.detector_coverage.length === 0 ? (
            <Unavailable reason="No video has been analysed in this window, so detector capability is unknown. Coverage is read from the analysis runs themselves, never assumed from the camera list." />
          ) : (
            <>
              <ul className="space-y-1.5">
                {data.detector_coverage.map((row) => {
                  const ratio =
                    row.analyses_total > 0 ? row.analyses_supported / row.analyses_total : 0;
                  return (
                    <li key={row.check}>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-ink-muted truncate text-xs">{row.label}</span>
                        <span className="text-ink-subtle mono shrink-0 text-2xs tabular-nums">
                          {row.analyses_supported}/{row.analyses_total} runs
                        </span>
                      </div>
                      <div className="bg-surface-sunken mt-1 h-1 overflow-hidden rounded-full">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${ratio * 100}%`,
                            backgroundColor:
                              ratio === 0
                                ? "var(--color-risk-critical)"
                                : ratio < 1
                                  ? "var(--color-risk-moderate)"
                                  : "var(--color-risk-low)",
                          }}
                        />
                      </div>
                      {row.reasons.length > 0 ? (
                        <p className="text-ink-subtle mt-0.5 text-2xs leading-snug">
                          {row.reasons[0]}
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              <p className="text-ink-subtle border-line-subtle mt-2 border-t pt-2 text-2xs leading-relaxed">
                A check with no supporting camera reports nothing. That is a coverage gap, not a
                clean road — which is why this panel sits beside the counts rather than behind
                them.
              </p>
            </>
          )}
        </Panel>
      </div>

      {/* ------------------------------------------------------------ compliance */}
      <Panel title="Compliance measures" meta="what can and cannot be measured">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <Kpi label="Helmet violations detected" value={data.helmet_violations} />
            <p className="text-ink-subtle mt-1 text-2xs leading-relaxed">
              Counted from stored events in this window.
            </p>
          </div>
          <div className="md:col-span-2">
            <span className="field-label">Helmet compliance rate</span>
            <Unavailable reason={data.helmet_compliance_rate.unavailable_reason ?? "Not available."} />
          </div>
        </div>
      </Panel>

      <p className="text-ink-subtle px-1 text-2xs">
        Generated {new Date(data.generated_at).toLocaleString()} · window {data.window_label} ·
        every figure counted from stored records
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ helpers */

function BreakdownBlock({
  breakdown,
  limit,
  colors,
}: {
  breakdown: Breakdown;
  limit?: number;
  colors?: Record<string, string>;
}) {
  if (!breakdown.available) {
    return <Unavailable reason={breakdown.unavailable_reason ?? "Nothing has produced this yet."} />;
  }
  return (
    <ShareList
      limit={limit}
      data={breakdown.slices.map((slice) => ({
        key: slice.key,
        label: slice.label,
        count: slice.count,
        share: slice.share,
        color: colors?.[slice.key],
      }))}
    />
  );
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="mt-2 flex items-center gap-3">
      {items.map((item) => (
        <span key={item.label} className="text-ink-subtle flex items-center gap-1 text-2xs">
          <span
            className="inline-block h-1.5 w-3 rounded-[1px]"
            style={{ backgroundColor: item.color }}
          />
          {item.label}
        </span>
      ))}
    </div>
  );
}

function DayStat({
  label,
  buckets,
  pick,
}: {
  label: string;
  buckets: { label: string; events: number }[];
  pick: "max" | "min";
}) {
  const withData = buckets.filter((bucket) => bucket.events > 0);
  if (withData.length === 0) {
    return (
      <div>
        <span className="field-label mb-0">{label}</span>
        <p className="text-ink-subtle mono mt-1 text-sm">—</p>
      </div>
    );
  }
  const chosen = withData.reduce((best, bucket) =>
    pick === "max"
      ? bucket.events > best.events
        ? bucket
        : best
      : bucket.events < best.events
        ? bucket
        : best,
  );
  return (
    <div>
      <span className="field-label mb-0">{label}</span>
      <p className="text-ink mono mt-1 text-sm">{chosen.label}</p>
      <p className="text-ink-subtle text-2xs">{chosen.events.toLocaleString()} events</p>
    </div>
  );
}
