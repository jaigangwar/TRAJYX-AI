/**
 * Risk Map.
 *
 * Full-screen GIS view: filters on the left, map in the centre, hotspot
 * detail on the right. Clicking empty map probes the driver alert engine at
 * that point, which is how an operator checks what a driver would actually be
 * told there.
 */

import { useState } from "react";

import { Badge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { AsyncBoundary, ErrorState } from "@/components/ui/StateBlock";
import { useCameras } from "@/features/dashboard/api";
import { RiskMap } from "@/features/risk/RiskMap";
import {
  useAggregateRisk,
  useEvaluateAlert,
  useSegmentDetail,
  useSegments,
  useZones,
  type SegmentDetail,
} from "@/features/risk/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { EVENT_LABELS, formatTimestamp } from "@/lib/format";
import { RISK_LEVELS_ASCENDING, riskPresentation } from "@/lib/risk";
import type { EventType, RiskLevel } from "@shared/domain";

const WINDOWS = [
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
];

export function RiskMapPage() {
  const [minimumLevel, setMinimumLevel] = useState<RiskLevel | "">("");
  const [windowHours, setWindowHours] = useState(24 * 7);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [probe, setProbe] = useState<{ latitude: number; longitude: number } | null>(null);

  const segments = useSegments();
  const zones = useZones(minimumLevel || undefined);
  const cameras = useCameras();
  const detail = useSegmentDetail(selectedId);
  const aggregate = useAggregateRisk();
  const evaluate = useEvaluateAlert();

  usePageHeader(
    "Risk Map",
    "Road-segment risk, risk zones and camera coverage",
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
        variant="secondary"
        icon={<Icon name="refresh" size={13} />}
        loading={aggregate.isPending}
        onClick={() => aggregate.mutate(windowHours)}
      >
        Recompute
      </Button>
    </div>,
  );

  const handleProbe = (latitude: number, longitude: number) => {
    setProbe({ latitude, longitude });
    setSelectedId(null);
    evaluate.mutate({ latitude, longitude, radius_m: 1500 });
  };

  return (
    <div className="flex h-full min-h-0">
      {/* Filters */}
      <aside className="border-line bg-surface w-[230px] shrink-0 overflow-y-auto border-r">
        <div className="panel-header">
          <h2 className="panel-title">Filters</h2>
        </div>
        <div className="space-y-4 p-3">
          <div>
            <span className="field-label">Minimum risk level</span>
            <div className="space-y-1">
              <FilterRow
                label="All levels"
                active={minimumLevel === ""}
                onClick={() => setMinimumLevel("")}
              />
              {[...RISK_LEVELS_ASCENDING].reverse().map((level) => (
                <FilterRow
                  key={level}
                  label={riskPresentation(level).label}
                  colour={riskPresentation(level).color}
                  active={minimumLevel === level}
                  onClick={() => setMinimumLevel(level)}
                />
              ))}
            </div>
          </div>

          <div className="border-line border-t pt-3">
            <span className="field-label">Legend</span>
            <ul className="space-y-1.5">
              {[...RISK_LEVELS_ASCENDING].reverse().map((level) => (
                <li key={level} className="flex items-center gap-2 text-xs">
                  <span
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: riskPresentation(level).color }}
                  />
                  <span className="text-ink-muted">{riskPresentation(level).label}</span>
                </li>
              ))}
              <li className="flex items-center gap-2 text-xs">
                <span className="bg-ink-muted size-2.5 shrink-0 rounded-full" />
                <span className="text-ink-muted">Camera</span>
              </li>
              <li className="flex items-center gap-2 text-xs">
                <span className="bg-line-strong size-2.5 shrink-0 rounded-full" />
                <span className="text-ink-subtle">Unscored segment</span>
              </li>
            </ul>
          </div>

          <div className="border-line border-t pt-3">
            <span className="field-label">Counts</span>
            <dl className="space-y-1">
              <CountRow label="Segments" value={segments.data?.length ?? 0} />
              <CountRow label="Risk zones" value={zones.data?.length ?? 0} />
              <CountRow label="Cameras" value={cameras.data?.items.length ?? 0} />
            </dl>
          </div>

          <p className="text-ink-subtle border-line border-t pt-3 text-2xs leading-relaxed">
            Zones are computed from attributed events, never placed by hand. Click empty map to
            check what a driver would be told at that point.
          </p>
        </div>
      </aside>

      {/* Map */}
      <div className="relative min-w-0 flex-1">
        {segments.error ? (
          <ErrorState
            error={segments.error}
            title="Could not load road segments"
            onRetry={() => void segments.refetch()}
          />
        ) : (
          <RiskMap
            segments={segments.data ?? []}
            zones={zones.data ?? []}
            cameras={cameras.data?.items ?? []}
            selectedSegmentId={selectedId}
            onSelectSegment={(id) => {
              setSelectedId(id);
              setProbe(null);
            }}
            onProbe={handleProbe}
            probePoint={probe}
          />
        )}

        {segments.data?.length === 0 ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="panel pointer-events-auto max-w-sm p-4 text-center">
              <p className="text-ink text-xs font-medium">No road segments defined</p>
              <p className="text-ink-muted mt-1.5 text-xs">
                Define segments so events can be attributed to them and risk zones computed.
                <code className="mono text-ink-subtle mt-1.5 block">
                  python scripts/seed_demo.py
                </code>
                seeds a demo corridor.
              </p>
            </div>
          </div>
        ) : null}

        {aggregate.data ? (
          <div className="panel absolute bottom-3 left-3 px-2.5 py-1.5">
            <p className="text-ink-muted text-2xs">
              Scored {aggregate.data.segments_scored} segments, built{" "}
              {aggregate.data.zones_created} risk zones.
            </p>
          </div>
        ) : null}
      </div>

      {/* Detail */}
      <aside className="border-line bg-surface w-[330px] shrink-0 overflow-y-auto border-l">
        {probe ? (
          <ProbePanel
            probe={probe}
            evaluation={evaluate}
            onClose={() => {
              setProbe(null);
              evaluate.reset();
            }}
          />
        ) : selectedId ? (
          <div>
            <div className="panel-header sticky top-0 z-10 bg-inherit">
              <h2 className="panel-title">Hotspot detail</h2>
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                aria-label="Close detail"
                className="text-ink-subtle hover:text-ink"
              >
                <Icon name="close" size={14} />
              </button>
            </div>
            <div className="p-3">
              <AsyncBoundary
                isLoading={detail.isLoading}
                error={detail.error}
                data={detail.data}
                onRetry={() => void detail.refetch()}
                emptyMessage="No detail for this segment."
              >
                {(data) => <SegmentDetailView detail={data} />}
              </AsyncBoundary>
            </div>
          </div>
        ) : (
          <div>
            <div className="panel-header">
              <h2 className="panel-title">Hotspots</h2>
            </div>
            <AsyncBoundary
              isLoading={segments.isLoading}
              error={segments.error}
              data={segments.data?.filter(
                (segment) => segment.risk_score !== null && segment.risk_score !== undefined,
              )}
              emptyMessage="No segment has been scored yet."
              emptyHint="Risk appears once events are attributed to a segment. Use Recompute after analysing footage."
              loadingVariant="rows"
            >
              {(scored) => (
                <ul className="divide-line-subtle divide-y">
                  {scored.map((segment) => (
                    <li key={segment.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(segment.id)}
                        className="hover:bg-surface-hover w-full px-3 py-2 text-left transition-colors"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-ink min-w-0 flex-1 truncate text-xs font-medium">
                            {segment.name}
                          </span>
                          <RiskBadge score={segment.risk_score ?? 0} showScore />
                        </div>
                        <p className="text-ink-subtle mt-0.5 text-2xs">
                          {segment.event_count} events · {segment.near_miss_count} near misses
                          {segment.peak_hour !== null && segment.peak_hour !== undefined
                            ? ` · peak ${String(segment.peak_hour).padStart(2, "0")}:00`
                            : ""}
                        </p>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </AsyncBoundary>
          </div>
        )}
      </aside>
    </div>
  );
}

/* --------------------------------------------------------------- sub-panels */

function SegmentDetailView({ detail }: { detail: SegmentDetail }) {
  const { segment } = detail;
  const presentation = segment.risk_level ? riskPresentation(segment.risk_level) : null;
  const maxHourly = Math.max(1, ...detail.risk_by_hour.map((point) => point.risk_score));

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-ink text-sm font-semibold">{segment.name}</h3>
        <p className="text-ink-subtle mt-0.5 text-2xs">
          {segment.road_name ?? "no road name"} · {segment.length_m.toFixed(0)} m
          {segment.lanes ? ` · ${segment.lanes} lanes` : ""}
          {segment.speed_limit_kmh ? ` · ${segment.speed_limit_kmh} km/h` : ""}
        </p>
      </div>

      {segment.risk_score !== null && segment.risk_score !== undefined && presentation ? (
        <div
          className="rounded-sm border p-3"
          style={{ borderColor: `${presentation.color}55`, backgroundColor: presentation.background }}
        >
          <div className="flex items-baseline justify-between">
            <span className="field-label mb-0">Risk score</span>
            <RiskBadge level={segment.risk_level!} />
          </div>
          <p className="metric mt-1 text-3xl leading-none" style={{ color: presentation.color }}>
            {Math.round(segment.risk_score)}
            <span className="text-ink-subtle ml-1 text-xs font-normal">/100</span>
          </p>
          <p className="text-ink-subtle mt-1 text-2xs">
            confidence {segment.risk_confidence ?? "—"}
            {segment.peak_hour !== null && segment.peak_hour !== undefined
              ? ` · peak ${String(segment.peak_hour).padStart(2, "0")}:00`
              : ""}
          </p>
          {segment.top_risk_factors.length > 0 ? (
            <ul className="mt-2.5 space-y-1">
              {segment.top_risk_factors.map((factor) => (
                <li key={factor} className="text-ink-muted flex items-start gap-1.5 text-xs">
                  <span className="bg-ink-subtle mt-1.5 size-1 shrink-0 rounded-full" />
                  {factor}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="text-ink-subtle text-xs">
          Not scored. No events have been attributed to this segment.
        </p>
      )}

      {detail.risk_by_hour.length > 0 ? (
        <div className="border-line border-t pt-3">
          <h4 className="field-label">Risk by hour</h4>
          <p className="text-ink-subtle mb-2 text-2xs">
            The same place is not equally dangerous all day.
          </p>
          <div className="flex h-24 items-end gap-px">
            {Array.from({ length: 24 }, (_, hour) => {
              const point = detail.risk_by_hour.find((entry) => entry.hour === hour);
              const height = point ? Math.max(2, (point.risk_score / maxHourly) * 100) : 1;
              return (
                <div
                  key={hour}
                  title={
                    point
                      ? `${String(hour).padStart(2, "0")}:00 — risk ${point.risk_score.toFixed(0)}, ${point.event_count} events`
                      : `${String(hour).padStart(2, "0")}:00 — no events`
                  }
                  style={{
                    height: `${height}%`,
                    backgroundColor: point
                      ? riskPresentation(point.risk_level).color
                      : "var(--color-line)",
                  }}
                  className="flex-1 rounded-t-[1px]"
                />
              );
            })}
          </div>
          <div className="text-ink-subtle mt-1 flex justify-between text-2xs">
            <span>00</span>
            <span>06</span>
            <span>12</span>
            <span>18</span>
            <span>23</span>
          </div>
        </div>
      ) : null}

      {Object.keys(detail.event_breakdown).length > 0 ? (
        <div className="border-line border-t pt-3">
          <h4 className="field-label">Event breakdown</h4>
          <ul className="space-y-1">
            {Object.entries(detail.event_breakdown)
              .sort((a, b) => b[1] - a[1])
              .map(([type, count]) => (
                <li key={type} className="flex items-center justify-between text-xs">
                  <span className="text-ink-muted">
                    {EVENT_LABELS[type as EventType] ?? type}
                  </span>
                  <span className="text-ink mono">{count}</span>
                </li>
              ))}
          </ul>
        </div>
      ) : null}

      {detail.cameras.length > 0 ? (
        <div className="border-line border-t pt-3">
          <h4 className="field-label">Cameras on this segment</h4>
          <ul className="space-y-1">
            {detail.cameras.map((camera) => (
              <li key={String(camera.id)} className="flex items-center justify-between text-xs">
                <span className="text-ink-muted truncate">{String(camera.name)}</span>
                <Badge tone="neutral">{String(camera.status).toLowerCase()}</Badge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {detail.recent_events.length > 0 ? (
        <div className="border-line border-t pt-3">
          <h4 className="field-label">Recent events</h4>
          <ul className="space-y-1">
            {detail.recent_events.map((event) => (
              <li key={String(event.id)} className="flex items-center justify-between gap-2 text-xs">
                <span className="text-ink-muted min-w-0 flex-1 truncate">
                  {EVENT_LABELS[String(event.event_type) as EventType] ?? String(event.event_type)}
                </span>
                <span className="text-ink-subtle mono shrink-0 text-2xs">
                  {formatTimestamp(String(event.timestamp ?? ""))}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function ProbePanel({
  probe,
  evaluation,
  onClose,
}: {
  probe: { latitude: number; longitude: number };
  evaluation: ReturnType<typeof useEvaluateAlert>;
  onClose: () => void;
}) {
  const result = evaluation.data;

  return (
    <div>
      <div className="panel-header sticky top-0 z-10 bg-inherit">
        <h2 className="panel-title">Alert engine probe</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close probe"
          className="text-ink-subtle hover:text-ink"
        >
          <Icon name="close" size={14} />
        </button>
      </div>

      <div className="space-y-3 p-3">
        <p className="text-ink-subtle mono text-2xs">
          {probe.latitude.toFixed(5)}, {probe.longitude.toFixed(5)}
        </p>
        <p className="text-ink-muted text-2xs leading-relaxed">
          What a driver at this point would be told. No heading is supplied here, so the direction
          gate is not applied — on a real device it is.
        </p>

        {evaluation.isPending ? (
          <p className="text-ink-subtle text-xs">Evaluating…</p>
        ) : evaluation.error ? (
          <ErrorState error={evaluation.error} title="Could not evaluate" />
        ) : result ? (
          <>
            <div className="border-line bg-surface-sunken rounded-sm border p-2.5">
              <span className="field-label">Matched road segment</span>
              <p className="text-ink text-xs">
                {result.current_segment_name ?? "none within 80 m"}
              </p>
            </div>

            {result.alert ? (
              <div className="border-risk-critical/45 bg-risk-critical-dim rounded-sm border p-3">
                <div className="flex items-center justify-between">
                  <Badge tone="critical">{result.alert.level.replace("_", " ")}</Badge>
                  <RiskBadge level={result.alert.risk_level} showScore score={result.alert.risk_score} />
                </div>
                <p className="text-ink mt-2 text-sm font-semibold">{result.alert.headline}</p>
                <p className="text-ink-muted mt-0.5 text-xs">{result.alert.detail}</p>

                {result.alert.factors.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {result.alert.factors.map((factor) => (
                      <li key={factor} className="text-ink-muted text-2xs">
                        · {factor}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {result.alert.recommendations.length > 0 ? (
                  <p className="text-accent mt-2 text-2xs">
                    {result.alert.recommendations.join(" · ")}
                  </p>
                ) : null}
                <p className="text-ink-subtle mt-2 text-2xs">
                  cooldown {result.alert.cooldown_seconds}s · origin {result.alert.origin}
                </p>
              </div>
            ) : (
              <div className="border-line bg-surface-sunken rounded-sm border p-2.5">
                <span className="field-label">No alert</span>
                <p className="text-ink-muted text-xs">
                  {result.suppressed_reason ?? "No risk zones within range."}
                </p>
              </div>
            )}

            <div>
              <h4 className="field-label">Nearby zones ({result.nearby.length})</h4>
              {result.nearby.length === 0 ? (
                <p className="text-ink-subtle text-2xs">None within 1.5 km.</p>
              ) : (
                <ul className="space-y-1.5">
                  {result.nearby.map((entry) => (
                    <li
                      key={entry.zone.id}
                      className="border-line bg-surface-sunken rounded-sm border p-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <RiskBadge level={entry.zone.risk_level} showScore score={entry.zone.risk_score} />
                        <span className="text-ink mono text-2xs">
                          {entry.distance_m.toFixed(0)} m
                        </span>
                      </div>
                      <p className="text-ink-subtle mt-1 text-2xs">
                        {entry.zone.road_name ?? "unnamed"} · bearing{" "}
                        {entry.bearing_deg.toFixed(0)}° ·{" "}
                        {entry.is_ahead ? "ahead" : "behind"}
                        {entry.eta_seconds ? ` · ${entry.eta_seconds.toFixed(0)}s` : ""}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

function FilterRow({
  label,
  colour,
  active,
  onClick,
}: {
  label: string;
  colour?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-sm px-1.5 py-1 text-left text-xs transition-colors ${
        active ? "bg-accent-dim text-accent" : "text-ink-muted hover:bg-surface-hover"
      }`}
    >
      {colour ? (
        <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: colour }} />
      ) : (
        <span className="size-2 shrink-0" />
      )}
      {label}
      {active ? <Icon name="check" size={11} className="ml-auto" /> : null}
    </button>
  );
}

function CountRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <dt className="text-ink-subtle">{label}</dt>
      <dd className="text-ink mono">{value}</dd>
    </div>
  );
}
