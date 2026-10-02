/**
 * Model Health.
 *
 * The registry and its measured performance. Two decisions shape this page:
 *
 * 1. A model appears here because an analysis run actually used it, not
 *    because someone added a row. A registry that can list a model the
 *    platform has never executed is a registry that can lie about what is
 *    deployed.
 *
 * 2. Accuracy is not shown as a number unless a recorded evaluation run
 *    against a named dataset produced it. Precision, recall and F1 are the
 *    figures a safety product is most tempted to invent, and the most
 *    damaging to invent, so the unevaluated state is stated prominently
 *    rather than tucked into a tooltip. Detection confidence is never
 *    substituted: it is the model's own certainty and says nothing about
 *    whether it was right.
 *
 * "Healthy" here is a claim about speed and reliability — the two things this
 * platform measures — and the page says so in as many words.
 */

import { useState } from "react";

import { Unavailable } from "@/components/charts/Charts";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Kpi } from "@/components/ui/Kpi";
import { Panel } from "@/components/ui/Panel";
import { AsyncBoundary } from "@/components/ui/StateBlock";
import {
  useModelHealth,
  type Metric,
  type ModelHealthReport,
  type ModelVersion,
} from "@/features/models/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { formatTimestamp } from "@/lib/format";
import type { ModelHealth } from "@shared/domain";

const WINDOWS = [
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
  { hours: 24 * 90, label: "90d" },
  { hours: 24 * 365, label: "1y" },
];

const HEALTH_TONE: Record<
  ModelHealth,
  "low" | "moderate" | "critical" | "neutral"
> = {
  HEALTHY: "low",
  WARNING: "moderate",
  NEEDS_ATTENTION: "critical",
  UNKNOWN: "neutral",
};

const HEALTH_LABEL: Record<ModelHealth, string> = {
  HEALTHY: "Healthy",
  WARNING: "Warning",
  NEEDS_ATTENTION: "Needs attention",
  UNKNOWN: "Unknown",
};

const ROLE_LABEL: Record<string, string> = {
  detection: "Object detection",
  tracking: "Multi-object tracking",
  risk: "Risk scoring",
};

export function ModelHealthPage() {
  const [windowHours, setWindowHours] = useState(24 * 30);
  const health = useModelHealth(windowHours);

  usePageHeader(
    "Model Health",
    "The model registry and its measured performance",
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
        onClick={() => void health.refetch()}
        loading={health.isFetching}
      >
        Refresh
      </Button>
    </div>,
  );

  return (
    <div className="space-y-3 p-4">
      <AsyncBoundary
        isLoading={health.isLoading}
        error={health.error}
        data={health.data}
        errorTitle="Cannot reach the TRAJYX API"
        onRetry={() => void health.refetch()}
      >
        {(data) => <ModelHealthBody data={data} />}
      </AsyncBoundary>
    </div>
  );
}

function ModelHealthBody({ data }: { data: ModelHealthReport }) {
  if (data.models.length === 0) {
    return (
      <Unavailable reason="No analysis run has executed in this window, so no model version can be reported. The registry is derived from runs that actually happened — it is deliberately unable to list a model the platform has never executed. Analyse a video, or widen the window." />
    );
  }

  return (
    <>
      {/* -------------------------------------------------- evaluation notice */}
      {!data.evaluation_available ? (
        <div className="border-line-strong bg-surface-raised flex items-start gap-2 rounded-sm border px-3 py-2.5">
          <Icon
            name="alert"
            size={14}
            className="text-risk-moderate mt-0.5 shrink-0"
          />
          <div className="min-w-0">
            <p className="text-ink text-xs font-semibold">
              Accuracy has not been evaluated
            </p>
            <p className="text-ink-muted mt-1 text-xs leading-relaxed">
              {data.evaluation_note}
            </p>
            <p className="text-ink-subtle mt-1.5 text-2xs leading-relaxed">
              Everything below measures throughput and reliability. A model
              marked{" "}
              <span className="text-risk-low font-semibold">Healthy</span> is
              fast and does not crash — that is the entire claim, and it is not
              a statement about whether its detections are correct.
            </p>
          </div>
        </div>
      ) : null}

      {/* --------------------------------------------------------- model cards */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {data.models.map((model) => (
          <ModelCard
            key={`${model.name}-${model.version ?? "none"}-${model.role}`}
            model={model}
          />
        ))}
      </div>

      {/* -------------------------------------------------- how health is set */}
      <Panel title="How health is determined" meta="thresholds, stated">
        <div className="grid grid-cols-1 gap-x-6 gap-y-3 text-xs md:grid-cols-2">
          <Rule
            tone="low"
            label="Healthy"
            body="Every analysis job completed, and mean inference is under 66 ms per frame — twice the 33 ms a 30 fps stream needs, which leaves headroom for batching."
          />
          <Rule
            tone="moderate"
            label="Warning"
            body="Either 5% or more of analysis jobs failed, or mean inference reached 66 ms per frame, at which point a single worker can no longer keep up with a live 30 fps camera."
          />
          <Rule
            tone="critical"
            label="Needs attention"
            body="Either 20% or more of jobs failed, or mean inference reached 200 ms per frame — far slower than real time, so backlog grows faster than it clears."
          />
          <Rule
            tone="neutral"
            label="Unknown"
            body="No run in the window recorded an inference time, so speed cannot be judged. Reported as unknown rather than assumed healthy."
          />
        </div>
      </Panel>

      <p className="text-ink-subtle px-1 text-2xs">
        Generated {formatTimestamp(data.generated_at)} · window{" "}
        {Math.round(data.window_hours / 24)} days · derived from stored analysis
        runs and job outcomes
      </p>
    </>
  );
}

/* --------------------------------------------------------------- model card */

function ModelCard({ model }: { model: ModelVersion }) {
  const evaluated = model.accuracy.precision.available;

  return (
    <Panel
      title={model.name}
      meta={
        <span className="mono">
          {model.version ?? (
            <span
              className="text-ink-subtle"
              title="The analysis record stores no version for this component, so its runs cannot be attributed to a specific build."
            >
              version not recorded
            </span>
          )}{" "}
          · {ROLE_LABEL[model.role] ?? model.role}
        </span>
      }
      actions={
        <div className="flex items-center gap-1.5">
          {!model.registered ? (
            <Badge
              tone="neutral"
              title="Observed from analysis runs only; no registry record exists."
            >
              Unregistered
            </Badge>
          ) : null}
          <Badge tone={HEALTH_TONE[model.health]}>
            {HEALTH_LABEL[model.health]}
          </Badge>
        </div>
      }
    >
      <p className="text-ink-muted text-xs leading-relaxed">
        {model.health_reason}
      </p>

      {/* ------------------------------------------------------------ throughput */}
      <div className="border-line-subtle mt-3 grid grid-cols-2 gap-x-4 gap-y-3 border-t pt-3 sm:grid-cols-4">
        <Kpi label="Runs" value={model.runs} />
        <Kpi label="Frames" value={model.frames_processed} />
        <Kpi label="Detections" value={model.detections} />
        <Kpi
          label="Job failures"
          value={model.failure_rate}
          unit="%"
          tone={
            model.failure_rate.available && (model.failure_rate.value ?? 0) > 0
              ? "critical"
              : "neutral"
          }
          note={`${model.jobs_succeeded} ok · ${model.jobs_failed} failed`}
        />
      </div>

      {/* --------------------------------------------------------------- latency */}
      <div className="border-line-subtle mt-3 border-t pt-3">
        <div className="flex items-baseline justify-between">
          <span className="field-label mb-0">Inference latency, per frame</span>
          <span className="text-ink-subtle text-2xs">
            {model.latency.samples}{" "}
            {model.latency.samples === 1 ? "sample" : "samples"}
          </span>
        </div>
        <div className="mt-2 grid grid-cols-4 gap-x-4">
          <Kpi label="Mean" value={model.latency.mean_ms} unit="ms" />
          <Kpi label="Median" value={model.latency.median_ms} unit="ms" />
          <Kpi label="p95" value={model.latency.p95_ms} unit="ms" />
          <Kpi label="Slowest" value={model.latency.slowest_ms} unit="ms" />
        </div>
        <p className="text-ink-subtle mt-1.5 text-2xs leading-relaxed">
          {model.role === "detection"
            ? "Measured wall-clock time the detector spent per analysed frame. p95 is a nearest-rank percentile, so it is always a figure some run actually produced."
            : (model.latency.mean_ms.unavailable_reason ??
              "No per-frame timing exists for this stage.")}
        </p>
      </div>

      {/* -------------------------------------------------------------- accuracy */}
      <div className="border-line-subtle mt-3 border-t pt-3">
        <div className="flex items-baseline justify-between">
          <span className="field-label mb-0">Accuracy</span>
          {evaluated && model.accuracy.dataset_version ? (
            <span className="text-ink-subtle mono text-2xs">
              {model.accuracy.dataset_version}
            </span>
          ) : null}
        </div>

        {evaluated ? (
          <>
            <div className="mt-2 grid grid-cols-3 gap-x-4">
              <Kpi label="Precision" value={model.accuracy.precision} />
              <Kpi label="Recall" value={model.accuracy.recall} />
              <Kpi label="F1" value={model.accuracy.f1} />
            </div>
            {model.accuracy.evaluated_at ? (
              <p className="text-ink-subtle mt-1.5 text-2xs">
                Evaluated {formatTimestamp(model.accuracy.evaluated_at)} against{" "}
                {model.accuracy.dataset_version}.
              </p>
            ) : null}
          </>
        ) : (
          <div className="mt-2">
            <div className="mb-2 grid grid-cols-3 gap-x-4">
              <UnevaluatedMetric
                label="Precision"
                metric={model.accuracy.precision}
              />
              <UnevaluatedMetric
                label="Recall"
                metric={model.accuracy.recall}
              />
              <UnevaluatedMetric label="F1" metric={model.accuracy.f1} />
            </div>
            <Unavailable
              reason={
                model.accuracy.precision.unavailable_reason ?? "Not evaluated."
              }
            />
          </div>
        )}
      </div>

      {model.notes.length > 0 ? (
        <ul className="border-line-subtle mt-3 space-y-1 border-t pt-2">
          {model.notes.map((note) => (
            <li
              key={note}
              className="text-ink-subtle flex gap-1.5 text-2xs leading-relaxed"
            >
              <Icon name="info" size={11} className="mt-0.5 shrink-0" />
              {note}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="text-ink-subtle mono mt-2 text-2xs">
        {model.first_seen_at
          ? `first run ${formatTimestamp(model.first_seen_at)}`
          : "—"}
        {model.last_seen_at
          ? ` · last run ${formatTimestamp(model.last_seen_at)}`
          : ""}
      </p>
    </Panel>
  );
}

/**
 * An accuracy figure that has never been measured.
 *
 * Rendered as an explicit "not evaluated" rather than a dash, because a dash
 * in a row of numbers reads as a rounding artefact. This has to read as a
 * deliberate absence.
 */
function UnevaluatedMetric({
  label,
  metric,
}: {
  label: string;
  metric: Metric;
}) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1">
        <span className="field-label mb-0">{label}</span>
        <span
          title={metric.unavailable_reason ?? "Not evaluated."}
          className="text-ink-subtle cursor-help"
        >
          <Icon name="info" size={11} />
        </span>
      </div>
      <p className="text-ink-subtle mt-1 text-2xs font-semibold tracking-wide uppercase">
        Not evaluated
      </p>
    </div>
  );
}

function Rule({
  tone,
  label,
  body,
}: {
  tone: "low" | "moderate" | "critical" | "neutral";
  label: string;
  body: string;
}) {
  return (
    <div className="flex gap-2">
      <Badge tone={tone} className="mt-0.5 h-fit shrink-0">
        {label}
      </Badge>
      <p className="text-ink-muted text-xs leading-relaxed">{body}</p>
    </div>
  );
}
