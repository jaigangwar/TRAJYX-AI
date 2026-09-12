import { useState } from "react";

import { Badge, CameraStatusBadge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Icon } from "@/components/ui/Icon";
import { Panel } from "@/components/ui/Panel";
import { CameraForm } from "@/features/dashboard/CameraForm";
import { useCameras, useDeleteCamera, type Camera } from "@/features/dashboard/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { formatCoordinate, formatHeading, formatRelativeTime } from "@/lib/format";

export function CamerasPage() {
  const cameras = useCameras();
  const deleteCamera = useDeleteCamera();
  const [selected, setSelected] = useState<Camera | null>(null);
  const [creating, setCreating] = useState(false);

  usePageHeader(
    "Cameras",
    "Registry, geometry and analysis capability",
    <Button
      size="sm"
      variant="primary"
      icon={<Icon name="camera" size={13} />}
      onClick={() => {
        setSelected(null);
        setCreating(true);
      }}
    >
      Register camera
    </Button>,
  );

  const columns: Column<Camera>[] = [
    {
      key: "name",
      header: "Camera",
      sortValue: (row) => row.name,
      cell: (row) => <span className="text-ink font-medium">{row.name}</span>,
    },
    {
      key: "status",
      header: "Status",
      width: "90px",
      sortValue: (row) => row.status,
      cell: (row) => <CameraStatusBadge status={row.status} />,
    },
    {
      key: "road",
      header: "Road",
      sortValue: (row) => row.road_name ?? "",
      cell: (row) => row.road_name ?? "—",
    },
    {
      key: "location",
      header: "Location",
      cell: (row) => (
        <span className="mono">{formatCoordinate(row.location.latitude, row.location.longitude)}</span>
      ),
    },
    {
      key: "capabilities",
      header: "Detects",
      cell: (row) => <CapabilityChips camera={row} />,
    },
    {
      key: "risk",
      header: "Risk",
      width: "90px",
      align: "right",
      sortValue: (row) => row.current_risk_score ?? null,
      cell: (row) =>
        row.current_risk_score !== null && row.current_risk_score !== undefined ? (
          <RiskBadge score={row.current_risk_score} showScore />
        ) : (
          <span className="text-ink-subtle">—</span>
        ),
    },
    {
      key: "last_event",
      header: "Last event",
      width: "80px",
      align: "right",
      sortValue: (row) => row.last_event_at ?? null,
      cell: (row) => formatRelativeTime(row.last_event_at),
    },
  ];

  return (
    <div className="flex h-full min-h-0">
      <div className="min-w-0 flex-1 p-4">
        <Panel
          title="Registered cameras"
          meta={cameras.data ? `${cameras.data.items.length}` : undefined}
          flush
        >
          <DataTable
            columns={columns}
            rows={cameras.data?.items}
            rowKey={(row) => row.id}
            isLoading={cameras.isLoading}
            error={cameras.error}
            onRetry={() => void cameras.refetch()}
            emptyMessage="No cameras registered yet."
            emptyHint="Register a camera to define its location, lane directions and stop line. Those settings decide which safety checks the analysis can perform."
            onRowClick={(row) => {
              setCreating(false);
              setSelected(row);
            }}
            selectedKey={selected?.id ?? null}
            defaultSort="name"
            defaultDescending={false}
          />
        </Panel>
      </div>

      {creating || selected ? (
        <aside className="border-line bg-surface w-[400px] shrink-0 overflow-y-auto border-l">
          <div className="panel-header sticky top-0 z-10 bg-inherit">
            <h2 className="panel-title">{creating ? "Register camera" : "Camera detail"}</h2>
            <button
              type="button"
              onClick={() => {
                setCreating(false);
                setSelected(null);
              }}
              aria-label="Close panel"
              className="text-ink-subtle hover:text-ink"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
          <div className="p-3">
            <CameraForm
              key={selected?.id ?? "new"}
              camera={creating ? null : selected}
              onSaved={(camera) => {
                setCreating(false);
                setSelected(camera);
              }}
              onDelete={
                selected
                  ? async () => {
                      await deleteCamera.mutateAsync(selected.id);
                      setSelected(null);
                    }
                  : undefined
              }
            />
          </div>
        </aside>
      ) : null}
    </div>
  );
}

function CapabilityChips({ camera }: { camera: Camera }) {
  const { capabilities, lane_directions } = camera;
  const active = [
    capabilities.speed_estimation && "Speed",
    capabilities.wrong_way_detection && "Wrong way",
    capabilities.stop_line_violation && "Stop line",
    capabilities.red_light_violation && "Red light",
  ].filter((entry): entry is string => Boolean(entry));

  if (active.length === 0) {
    return (
      <span
        className="text-ink-subtle text-2xs"
        title="No geometry configured, so only detection and tracking apply to this camera."
      >
        detection only
      </span>
    );
  }

  return (
    <span className="flex flex-wrap items-center gap-1">
      {active.map((label) => (
        <Badge key={label} tone="accent">
          {label}
        </Badge>
      ))}
      {lane_directions.length > 0 ? (
        <span
          className="text-ink-subtle text-2xs"
          title={lane_directions
            .map((lane) => `Lane ${lane.lane_index}: ${formatHeading(lane.heading_deg)}`)
            .join("\n")}
        >
          {lane_directions.length} lanes
        </span>
      ) : null}
    </span>
  );
}
