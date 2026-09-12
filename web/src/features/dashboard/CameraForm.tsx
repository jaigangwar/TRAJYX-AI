/** Camera create/edit form. Geometry fields gate what the analysis may conclude. */

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { ErrorState } from "@/components/ui/StateBlock";
import { useCreateCamera, useUpdateCamera, type Camera } from "@/features/dashboard/api";
import { formatTimestamp } from "@/lib/format";
import { CAMERASTATUS_VALUES, SIGNALSTATE_VALUES } from "@shared/domain";

interface CameraFormProps {
  camera: Camera | null;
  onSaved: (camera: Camera) => void;
  onDelete?: () => Promise<void>;
}

interface FormState {
  name: string;
  latitude: string;
  longitude: string;
  road_name: string;
  description: string;
  stream_url: string;
  frame_width: string;
  frame_height: string;
  frame_rate: string;
  status: string;
  signal_state: string;
  metres_per_pixel: string;
  reference_y: string;
  stop_line: { x1: string; y1: string; x2: string; y2: string };
  lanes: { lane_index: string; heading_deg: string; label: string }[];
}

function initialState(camera: Camera | null): FormState {
  return {
    name: camera?.name ?? "",
    latitude: camera ? String(camera.location.latitude) : "",
    longitude: camera ? String(camera.location.longitude) : "",
    road_name: camera?.road_name ?? "",
    description: camera?.description ?? "",
    stream_url: camera?.stream_url ?? "",
    frame_width: camera?.frame_width ? String(camera.frame_width) : "",
    frame_height: camera?.frame_height ? String(camera.frame_height) : "",
    frame_rate: camera?.frame_rate ? String(camera.frame_rate) : "",
    status: camera?.status ?? "OFFLINE",
    signal_state: camera?.signal_state ?? "UNKNOWN",
    metres_per_pixel: camera?.calibration
      ? String(camera.calibration.metres_per_pixel_at_reference)
      : "",
    reference_y: camera?.calibration ? String(camera.calibration.reference_y) : "",
    stop_line: camera?.stop_line
      ? {
          x1: String(camera.stop_line.start.x),
          y1: String(camera.stop_line.start.y),
          x2: String(camera.stop_line.end.x),
          y2: String(camera.stop_line.end.y),
        }
      : { x1: "", y1: "", x2: "", y2: "" },
    lanes:
      camera?.lane_directions.map((lane) => ({
        lane_index: String(lane.lane_index),
        heading_deg: String(lane.heading_deg),
        label: lane.label ?? "",
      })) ?? [],
  };
}

const numberOrNull = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
};

export function CameraForm({ camera, onSaved, onDelete }: CameraFormProps) {
  const [form, setForm] = useState<FormState>(() => initialState(camera));
  const [deleting, setDeleting] = useState(false);
  const create = useCreateCamera();
  const update = useUpdateCamera();

  const isNew = camera === null;
  const pending = create.isPending || update.isPending;
  const error = create.error ?? update.error;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const buildPayload = () => {
    const latitude = numberOrNull(form.latitude);
    const longitude = numberOrNull(form.longitude);
    const mpp = numberOrNull(form.metres_per_pixel);
    const referenceY = numberOrNull(form.reference_y);

    const stopLineValues = [
      numberOrNull(form.stop_line.x1),
      numberOrNull(form.stop_line.y1),
      numberOrNull(form.stop_line.x2),
      numberOrNull(form.stop_line.y2),
    ];
    const hasStopLine = stopLineValues.every((value) => value !== null);

    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      location: { latitude: latitude ?? 0, longitude: longitude ?? 0 },
      road_name: form.road_name.trim() || null,
      description: form.description.trim() || null,
      stream_url: form.stream_url.trim() || null,
      frame_width: numberOrNull(form.frame_width),
      frame_height: numberOrNull(form.frame_height),
      frame_rate: numberOrNull(form.frame_rate),
      signal_state: form.signal_state,
      stop_line: hasStopLine
        ? {
            start: { x: stopLineValues[0], y: stopLineValues[1] },
            end: { x: stopLineValues[2], y: stopLineValues[3] },
          }
        : null,
      calibration:
        mpp !== null && referenceY !== null
          ? { metres_per_pixel_at_reference: mpp, reference_y: referenceY }
          : null,
      lane_directions: form.lanes
        .map((lane) => ({
          lane_index: numberOrNull(lane.lane_index),
          heading_deg: numberOrNull(lane.heading_deg),
          label: lane.label.trim() || null,
        }))
        .filter(
          (lane): lane is { lane_index: number; heading_deg: number; label: string | null } =>
            lane.lane_index !== null && lane.heading_deg !== null,
        ),
    };

    if (!isNew) payload.status = form.status;
    return payload;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload = buildPayload();
    const saved = isNew
      ? await create.mutateAsync(payload)
      : await update.mutateAsync({ id: camera.id, body: payload });
    onSaved(saved);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error ? <ErrorState error={error} title="Could not save the camera" /> : null}

      <Section title="Identity">
        <Field label="Name" required>
          <Input value={form.name} onChange={(value) => set("name", value)} required />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Latitude" required>
            <Input value={form.latitude} onChange={(value) => set("latitude", value)} required />
          </Field>
          <Field label="Longitude" required>
            <Input value={form.longitude} onChange={(value) => set("longitude", value)} required />
          </Field>
        </div>
        <Field label="Road name">
          <Input value={form.road_name} onChange={(value) => set("road_name", value)} />
        </Field>
        <Field label="Description">
          <Input value={form.description} onChange={(value) => set("description", value)} />
        </Field>
      </Section>

      <Section title="Source">
        <Field label="Stream URL" hint="RTSP or HTTP. Leave blank for upload-only cameras.">
          <Input value={form.stream_url} onChange={(value) => set("stream_url", value)} />
        </Field>
        <div className="grid grid-cols-3 gap-2">
          <Field label="Width">
            <Input value={form.frame_width} onChange={(value) => set("frame_width", value)} />
          </Field>
          <Field label="Height">
            <Input value={form.frame_height} onChange={(value) => set("frame_height", value)} />
          </Field>
          <Field label="FPS">
            <Input value={form.frame_rate} onChange={(value) => set("frame_rate", value)} />
          </Field>
        </div>
        {!isNew ? (
          <Field label="Status">
            <Select
              value={form.status}
              onChange={(value) => set("status", value)}
              options={CAMERASTATUS_VALUES}
            />
          </Field>
        ) : null}
      </Section>

      <Section
        title="Geometry"
        hint="These settings decide which safety checks this camera can perform. Left blank, the corresponding check reports UNABLE TO DETERMINE rather than guessing."
      >
        <Field label="Signal phase" hint="UNKNOWN disables red-light detection entirely.">
          <Select
            value={form.signal_state}
            onChange={(value) => set("signal_state", value)}
            options={SIGNALSTATE_VALUES}
          />
        </Field>

        <div>
          <span className="field-label">Stop line (image pixels)</span>
          <div className="grid grid-cols-4 gap-1.5">
            {(["x1", "y1", "x2", "y2"] as const).map((key) => (
              <Input
                key={key}
                value={form.stop_line[key]}
                placeholder={key}
                onChange={(value) => set("stop_line", { ...form.stop_line, [key]: value })}
              />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Field label="Metres per pixel" hint="Enables speed estimation.">
            <Input
              value={form.metres_per_pixel}
              onChange={(value) => set("metres_per_pixel", value)}
            />
          </Field>
          <Field label="Reference row (y)">
            <Input value={form.reference_y} onChange={(value) => set("reference_y", value)} />
          </Field>
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="field-label mb-0">Lane directions</span>
            <button
              type="button"
              onClick={() =>
                set("lanes", [
                  ...form.lanes,
                  { lane_index: String(form.lanes.length), heading_deg: "", label: "" },
                ])
              }
              className="text-accent hover:text-accent-hover text-2xs"
            >
              + Add lane
            </button>
          </div>
          {form.lanes.length === 0 ? (
            <p className="text-ink-subtle text-2xs">
              None configured — wrong-way detection is unavailable for this camera.
            </p>
          ) : (
            <div className="space-y-1.5">
              {form.lanes.map((lane, index) => (
                <div key={index} className="flex items-center gap-1.5">
                  <Input
                    value={lane.lane_index}
                    placeholder="idx"
                    className="w-12"
                    onChange={(value) => {
                      const next = [...form.lanes];
                      next[index] = { ...lane, lane_index: value };
                      set("lanes", next);
                    }}
                  />
                  <Input
                    value={lane.heading_deg}
                    placeholder="heading°"
                    className="w-20"
                    onChange={(value) => {
                      const next = [...form.lanes];
                      next[index] = { ...lane, heading_deg: value };
                      set("lanes", next);
                    }}
                  />
                  <Input
                    value={lane.label}
                    placeholder="label"
                    onChange={(value) => {
                      const next = [...form.lanes];
                      next[index] = { ...lane, label: value };
                      set("lanes", next);
                    }}
                  />
                  <button
                    type="button"
                    aria-label={`Remove lane ${index}`}
                    onClick={() => set("lanes", form.lanes.filter((_, i) => i !== index))}
                    className="text-ink-subtle hover:text-risk-critical shrink-0"
                  >
                    <Icon name="close" size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Section>

      {camera ? (
        <Section title="Resulting capability">
          <div className="flex flex-wrap gap-1">
            {Object.entries(camera.capabilities).map(([key, enabled]) => (
              <Badge key={key} tone={enabled ? "low" : "offline"}>
                {key.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
          <p className="text-ink-subtle text-2xs">
            Registered {formatTimestamp(camera.created_at)}
            {camera.updated_at ? ` · updated ${formatTimestamp(camera.updated_at)}` : ""}
          </p>
        </Section>
      ) : null}

      <div className="border-line flex items-center gap-2 border-t pt-3">
        <Button type="submit" variant="primary" loading={pending} className="flex-1">
          {isNew ? "Register camera" : "Save changes"}
        </Button>
        {onDelete ? (
          <Button
            type="button"
            variant="danger"
            loading={deleting}
            onClick={async () => {
              setDeleting(true);
              try {
                await onDelete();
              } finally {
                setDeleting(false);
              }
            }}
          >
            Remove
          </Button>
        ) : null}
      </div>
    </form>
  );
}

/* --------------------------------------------------------------- primitives */

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="space-y-2.5">
      <legend className="text-ink-muted text-2xs font-semibold tracking-wide uppercase">
        {title}
      </legend>
      {hint ? <p className="text-ink-subtle text-2xs leading-relaxed">{hint}</p> : null}
      {children}
    </fieldset>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="field-label">
        {label}
        {required ? <span className="text-risk-critical ml-0.5">*</span> : null}
      </span>
      {children}
      {hint ? <span className="text-ink-subtle mt-1 block text-2xs">{hint}</span> : null}
    </label>
  );
}

function Input({
  value,
  onChange,
  placeholder,
  required,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  className?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      required={required}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      className={`border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none ${className ?? ""}`}
    />
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: readonly string[];
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none"
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}
