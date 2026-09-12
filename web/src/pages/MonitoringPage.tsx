/** Live Monitoring: camera grid ordered so problems surface first. */

import { Link } from "react-router-dom";

import { Badge, CameraStatusBadge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { Panel } from "@/components/ui/Panel";
import { AsyncBoundary } from "@/components/ui/StateBlock";
import { useCameraGrid, type Camera } from "@/features/dashboard/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { formatRelativeTime } from "@/lib/format";
import { riskPresentation } from "@/lib/risk";

export function MonitoringPage() {
  const grid = useCameraGrid();

  usePageHeader(
    "Live Monitoring",
    "Camera status, current traffic level and risk",
    <Button
      size="sm"
      variant="ghost"
      icon={<Icon name="refresh" size={13} />}
      onClick={() => void grid.refetch()}
      loading={grid.isFetching}
    >
      Refresh
    </Button>,
  );

  return (
    <div className="p-4">
      <Panel
        title="Cameras"
        meta={grid.data ? `${grid.data.total} registered` : undefined}
        actions={
          <span className="text-ink-subtle text-2xs">
            Alerting cameras sort first, then by descending risk
          </span>
        }
      >
        <AsyncBoundary
          isLoading={grid.isLoading}
          error={grid.error}
          data={grid.data?.items}
          emptyMessage="No cameras registered."
          emptyHint="Register a camera to start monitoring it."
          onRetry={() => void grid.refetch()}
        >
          {(cameras) => (
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
              {cameras.map((camera) => (
                <CameraCard key={camera.id} camera={camera} />
              ))}
            </div>
          )}
        </AsyncBoundary>
      </Panel>
    </div>
  );
}

function CameraCard({ camera }: { camera: Camera }) {
  const risk = camera.current_risk_score;
  const presentation = camera.current_risk_level ? riskPresentation(camera.current_risk_level) : null;
  const alerting = camera.status === "ALERT";

  return (
    <Link
      to="/cameras"
      className={`border-line bg-surface-sunken hover:border-line-strong block rounded-sm border transition-colors ${
        alerting ? "border-risk-critical/60" : ""
      }`}
    >
      {/* Viewport placeholder. A live frame appears once streaming lands in
          phase 3; showing a stock image here would imply a feed exists. */}
      <div className="border-line bg-ground relative flex aspect-video items-center justify-center border-b">
        <Icon name="video" size={22} className="text-ink-subtle/40" />
        <span className="text-ink-subtle absolute bottom-1.5 left-2 text-2xs">
          No live frame · phase 3
        </span>
        {presentation ? (
          <span
            className="absolute top-0 left-0 h-full w-[3px]"
            style={{ backgroundColor: presentation.color }}
            aria-hidden="true"
          />
        ) : null}
      </div>

      <div className="p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-ink truncate text-xs font-medium">{camera.name}</p>
            <p className="text-ink-subtle truncate text-2xs">{camera.road_name ?? "no road set"}</p>
          </div>
          <CameraStatusBadge status={camera.status} />
        </div>

        <div className="border-line-subtle mt-2 flex items-center justify-between gap-2 border-t pt-2">
          <span className="text-ink-subtle text-2xs">
            {camera.last_seen_at ? `seen ${formatRelativeTime(camera.last_seen_at)}` : "never seen"}
          </span>
          {risk !== null && risk !== undefined ? (
            <RiskBadge score={risk} showScore />
          ) : (
            <Badge tone="offline" title="No analysis has run for this camera yet.">
              unscored
            </Badge>
          )}
        </div>
      </div>
    </Link>
  );
}
