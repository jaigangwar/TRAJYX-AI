/**
 * Video Analysis.
 *
 * Three panes: jobs on the left, annotated playback in the centre with an
 * event timeline beneath it, and the analysis readout on the right. Clicking
 * a timeline event seeks the video to that moment.
 */

import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge, JobStatusBadge, OriginBadge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Kpi } from "@/components/ui/Kpi";
import { Panel } from "@/components/ui/Panel";
import { AsyncBoundary, ErrorState } from "@/components/ui/StateBlock";
import { UploadPanel } from "@/features/analysis/UploadPanel";
import {
  mediaUrl,
  useAnalysis,
  useDeleteJob,
  useJob,
  useJobs,
  type TimelineEntry,
  type VideoAnalysis,
  type VideoJob,
} from "@/features/analysis/api";
import { useAuthedMedia } from "@/features/analysis/useAuthedMedia";
import { usePageHeader } from "@/hooks/usePageHeader";
import { EVENT_LABELS, formatRelativeTime, formatTimestamp } from "@/lib/format";
import { riskPresentation } from "@/lib/risk";
import type { EventType } from "@shared/domain";

const ConflictView3D = lazy(() =>
  import("@/features/analysis/ConflictView3D").then((module) => ({ default: module.ConflictView3D })),
);

export function AnalysisPage() {
  const jobs = useJobs();
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [replayMode, setReplayMode] = useState<"timeline" | "3d">("timeline");

  // Derived, not stored: with no explicit choice the newest job is shown, so
  // the page is never empty-looking when there is something to display. Doing
  // this in an effect would mean a synchronous setState during render.
  const selectedId = chosenId ?? jobs.data?.items[0]?.id ?? null;

  const job = useJob(selectedId);
  const analysis = useAnalysis(selectedId, job.data?.status === "COMPLETED");
  const returnToTimeline = useCallback(() => setReplayMode("timeline"), []);

  usePageHeader("Video Analysis", "Upload CCTV footage and review what the pipeline found");

  return (
    <div className="flex h-full min-h-0">
      <aside className="border-line bg-surface flex w-[290px] shrink-0 flex-col border-r">
        <UploadPanel onUploaded={(created) => setChosenId(created.id)} />
        <JobList
          jobs={jobs.data?.items}
          isLoading={jobs.isLoading}
          error={jobs.error}
          onRetry={() => void jobs.refetch()}
          selectedId={selectedId}
          onSelect={setChosenId}
        />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        {selectedId === null ? (
          <Panel title="Analysis">
            <p className="text-ink-muted text-xs">
              Upload footage to begin, or select a previous job.
            </p>
          </Panel>
        ) : (
          <>
            <Player job={job.data} analysis={analysis.data} />
            <div className="flex items-center gap-1 border-b border-line">
              <button
                type="button"
                aria-pressed={replayMode === "timeline"}
                onClick={() => setReplayMode("timeline")}
                className={`px-3 py-1.5 text-xs ${replayMode === "timeline" ? "border-b-2 border-accent text-accent" : "text-ink-muted hover:text-ink"}`}
              >2D event timeline</button>
              <button
                type="button"
                aria-pressed={replayMode === "3d"}
                disabled={!analysis.data?.camera_calibration}
                title={analysis.data?.calibration_note ?? "3D replay requires a matching camera calibration."}
                onClick={() => setReplayMode("3d")}
                className={`px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-45 ${replayMode === "3d" ? "border-b-2 border-accent text-accent" : "text-ink-muted hover:text-ink"}`}
              >3D conflict view</button>
            </div>
            {replayMode === "3d" && analysis.data ? (
              <Suspense fallback={<Panel><p className="text-ink-muted text-xs">Loading calibrated 3D replay…</p></Panel>}>
                <ConflictView3D analysis={analysis.data} onUnavailable={returnToTimeline} />
              </Suspense>
            ) : (
              <Timeline
                analysis={analysis.data}
                isLoading={analysis.isLoading}
                status={job.data?.status}
              />
            )}
          </>
        )}
      </div>

      {selectedId ? (
        <aside className="border-line bg-surface w-[340px] shrink-0 overflow-y-auto border-l">
          <ReadoutPanel job={job.data} analysis={analysis} />
        </aside>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ job list */

function JobList({
  jobs,
  isLoading,
  error,
  onRetry,
  selectedId,
  onSelect,
}: {
  jobs: VideoJob[] | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const deleteJob = useDeleteJob();

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="panel-header sticky top-0 z-10 bg-inherit">
        <h2 className="panel-title">Jobs</h2>
        <span className="text-ink-subtle text-2xs">{jobs?.length ?? 0}</span>
      </div>

      <AsyncBoundary
        isLoading={isLoading}
        error={error}
        data={jobs}
        onRetry={onRetry}
        emptyMessage="No analysis jobs yet."
        emptyHint="Upload a video to create one."
        loadingVariant="rows"
      >
        {(items) => (
          <ul className="divide-line-subtle divide-y">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelect(item.id)}
                  className={`w-full px-3 py-2 text-left transition-colors ${
                    selectedId === item.id ? "bg-accent-dim" : "hover:bg-surface-hover"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-ink min-w-0 flex-1 truncate text-xs font-medium">
                      {item.filename}
                    </span>
                    <JobStatusBadge status={item.status} />
                  </div>
                  <div className="mt-1 flex items-center gap-1.5">
                    <span className="text-ink-subtle text-2xs">
                      {formatRelativeTime(item.created_at)} ago
                    </span>
                    {item.camera_name ? (
                      <span className="text-ink-subtle truncate text-2xs">
                        · {item.camera_name}
                      </span>
                    ) : null}
                    <OriginBadge origin={item.origin} />
                  </div>
                  {item.progress && item.status === "PROCESSING" ? (
                    <div className="mt-1.5">
                      <div className="bg-line h-0.5 w-full overflow-hidden rounded-full">
                        <div
                          className="bg-accent h-full transition-[width]"
                          style={{ width: `${item.progress.percent}%` }}
                        />
                      </div>
                      <p className="text-ink-subtle mt-1 text-2xs">
                        {item.progress.stage} · {item.progress.percent}% ·{" "}
                        {item.progress.detections} detections
                      </p>
                    </div>
                  ) : null}
                  {item.error ? (
                    <p className="text-risk-critical mt-1 text-2xs">{item.error}</p>
                  ) : null}
                </button>
                {selectedId === item.id ? (
                  <div className="px-3 pb-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      loading={deleteJob.isPending}
                      onClick={() => deleteJob.mutate(item.id)}
                    >
                      Delete job
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </AsyncBoundary>
    </div>
  );
}

/* -------------------------------------------------------------------- player */

const seekRequest = { current: null as ((seconds: number) => void) | null };

function Player({ job, analysis }: { job: VideoJob | undefined; analysis: VideoAnalysis | undefined }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hasAnnotated = job?.status === "COMPLETED" && Boolean(job.annotated_key);
  const media = useAuthedMedia(job && hasAnnotated ? mediaUrl(job.id, "annotated") : null);

  useEffect(() => {
    seekRequest.current = (seconds: number) => {
      if (videoRef.current) {
        videoRef.current.currentTime = seconds;
        void videoRef.current.play();
      }
    };
    return () => {
      seekRequest.current = null;
    };
  }, []);

  return (
    <Panel
      title="Annotated playback"
      meta={
        analysis
          ? `${analysis.frame_width}x${analysis.frame_height} · ${analysis.frame_rate.toFixed(0)}fps · every ${analysis.frame_stride} frame${analysis.frame_stride > 1 ? "s" : ""}`
          : undefined
      }
      actions={job ? <OriginBadge origin={job.origin} /> : undefined}
      flush
    >
      <div className="bg-surface-sunken relative flex aspect-video items-center justify-center">
        {job?.status === "PROCESSING" || job?.status === "QUEUED" ? (
          <div className="text-center">
            <p className="text-ink-muted text-xs">
              {job.progress?.stage ?? "queued"} · {job.progress?.percent ?? 0}%
            </p>
            <p className="text-ink-subtle mt-1 text-2xs">
              {job.progress?.frames_processed ?? 0} frames · {job.progress?.detections ?? 0}{" "}
              detections · {job.progress?.active_tracks ?? 0} active tracks
            </p>
          </div>
        ) : job?.status === "FAILED" ? (
          <div className="max-w-md px-6 text-center">
            <Badge tone="critical">Failed</Badge>
            <p className="text-ink-muted mt-2 text-xs">{job.error ?? "Analysis failed."}</p>
          </div>
        ) : media.isLoading ? (
          <p className="text-ink-subtle text-xs">Loading video…</p>
        ) : media.error ? (
          <ErrorState error={media.error} title="Could not load the annotated video" />
        ) : media.url ? (
          <video
            ref={videoRef}
            src={media.url}
            controls
            className="h-full w-full"
            // Autoplay is deliberately off: an operator reviewing evidence
            // should control playback.
          />
        ) : (
          <p className="text-ink-subtle text-xs">
            No annotated video. Run analysis to produce one.
          </p>
        )}
      </div>
    </Panel>
  );
}

/* ------------------------------------------------------------------ timeline */

function Timeline({
  analysis,
  isLoading,
  status,
}: {
  analysis: VideoAnalysis | undefined;
  isLoading: boolean;
  status: string | undefined;
}) {
  const grouped = useMemo(() => {
    if (!analysis) return [];
    return analysis.timeline;
  }, [analysis]);

  return (
    <Panel title="Event timeline" meta={analysis ? `${grouped.length} events` : undefined} flush>
      <AsyncBoundary
        isLoading={isLoading}
        error={null}
        data={status === "COMPLETED" ? grouped : undefined}
        emptyMessage={
          status === "COMPLETED" ? "No safety events detected in this footage." : "Not analysed yet."
        }
        emptyHint={
          status === "COMPLETED"
            ? "Check the readout for which detectors could not run — an absent result is not a negative one."
            : "Run analysis to produce a timeline."
        }
        loadingVariant="rows"
      >
        {(entries) => (
          <>
            {analysis ? <TimelineStrip entries={entries} duration={analysis.duration_s} /> : null}
            <ul className="divide-line-subtle max-h-56 divide-y overflow-y-auto">
              {entries.map((entry, index) => (
                <li key={`${entry.timestamp_s}-${entry.event_type}-${index}`}>
                  <button
                    type="button"
                    onClick={() => seekRequest.current?.(entry.timestamp_s)}
                    className="hover:bg-surface-hover flex w-full items-center gap-3 px-3 py-1.5 text-left transition-colors"
                  >
                    <span className="text-accent mono w-14 shrink-0 text-2xs">
                      {formatClock(entry.timestamp_s)}
                    </span>
                    <span className="text-ink min-w-0 flex-1 truncate text-xs">
                      {EVENT_LABELS[entry.event_type as EventType] ?? entry.label}
                    </span>
                    {entry.track_ids.length ? (
                      <span className="text-ink-subtle mono shrink-0 text-2xs">
                        #{entry.track_ids.join(", #")}
                      </span>
                    ) : null}
                    {entry.risk_score !== null && entry.risk_score !== undefined ? (
                      <RiskBadge score={entry.risk_score} showScore />
                    ) : (
                      <Badge tone={severityTone(entry.severity)}>{entry.severity.toLowerCase()}</Badge>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </AsyncBoundary>
    </Panel>
  );
}

/** A scrubber showing where events fall in the clip. */
function TimelineStrip({ entries, duration }: { entries: TimelineEntry[]; duration: number }) {
  if (duration <= 0) return null;

  return (
    <div className="border-line bg-surface-sunken relative h-8 border-b">
      {entries.map((entry, index) => {
        const left = Math.min(100, (entry.timestamp_s / duration) * 100);
        const colour =
          entry.risk_score !== null && entry.risk_score !== undefined
            ? riskPresentation(
                entry.risk_score >= 76
                  ? "CRITICAL"
                  : entry.risk_score >= 51
                    ? "HIGH"
                    : entry.risk_score >= 26
                      ? "MODERATE"
                      : "LOW",
              ).color
            : severityColour(entry.severity);

        return (
          <button
            key={`${entry.timestamp_s}-${index}`}
            type="button"
            title={`${formatClock(entry.timestamp_s)} — ${entry.label}`}
            onClick={() => seekRequest.current?.(entry.timestamp_s)}
            style={{ left: `${left}%`, backgroundColor: colour }}
            className="absolute top-1.5 h-5 w-[3px] -translate-x-1/2 rounded-full transition-transform hover:scale-y-125"
          />
        );
      })}
      <span className="text-ink-subtle mono absolute right-1.5 bottom-0 text-2xs">
        {formatClock(duration)}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------- readout */

function ReadoutPanel({
  job,
  analysis,
}: {
  job: VideoJob | undefined;
  analysis: ReturnType<typeof useAnalysis>;
}) {
  return (
    <div>
      <div className="panel-header sticky top-0 z-10 bg-inherit">
        <h2 className="panel-title">Analysis readout</h2>
        {job ? <JobStatusBadge status={job.status} /> : null}
      </div>

      <div className="p-3">
        <AsyncBoundary
          isLoading={analysis.isLoading}
          error={analysis.error}
          data={job?.status === "COMPLETED" ? analysis.data : undefined}
          emptyMessage="Not analysed yet."
          emptyHint="Run analysis from the upload panel to produce a readout."
          onRetry={() => void analysis.refetch()}
        >
          {(data) => <Readout analysis={data} />}
        </AsyncBoundary>
      </div>
    </div>
  );
}

function Readout({ analysis }: { analysis: VideoAnalysis }) {
  return (
    <div className="space-y-4">
      {analysis.risk_score !== null && analysis.risk_score !== undefined ? (
        <div
          className="rounded-sm border p-3"
          style={{
            borderColor: `${riskPresentation(analysis.risk_level ?? "LOW").color}66`,
            backgroundColor: riskPresentation(analysis.risk_level ?? "LOW").background,
          }}
        >
          <div className="flex items-baseline justify-between">
            <span className="field-label mb-0">Collision risk</span>
            <RiskBadge level={analysis.risk_level ?? "LOW"} />
          </div>
          <p
            className="metric mt-1 text-3xl leading-none"
            style={{ color: riskPresentation(analysis.risk_level ?? "LOW").color }}
          >
            {Math.round(analysis.risk_score)}
            <span className="text-ink-subtle ml-1 text-xs font-normal">/100</span>
          </p>
          <p className="text-ink-subtle mt-1 text-2xs">
            confidence {analysis.risk_confidence ?? "—"} · estimated, not measured
          </p>

          {analysis.top_risk_factors.length > 0 ? (
            <ul className="mt-2.5 space-y-1">
              {analysis.top_risk_factors.map((factor) => (
                <li key={factor} className="text-ink-muted flex items-start gap-1.5 text-xs">
                  <span className="bg-ink-subtle mt-1.5 size-1 shrink-0 rounded-full" />
                  {factor}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Kpi label="Vehicles" value={analysis.vehicle_count} />
        <Kpi label="Pedestrians" value={analysis.pedestrian_count} />
        <Kpi label="Violations" value={analysis.violation_count} tone={analysis.violation_count ? "moderate" : "neutral"} />
        <Kpi label="Near misses" value={analysis.near_miss_count} tone={analysis.near_miss_count ? "high" : "neutral"} />
        <Kpi label="Behaviour events" value={analysis.behaviour_count} />
        <Kpi
          label="Min est. TTC"
          value={analysis.minimum_ttc_s ?? null}
          unit="s"
          note={analysis.minimum_ttc_s !== null ? "estimated" : undefined}
        />
      </div>

      <Section title="Traffic composition">
        {Object.keys(analysis.class_counts).length === 0 ? (
          <p className="text-ink-subtle text-2xs">No objects detected.</p>
        ) : (
          <ul className="space-y-1">
            {Object.entries(analysis.class_counts)
              .sort((a, b) => b[1] - a[1])
              .map(([name, count]) => (
                <li key={name} className="flex items-center justify-between text-xs">
                  <span className="text-ink-muted capitalize">
                    {name.toLowerCase().replace(/_/g, " ")}
                  </span>
                  <span className="text-ink mono">{count}</span>
                </li>
              ))}
          </ul>
        )}
        <p className="text-ink-subtle mt-1.5 text-2xs">
          Detections across analysed frames. {analysis.track_count} unique objects were tracked.
        </p>
      </Section>

      <Section title={`Tracks (${analysis.tracks.length})`}>
        <ul className="max-h-48 space-y-1 overflow-y-auto">
          {analysis.tracks.map((track) => (
            <li key={track.track_id} className="flex items-center gap-2 text-xs">
              <span className="text-accent mono w-8 shrink-0">#{track.track_id}</span>
              <span className="text-ink-muted min-w-0 flex-1 truncate capitalize">
                {track.vehicle_class.toLowerCase().replace(/_/g, " ")}
              </span>
              <span className="text-ink-subtle mono shrink-0 text-2xs">
                {track.mean_speed_kmh !== null && track.mean_speed_kmh !== undefined
                  ? `~${track.mean_speed_kmh.toFixed(0)}km/h`
                  : "no speed"}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      {analysis.unavailable_checks.length > 0 ? (
        <Section title="Checks that could not run">
          <p className="text-ink-subtle mb-2 text-2xs leading-relaxed">
            These are not negative results. An absent check means the system could not determine
            the answer, which is different from determining there was nothing to report.
          </p>
          <ul className="space-y-2">
            {analysis.unavailable_checks.map((check) => (
              <li key={check.name}>
                <Badge tone="offline">{check.name.replace(/_/g, " ")}</Badge>
                <p className="text-ink-subtle mt-1 text-2xs leading-relaxed">{check.reason}</p>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title="Run detail">
        <dl className="space-y-1.5">
          <Row label="Detector" value={`${analysis.detector_name} ${analysis.detector_version}`} />
          <Row label="Tracker" value={analysis.tracker_name} />
          <Row label="Frames analysed" value={`${analysis.frames_analysed} of ${analysis.frame_count}`} />
          <Row label="Detections" value={String(analysis.detection_count)} />
          <Row
            label="Inference"
            value={
              analysis.inference_ms_per_frame !== null && analysis.inference_ms_per_frame !== undefined
                ? `${analysis.inference_ms_per_frame} ms/frame`
                : "—"
            }
          />
          <Row label="Wall time" value={`${analysis.wall_seconds}s`} />
          <Row label="Duration" value={`${analysis.duration_s.toFixed(1)}s`} />
          <Row label="Completed" value={formatTimestamp(analysis.created_at)} />
        </dl>
        {Object.keys(analysis.unmapped_labels).length > 0 ? (
          <div className="border-risk-moderate/35 bg-risk-moderate-dim mt-2 rounded-sm border p-2">
            <p className="text-risk-moderate text-2xs font-semibold">Unmapped detector labels</p>
            <p className="text-ink-muted mt-1 text-2xs">
              {Object.entries(analysis.unmapped_labels)
                .map(([name, count]) => `${name} (${count})`)
                .join(", ")}
              . A rise here means the model and the class mapping have drifted apart.
            </p>
          </div>
        ) : null}
      </Section>
    </div>
  );
}

/* ------------------------------------------------------------------ helpers */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-line border-t pt-3">
      <h3 className="field-label">{title}</h3>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-ink-subtle text-2xs">{label}</dt>
      <dd className="text-ink truncate text-xs">{value}</dd>
    </div>
  );
}

function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function severityTone(severity: string) {
  if (severity === "CRITICAL") return "critical" as const;
  if (severity === "MAJOR") return "high" as const;
  if (severity === "MINOR") return "moderate" as const;
  return "neutral" as const;
}

function severityColour(severity: string): string {
  if (severity === "CRITICAL") return "var(--color-risk-critical)";
  if (severity === "MAJOR") return "var(--color-risk-high)";
  if (severity === "MINOR") return "var(--color-risk-moderate)";
  return "var(--color-info)";
}
