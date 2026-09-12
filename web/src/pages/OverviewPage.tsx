/**
 * Overview.
 *
 * Phase 0 scope: prove the web tier genuinely talks to the API and report the
 * platform's real state. Traffic KPIs (vehicles detected, violations today,
 * near misses, average risk) arrive in phase 2, once there is a database
 * behind them — they are deliberately absent rather than stubbed.
 */

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Panel } from "@/components/ui/Panel";
import { AsyncBoundary } from "@/components/ui/StateBlock";
import { useHealth, type Health } from "@/features/system/api";
import { usePageHeader } from "@/hooks/usePageHeader";

export function OverviewPage() {
  const health = useHealth();

  usePageHeader(
    "Overview",
    "Platform state and pipeline readiness",
    <Button
      size="sm"
      variant="ghost"
      icon={<Icon name="refresh" size={13} />}
      onClick={() => void health.refetch()}
      loading={health.isFetching}
    >
      Refresh
    </Button>,
  );

  return (
    <div className="space-y-3 p-4">
      <Panel title="Platform status">
        <AsyncBoundary
          isLoading={health.isLoading}
          error={health.error}
          data={health.data}
          errorTitle="Cannot reach the TRAJYX API"
          onRetry={() => void health.refetch()}
          loadingLabel="Checking platform status"
        >
          {(data) => <PlatformStatus health={data} />}
        </AsyncBoundary>
      </Panel>

      <Panel title="Pipeline readiness" meta="Phase 0">
        <PipelineReadiness />
      </Panel>
    </div>
  );
}

function PlatformStatus({ health }: { health: Health }) {
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
        <Field label="Service" value={health.service} />
        <Field label="API version" value={health.version} mono />
        <Field label="Environment" value={health.environment} />
        <Field label="Contract" value={health.contract_version} mono />
        <Field
          label="Data backend"
          value={health.capabilities.data_backend}
          tone={health.capabilities.data_backend === "local" ? "warn" : "ok"}
        />
        <Field
          label="Auth backend"
          value={health.capabilities.auth_backend}
          tone={health.capabilities.auth_backend === "local" ? "warn" : "ok"}
        />
        <Field
          label="Object storage"
          value={health.capabilities.storage_backend}
          tone={health.capabilities.storage_backend === "local" ? "warn" : "ok"}
        />
        <Field label="Demo mode" value={health.capabilities.demo_mode ? "enabled" : "disabled"} />
      </dl>

      {health.warnings.length > 0 ? (
        <div className="border-risk-moderate/35 bg-risk-moderate-dim rounded-sm border p-2.5">
          <h3 className="text-risk-moderate mb-1.5 text-2xs font-semibold tracking-wider uppercase">
            Configuration notes
          </h3>
          <ul className="space-y-1">
            {health.warnings.map((warning) => (
              <li key={warning} className="text-ink-muted text-xs">
                {warning}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  tone = "neutral",
}: {
  label: string;
  value: string;
  mono?: boolean;
  tone?: "neutral" | "ok" | "warn";
}) {
  const toneClass =
    tone === "ok" ? "text-risk-low" : tone === "warn" ? "text-risk-moderate" : "text-ink";
  return (
    <div className="min-w-0">
      <dt className="field-label">{label}</dt>
      <dd className={`truncate text-xs font-medium ${toneClass} ${mono ? "mono" : ""}`}>{value}</dd>
    </div>
  );
}

/**
 * Build-out state of the analysis pipeline, read from the phase plan. This is
 * project status rather than traffic data, and is labeled as such.
 */
const PIPELINE_STAGES = [
  { stage: "Video ingest and job queue", phase: 3 },
  { stage: "Object detection (YOLO)", phase: 4 },
  { stage: "Multi-object tracking", phase: 5 },
  { stage: "Safety and violation detection", phase: 6 },
  { stage: "Trajectory and interaction analysis", phase: 7 },
  { stage: "Near-miss and collision risk", phase: 8 },
  { stage: "ML risk model", phase: 9 },
  { stage: "Geospatial risk aggregation", phase: 10 },
  { stage: "Driver alert engine", phase: 14 },
] as const;

const CURRENT_PHASE = 0;

function PipelineReadiness() {
  return (
    <div>
      <p className="text-ink-muted mb-3 text-xs">
        Implementation state of the observe → track → understand → predict → warn pipeline. This
        panel reports build progress, not traffic measurements.
      </p>
      <ul className="divide-line-subtle divide-y">
        {PIPELINE_STAGES.map(({ stage, phase }) => {
          const done = phase <= CURRENT_PHASE;
          return (
            <li key={stage} className="flex items-center justify-between gap-3 py-1.5">
              <span className="text-ink-muted flex min-w-0 items-center gap-2 text-xs">
                {done ? (
                  <Icon name="check" size={13} className="text-risk-low shrink-0" />
                ) : (
                  <span
                    className="border-line-strong mx-px size-2.5 shrink-0 rounded-full border"
                    aria-hidden="true"
                  />
                )}
                <span className="truncate">{stage}</span>
              </span>
              {done ? (
                <Badge tone="low">Ready</Badge>
              ) : (
                <span className="text-ink-subtle shrink-0 text-2xs">Phase {phase}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
