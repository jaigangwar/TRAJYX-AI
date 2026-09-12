import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, OriginBadge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Kpi } from "@/components/ui/Kpi";
import { Panel } from "@/components/ui/Panel";
import { AsyncBoundary } from "@/components/ui/StateBlock";
import { useDashboardSummary, type DashboardSummary } from "@/features/dashboard/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { EVENT_LABELS, formatRelativeTime } from "@/lib/format";

const WINDOWS = [
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
];

export function OverviewPage() {
  const [windowHours, setWindowHours] = useState(24);
  const summary = useDashboardSummary(windowHours);

  usePageHeader(
    "Overview",
    "Platform state and recent safety events",
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
        onClick={() => void summary.refetch()}
        loading={summary.isFetching}
      >
        Refresh
      </Button>
    </div>,
  );

  return (
    <div className="space-y-3 p-4">
      <Panel title="Key indicators" meta={`last ${windowHours}h`}>
        <AsyncBoundary
          isLoading={summary.isLoading}
          error={summary.error}
          data={summary.data}
          errorTitle="Cannot reach the TRAJYX API"
          onRetry={() => void summary.refetch()}
        >
          {(data) => <Indicators data={data} />}
        </AsyncBoundary>
      </Panel>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Panel title="Recent events" className="lg:col-span-2" flush>
          <AsyncBoundary
            isLoading={summary.isLoading}
            error={summary.error}
            data={summary.data?.recent_events}
            emptyMessage="No safety events recorded yet."
            emptyHint="Events appear once a video has been analysed, or when demo mode seeds them."
            onRetry={() => void summary.refetch()}
            loadingVariant="rows"
          >
            {(events) => (
              <ul className="divide-line-subtle divide-y">
                {events.map((event) => (
                  <li key={event.id} className="flex items-center gap-3 px-3 py-2">
                    <span className="text-ink-subtle mono w-14 shrink-0 text-2xs">
                      {formatRelativeTime(event.timestamp)}
                    </span>
                    <span className="text-ink min-w-0 flex-1 truncate text-xs font-medium">
                      {EVENT_LABELS[event.event_type]}
                    </span>
                    <span className="text-ink-subtle w-32 shrink-0 truncate text-2xs">
                      {event.camera_name ?? "—"}
                    </span>
                    <OriginBadge origin={event.origin} />
                    {event.risk_score !== null && event.risk_score !== undefined ? (
                      <RiskBadge score={event.risk_score} showScore />
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </AsyncBoundary>
        </Panel>

        <Panel title="Pipeline readiness" meta="build state">
          <PipelineReadiness />
        </Panel>
      </div>
    </div>
  );
}

function Indicators({ data }: { data: DashboardSummary }) {
  const { cameras, events, risk, pipeline } = data;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4 lg:grid-cols-6">
        <Kpi
          label="Cameras online"
          value={cameras.online}
          note={`${cameras.total} registered`}
          tone={cameras.online > 0 ? "low" : "neutral"}
        />
        <Kpi
          label="Violations"
          value={events.violations}
          tone={events.violations > 0 ? "moderate" : "neutral"}
        />
        <Kpi
          label="Near misses"
          value={events.near_misses}
          tone={events.near_misses > 0 ? "high" : "neutral"}
        />
        <Kpi
          label="Critical events"
          value={events.critical}
          tone={events.critical > 0 ? "critical" : "neutral"}
        />
        <Kpi label="High-risk zones" value={risk.high_risk_zones} />
        <Kpi label="Average risk" value={risk.average_risk} unit="/100" />
      </div>

      <div className="border-line border-t pt-3">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4 lg:grid-cols-6">
          <Kpi label="Vehicles detected" value={pipeline.vehicles_detected} />
          <Kpi label="Pedestrians" value={pipeline.pedestrians_detected} />
          <Kpi label="Videos analysed" value={pipeline.videos_analysed} />
          <Kpi label="Behaviour events" value={events.behaviour} />
          <Kpi label="Driver reports" value={events.reports} />
          <Kpi
            label="Highest risk"
            value={null}
            note={risk.highest_risk_level ?? "nothing scored"}
          />
        </div>
      </div>

      {events.demo > 0 ? (
        <div className="border-accent-line bg-accent-dim flex items-center gap-2 rounded-sm border p-2.5">
          <Badge tone="accent">Demo data</Badge>
          <p className="text-ink-muted text-xs">
            {events.demo} of {events.total} events in this window are synthetic demo records.
          </p>
        </div>
      ) : null}
    </div>
  );
}

const PIPELINE_STAGES = [
  { stage: "Video ingest and job queue", phase: 3 },
  { stage: "Object detection (YOLO)", phase: 4 },
  { stage: "Multi-object tracking", phase: 5 },
  { stage: "Safety and violation detection", phase: 6 },
  { stage: "Trajectory and interaction", phase: 7 },
  { stage: "Near-miss and collision risk", phase: 8 },
  { stage: "Geospatial risk aggregation", phase: 10 },
  { stage: "Driver alert engine", phase: 14 },
] as const;

const CURRENT_PHASE = 2;

function PipelineReadiness() {
  return (
    <div>
      <p className="text-ink-muted mb-3 text-xs">
        Build progress of the observe → predict → warn pipeline. Not traffic data.
      </p>
      <ul className="divide-line-subtle divide-y">
        {PIPELINE_STAGES.map(({ stage, phase }) => {
          const done = phase <= CURRENT_PHASE;
          return (
            <li key={stage} className="flex items-center justify-between gap-2 py-1.5">
              <span className="text-ink-muted flex min-w-0 items-center gap-2 text-xs">
                {done ? (
                  <Icon name="check" size={12} className="text-risk-low shrink-0" />
                ) : (
                  <span
                    className="border-line-strong mx-px size-2.5 shrink-0 rounded-full border"
                    aria-hidden="true"
                  />
                )}
                <span className="truncate">{stage}</span>
              </span>
              <span className="text-ink-subtle shrink-0 text-2xs">
                {done ? "ready" : `Phase ${phase}`}
              </span>
            </li>
          );
        })}
      </ul>
      <Link
        to="/cameras"
        className="text-accent hover:text-accent-hover mt-3 inline-flex items-center gap-1 text-xs"
      >
        Configure cameras
        <Icon name="chevronRight" size={12} />
      </Link>
    </div>
  );
}
