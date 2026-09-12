/**
 * Shared event page.
 *
 * Violations, near misses and incidents are the same table with different
 * preset filters, because they are the same record shape. Keeping them as one
 * component is what stops the three drifting apart.
 */

import { useMemo, useState } from "react";

import { Badge, OriginBadge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Icon } from "@/components/ui/Icon";
import { Panel } from "@/components/ui/Panel";
import {
  useCameras,
  useEvents,
  useReviewEvent,
  type EventFilters,
  type SafetyEvent,
} from "@/features/dashboard/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { EVENT_LABELS, formatConfidence, formatTimestamp } from "@/lib/format";
import { TTC_PRESENTATION } from "@/lib/risk";
import { EVENTTYPE_VALUES, REPORTSTATUS_VALUES, type TtcBand } from "@shared/domain";

interface EventsPageProps {
  title: string;
  subtitle: string;
  /** Filters the page is locked to. */
  preset: EventFilters;
  emptyMessage: string;
  emptyHint: string;
  /** Show the estimated-TTC column (near misses only). */
  showTtc?: boolean;
}

export function EventsPage({
  title,
  subtitle,
  preset,
  emptyMessage,
  emptyHint,
  showTtc = false,
}: EventsPageProps) {
  const [eventType, setEventType] = useState("");
  const [cameraId, setCameraId] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [measuredOnly, setMeasuredOnly] = useState(false);
  const [selected, setSelected] = useState<SafetyEvent | null>(null);

  const filters = useMemo<EventFilters>(
    () => ({
      ...preset,
      ...(eventType ? { event_type: eventType } : {}),
      ...(cameraId ? { camera_id: cameraId } : {}),
      ...(reviewStatus ? { review_status: reviewStatus } : {}),
      ...(measuredOnly ? { origin: "MEASURED" } : {}),
      limit: 100,
    }),
    [preset, eventType, cameraId, reviewStatus, measuredOnly],
  );

  const events = useEvents(filters);
  const cameras = useCameras();
  const review = useReviewEvent();

  usePageHeader(
    title,
    subtitle,
    <Button
      size="sm"
      variant="ghost"
      icon={<Icon name="refresh" size={13} />}
      onClick={() => void events.refetch()}
      loading={events.isFetching}
    >
      Refresh
    </Button>,
  );

  const columns: Column<SafetyEvent>[] = [
    {
      key: "timestamp",
      header: "Time",
      width: "120px",
      sortValue: (row) => row.timestamp,
      cell: (row) => <span className="mono">{formatTimestamp(row.timestamp)}</span>,
    },
    {
      key: "event_type",
      header: "Event",
      sortValue: (row) => row.event_type,
      cell: (row) => (
        <span className="text-ink font-medium">{EVENT_LABELS[row.event_type]}</span>
      ),
    },
    {
      key: "camera",
      header: "Camera",
      sortValue: (row) => row.camera_name ?? "",
      cell: (row) => row.camera_name ?? <span className="text-ink-subtle">driver report</span>,
    },
    {
      key: "tracks",
      header: "Tracks",
      width: "90px",
      cell: (row) =>
        row.track_ids.length > 0 ? (
          <span className="mono">#{row.track_ids.join(", #")}</span>
        ) : (
          <span className="text-ink-subtle">—</span>
        ),
    },
    ...(showTtc
      ? [
          {
            key: "ttc",
            header: "Est. TTC",
            width: "100px",
            align: "right" as const,
            sortValue: (row: SafetyEvent) => ttcSeconds(row) ?? null,
            cell: (row: SafetyEvent) => <TtcCell event={row} />,
          },
        ]
      : []),
    {
      key: "confidence",
      header: "Conf.",
      width: "70px",
      align: "right",
      sortValue: (row) => row.confidence ?? null,
      cell: (row) => formatConfidence(row.confidence),
    },
    {
      key: "risk",
      header: "Risk",
      width: "100px",
      align: "right",
      sortValue: (row) => row.risk_score ?? null,
      cell: (row) =>
        row.risk_score !== null && row.risk_score !== undefined ? (
          <RiskBadge score={row.risk_score} showScore />
        ) : (
          <span className="text-ink-subtle">—</span>
        ),
    },
    {
      key: "origin",
      header: "Origin",
      width: "90px",
      cell: (row) => <OriginBadge origin={row.origin} />,
    },
    {
      key: "status",
      header: "Review",
      width: "90px",
      sortValue: (row) => row.review_status ?? "",
      cell: (row) =>
        row.review_status ? (
          <Badge tone={reviewTone(row.review_status)}>{row.review_status.toLowerCase()}</Badge>
        ) : (
          <span className="text-ink-subtle text-2xs">n/a</span>
        ),
    },
  ];

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col gap-3 p-4">
        <Panel title="Filters">
          <div className="flex flex-wrap items-end gap-3">
            {!preset.event_type ? (
              <FilterSelect
                label="Event type"
                value={eventType}
                onChange={setEventType}
                options={EVENTTYPE_VALUES.map((value) => ({
                  value,
                  label: EVENT_LABELS[value],
                }))}
              />
            ) : null}
            <FilterSelect
              label="Camera"
              value={cameraId}
              onChange={setCameraId}
              options={(cameras.data?.items ?? []).map((camera) => ({
                value: camera.id,
                label: camera.name,
              }))}
            />
            <FilterSelect
              label="Review status"
              value={reviewStatus}
              onChange={setReviewStatus}
              options={REPORTSTATUS_VALUES.map((value) => ({
                value,
                label: value.toLowerCase(),
              }))}
            />
            <label className="text-ink-muted flex h-7 cursor-pointer items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={measuredOnly}
                onChange={(event) => setMeasuredOnly(event.target.checked)}
                className="accent-accent size-3.5"
              />
              Measured only
            </label>
            {eventType || cameraId || reviewStatus || measuredOnly ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEventType("");
                  setCameraId("");
                  setReviewStatus("");
                  setMeasuredOnly(false);
                }}
              >
                Clear
              </Button>
            ) : null}
          </div>
        </Panel>

        <Panel
          title="Events"
          meta={events.data ? `${events.data.items.length}` : undefined}
          flush
          className="min-h-0 flex-1"
          scroll
        >
          <DataTable
            columns={columns}
            rows={events.data?.items}
            rowKey={(row) => row.id}
            isLoading={events.isLoading}
            error={events.error}
            onRetry={() => void events.refetch()}
            emptyMessage={emptyMessage}
            emptyHint={emptyHint}
            onRowClick={setSelected}
            selectedKey={selected?.id ?? null}
            defaultSort="timestamp"
          />
        </Panel>
      </div>

      {selected ? (
        <aside className="border-line bg-surface w-[360px] shrink-0 overflow-y-auto border-l">
          <div className="panel-header sticky top-0 bg-inherit">
            <h2 className="panel-title">Event detail</h2>
            <button
              type="button"
              onClick={() => setSelected(null)}
              aria-label="Close detail"
              className="text-ink-subtle hover:text-ink"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
          <EventDetail
            event={selected}
            onReview={async (status) => {
              const updated = await review.mutateAsync({ id: selected.id, status });
              setSelected(updated);
            }}
            reviewing={review.isPending}
          />
        </aside>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------- detail */

function EventDetail({
  event,
  onReview,
  reviewing,
}: {
  event: SafetyEvent;
  onReview: (status: string) => Promise<void>;
  reviewing: boolean;
}) {
  const detailEntries = Object.entries(event.details);

  return (
    <div className="space-y-4 p-3">
      <div>
        <h3 className="text-ink text-sm font-semibold">{EVENT_LABELS[event.event_type]}</h3>
        <p className="text-ink-subtle mt-0.5 text-2xs">{formatTimestamp(event.timestamp)}</p>
        <div className="mt-2 flex flex-wrap gap-1">
          <Badge tone="neutral">{event.category.toLowerCase()}</Badge>
          <Badge tone="neutral">{event.severity.toLowerCase()}</Badge>
          <OriginBadge origin={event.origin} />
        </div>
      </div>

      <dl className="space-y-2">
        <Row label="Camera" value={event.camera_name ?? "—"} />
        <Row label="Road segment" value={event.road_segment_id ?? "not matched"} />
        <Row
          label="Location"
          value={
            event.location
              ? `${event.location.latitude.toFixed(5)}, ${event.location.longitude.toFixed(5)}`
              : "—"
          }
          mono
        />
        <Row label="Confidence" value={formatConfidence(event.confidence)} />
        <Row
          label="Risk score"
          value={event.risk_score !== null && event.risk_score !== undefined ? `${Math.round(event.risk_score)} / 100` : "not scored"}
        />
        <Row label="Tracks" value={event.track_ids.length ? `#${event.track_ids.join(", #")}` : "—"} mono />
        <Row label="Model" value={event.model_version ?? "—"} mono />
        <Row label="Frame" value={event.frame_index !== null && event.frame_index !== undefined ? String(event.frame_index) : "—"} mono />
      </dl>

      {detailEntries.length > 0 ? (
        <div>
          <h4 className="field-label">Detection detail</h4>
          <dl className="space-y-1.5">
            {detailEntries.map(([key, value]) => (
              <Row key={key} label={key.replace(/_/g, " ")} value={String(value)} />
            ))}
          </dl>
        </div>
      ) : null}

      <div>
        <h4 className="field-label">Evidence</h4>
        {event.evidence_key ? (
          <p className="text-ink-muted mono text-2xs break-all">{event.evidence_key}</p>
        ) : (
          <p className="text-ink-subtle text-2xs">
            No evidence frame stored. Evidence capture lands with the detection pipeline in phase 4.
          </p>
        )}
      </div>

      {event.review_status ? (
        <div className="border-line border-t pt-3">
          <h4 className="field-label">Operator review</h4>
          <p className="text-ink-subtle mb-2 text-2xs">
            Confirmations become the ground-truth signal the risk model trains on.
          </p>
          <div className="flex gap-1.5">
            <Button
              size="sm"
              variant={event.review_status === "CONFIRMED" ? "primary" : "secondary"}
              loading={reviewing}
              onClick={() => void onReview("CONFIRMED")}
            >
              Confirm
            </Button>
            <Button
              size="sm"
              variant={event.review_status === "REJECTED" ? "danger" : "secondary"}
              loading={reviewing}
              onClick={() => void onReview("REJECTED")}
            >
              Reject
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-ink-subtle shrink-0 text-2xs capitalize">{label}</dt>
      <dd className={`text-ink text-right text-xs ${mono ? "mono" : ""}`}>{value}</dd>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="border-line bg-surface-sunken text-ink focus:border-accent h-7 min-w-[150px] rounded-sm border px-2 text-xs outline-none"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/* ------------------------------------------------------------------ helpers */

function ttcSeconds(event: SafetyEvent): number | undefined {
  const value = event.details.estimated_ttc_seconds;
  return typeof value === "number" ? value : undefined;
}

function TtcCell({ event }: { event: SafetyEvent }) {
  const seconds = ttcSeconds(event);
  const band = event.details.ttc_band as TtcBand | undefined;

  if (seconds === undefined) return <span className="text-ink-subtle">—</span>;

  return (
    <span
      className="mono"
      style={band ? { color: TTC_PRESENTATION[band].color } : undefined}
      title="Estimated time to collision. An estimate, never a measurement."
    >
      {seconds.toFixed(1)}s
    </span>
  );
}

function reviewTone(status: string) {
  if (status === "CONFIRMED") return "critical" as const;
  if (status === "REJECTED") return "offline" as const;
  if (status === "REVIEWING") return "info" as const;
  return "neutral" as const;
}
