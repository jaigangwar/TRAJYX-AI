/** Upload footage and start an analysis run. */

import { useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { ErrorState } from "@/components/ui/StateBlock";
import { useAnalyseVideo, useUploadVideo, type VideoJob } from "@/features/analysis/api";
import { useCameras } from "@/features/dashboard/api";
import { useHealth } from "@/features/system/api";

const MAX_MIB = 512;

export function UploadPanel({ onUploaded }: { onUploaded: (job: VideoJob) => void }) {
  const cameras = useCameras();
  const health = useHealth();
  const upload = useUploadVideo();
  const analyse = useAnalyseVideo();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [cameraId, setCameraId] = useState("");
  const [simulate, setSimulate] = useState(false);
  const [speedLimit, setSpeedLimit] = useState("");
  const [dragging, setDragging] = useState(false);

  const demoAvailable = health.data?.capabilities.demo_mode ?? false;
  const busy = upload.isPending || analyse.isPending;
  const tooBig = file !== null && file.size > MAX_MIB * 1024 * 1024;

  const selectedCamera = cameras.data?.items.find((camera) => camera.id === cameraId);

  const submit = async () => {
    if (!file || tooBig) return;
    const job = await upload.mutateAsync({ file, cameraId: cameraId || undefined });
    await analyse.mutateAsync({
      jobId: job.id,
      options: {
        simulate,
        ...(speedLimit ? { speed_limit_kmh: Number(speedLimit) } : {}),
      },
    });
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
    onUploaded(job);
  };

  return (
    <div className="border-line border-b">
      <div className="panel-header">
        <h2 className="panel-title">Upload footage</h2>
      </div>

      <div className="space-y-2.5 p-3">
        {upload.error ? <ErrorState error={upload.error} title="Upload failed" /> : null}
        {analyse.error ? <ErrorState error={analyse.error} title="Could not start analysis" /> : null}

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const dropped = event.dataTransfer.files?.[0];
            if (dropped) setFile(dropped);
          }}
          className={`flex flex-col items-center justify-center rounded-sm border border-dashed px-3 py-5 text-center transition-colors ${
            dragging ? "border-accent bg-accent-dim" : "border-line-strong bg-surface-sunken"
          }`}
        >
          <Icon name="upload" size={18} className="text-ink-subtle" />
          {file ? (
            <>
              <p className="text-ink mt-2 max-w-full truncate text-xs font-medium">{file.name}</p>
              <p className={`mt-0.5 text-2xs ${tooBig ? "text-risk-critical" : "text-ink-subtle"}`}>
                {(file.size / (1024 * 1024)).toFixed(1)} MiB
                {tooBig ? ` — exceeds the ${MAX_MIB} MiB limit` : ""}
              </p>
            </>
          ) : (
            <>
              <p className="text-ink-muted mt-2 text-xs">Drop a video here</p>
              <p className="text-ink-subtle mt-0.5 text-2xs">mp4, mov, avi, mkv, webm</p>
            </>
          )}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="text-accent hover:text-accent-hover mt-2 text-2xs"
          >
            {file ? "Choose a different file" : "Browse"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm"
            className="hidden"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </div>

        <label className="block">
          <span className="field-label">Camera</span>
          <select
            value={cameraId}
            onChange={(event) => setCameraId(event.target.value)}
            className="border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none"
          >
            <option value="">Unassigned</option>
            {(cameras.data?.items ?? []).map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.name}
              </option>
            ))}
          </select>
        </label>

        {selectedCamera ? (
          <div className="border-line bg-surface-sunken rounded-sm border p-2">
            <p className="text-ink-subtle text-2xs">This camera can detect:</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(selectedCamera.capabilities).map(([key, enabled]) => (
                <Badge key={key} tone={enabled ? "low" : "offline"}>
                  {key.replace(/_/g, " ")}
                </Badge>
              ))}
            </div>
            <p className="text-ink-subtle mt-1.5 text-2xs leading-relaxed">
              Disabled checks report &ldquo;unable to determine&rdquo;, not &ldquo;no
              violations&rdquo;. Configure the camera geometry to enable them.
            </p>
          </div>
        ) : null}

        <label className="block">
          <span className="field-label">Speed limit (km/h)</span>
          <input
            type="text"
            value={speedLimit}
            placeholder="leave blank to skip overspeed"
            onChange={(event) => setSpeedLimit(event.target.value)}
            className="border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none"
          />
        </label>

        {demoAvailable ? (
          <label className="border-accent-line bg-accent-dim flex cursor-pointer items-start gap-2 rounded-sm border p-2">
            <input
              type="checkbox"
              checked={simulate}
              onChange={(event) => setSimulate(event.target.checked)}
              className="accent-accent mt-0.5 size-3.5"
            />
            <span>
              <span className="text-accent block text-xs font-medium">Simulate detection</span>
              <span className="text-ink-muted mt-0.5 block text-2xs leading-relaxed">
                Replays a scripted scenario instead of running the detector. Everything produced is
                labelled DEMO DATA and is never presented as measured.
              </span>
            </span>
          </label>
        ) : null}

        <Button
          variant="primary"
          className="w-full"
          loading={busy}
          disabled={!file || tooBig}
          onClick={() => void submit()}
        >
          Upload and analyse
        </Button>
      </div>
    </div>
  );
}
