/**
 * Chart primitives.
 *
 * Deliberately hand-rolled SVG and flex rows rather than a charting library.
 * These are operations-console charts: dense, small, gridless, and readable at
 * a glance from across a room. A general-purpose library would bring its own
 * spacing, tooltips and animation opinions, all of which would have to be
 * fought back to get this.
 *
 * The rule that shapes every component here: **a null value is not zero.** A
 * bar with no measurement renders as an empty slot marked with a reason, never
 * as a bar of height zero, and a trend line breaks across a gap rather than
 * drawing a straight segment through it. Interpolating across missing data is
 * how a chart comes to assert something nobody measured.
 */

import { useId, type ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface Datum {
  key: string;
  /** Axis label. Kept short, since 24 of these share one row. */
  label: string;
  /**
   * Label used in the hover text, when the axis label had to be abbreviated
   * to fit. An hour column reads "03" on the axis but should say "03:00" on
   * hover, where there is room to be unambiguous.
   */
  hoverLabel?: string;
  /** The measured value, or null when nothing was measured for this bucket. */
  value: number | null;
  /** Optional second series drawn as an inner bar, e.g. near misses within events. */
  secondary?: number | null;
  /** Overrides the bar colour. Defaults to the accent. */
  color?: string;
  /** Extra detail for the hover title. */
  note?: string;
}

/* ------------------------------------------------------------------ columns */

interface ColumnChartProps {
  data: Datum[];
  /** Axis maximum. Defaults to the largest value present. */
  max?: number;
  height?: number;
  /** Show every nth label, so a 24-hour axis does not collide. */
  labelEvery?: number;
  valueSuffix?: string;
  secondaryLabel?: string;
  className?: string;
}

export function ColumnChart({
  data,
  max,
  height = 104,
  labelEvery = 1,
  valueSuffix = "",
  secondaryLabel,
  className,
}: ColumnChartProps) {
  const values = data.map((datum) => datum.value).filter((value): value is number => value !== null);
  const ceiling = max ?? Math.max(1, ...values);

  return (
    <div className={className}>
      <div className="flex items-end gap-px" style={{ height }} role="img">
        {data.map((datum) => {
          const measured = datum.value !== null;
          const ratio = measured ? Math.min(1, datum.value! / ceiling) : 0;
          // A measured non-zero value always gets at least 2px so it cannot
          // disappear; a measured zero stays flat, which is the honest height.
          const barHeight = measured
            ? datum.value! === 0
              ? 1
              : Math.max(2, ratio * height)
            : height;
          const secondaryHeight =
            datum.secondary !== null && datum.secondary !== undefined && datum.secondary > 0
              ? Math.max(2, Math.min(1, datum.secondary / ceiling) * height)
              : 0;

          const name = datum.hoverLabel ?? datum.label;
          const title = measured
            ? `${name}: ${formatValue(datum.value!)}${valueSuffix}` +
              (secondaryHeight && secondaryLabel
                ? ` · ${secondaryLabel} ${formatValue(datum.secondary!)}`
                : "") +
              (datum.note ? ` · ${datum.note}` : "")
            : `${name}: not measured${datum.note ? ` — ${datum.note}` : ""}`;

          return (
            <div
              key={datum.key}
              title={title}
              className="relative flex min-w-0 flex-1 items-end"
              style={{ height }}
            >
              {measured ? (
                <>
                  <div
                    className="w-full rounded-t-[1px] transition-[height]"
                    style={{
                      height: barHeight,
                      backgroundColor: datum.color ?? "var(--color-accent)",
                      opacity: datum.value === 0 ? 0.45 : 0.85,
                    }}
                  />
                  {secondaryHeight ? (
                    <div
                      className="absolute bottom-0 left-1/2 w-[45%] -translate-x-1/2 rounded-t-[1px]"
                      style={{
                        height: secondaryHeight,
                        backgroundColor: "var(--color-risk-critical)",
                      }}
                    />
                  ) : null}
                </>
              ) : (
                // Unmeasured: a faint hatched slot, visibly not a zero bar.
                <div className="bg-surface-sunken border-line-subtle h-full w-full border-x border-dashed opacity-40" />
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-1 flex gap-px">
        {data.map((datum, index) => (
          <div key={datum.key} className="min-w-0 flex-1 text-center">
            {index % labelEvery === 0 ? (
              <span className="text-ink-subtle mono text-[9px] leading-none">{datum.label}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- trend line */

interface TrendLineProps {
  data: Datum[];
  height?: number;
  max?: number;
  color?: string;
  valueSuffix?: string;
  className?: string;
}

/**
 * A single series over time, drawn as an SVG polyline.
 *
 * Runs of consecutive measured points become separate polylines, so a gap in
 * the data reads as a gap rather than as a straight line through it.
 */
export function TrendLine({
  data,
  height = 120,
  max,
  color = "var(--color-accent)",
  valueSuffix = "",
  className,
}: TrendLineProps) {
  const gradientId = useId();
  const values = data.map((datum) => datum.value).filter((value): value is number => value !== null);
  const ceiling = max ?? Math.max(1, ...values);
  const width = 100;
  const step = data.length > 1 ? width / (data.length - 1) : 0;

  const point = (index: number, value: number) => ({
    x: index * step,
    y: height - (Math.min(1, value / ceiling) * (height - 6) + 3),
  });

  // Split into runs of consecutive measured points.
  const runs: { x: number; y: number }[][] = [];
  let run: { x: number; y: number }[] = [];
  data.forEach((datum, index) => {
    if (datum.value === null) {
      if (run.length) runs.push(run);
      run = [];
      return;
    }
    run.push(point(index, datum.value));
  });
  if (run.length) runs.push(run);

  const area = runs
    .filter((entries) => entries.length > 1)
    .map(
      (entries) =>
        `M ${entries[0]!.x} ${height} ` +
        entries.map((entry) => `L ${entry.x} ${entry.y}`).join(" ") +
        ` L ${entries.at(-1)!.x} ${height} Z`,
    )
    .join(" ");

  return (
    <div className={className}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height }}
        role="img"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        {area ? <path d={area} fill={`url(#${gradientId})`} /> : null}

        {runs.map((entries, index) =>
          entries.length > 1 ? (
            <polyline
              key={index}
              points={entries.map((entry) => `${entry.x},${entry.y}`).join(" ")}
              fill="none"
              stroke={color}
              strokeWidth="1.5"
              vectorEffect="non-scaling-stroke"
              strokeLinejoin="round"
            />
          ) : (
            <circle key={index} cx={entries[0]!.x} cy={entries[0]!.y} r="1.5" fill={color} />
          ),
        )}
      </svg>

      <div className="mt-1 flex">
        {data.map((datum, index) => (
          <div
            key={datum.key}
            className="min-w-0 flex-1 text-center"
            title={
              datum.value === null
                ? `${datum.hoverLabel ?? datum.label}: not measured`
                : `${datum.hoverLabel ?? datum.label}: ${formatValue(datum.value)}${valueSuffix}`
            }
          >
            {index === 0 || index === data.length - 1 || index === Math.floor(data.length / 2) ? (
              <span className="text-ink-subtle mono text-[9px]">{datum.label}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- share list */

export interface ShareDatum {
  key: string;
  label: string;
  count: number;
  share: number;
  color?: string;
}

/**
 * A ranked breakdown as label / bar / count rows.
 *
 * Preferred over a pie chart: an operator comparing "which violation is most
 * common" reads ranked bars far faster than angular segments, and this stays
 * legible down to a 240px column.
 */
export function ShareList({
  data,
  limit,
  className,
}: {
  data: ShareDatum[];
  limit?: number;
  className?: string;
}) {
  const rows = limit ? data.slice(0, limit) : data;
  const peak = Math.max(1, ...rows.map((row) => row.count));

  return (
    <ul className={cn("space-y-1.5", className)}>
      {rows.map((row) => (
        <li key={row.key} className="grid grid-cols-[1fr_auto] items-center gap-x-2">
          <span className="text-ink-muted truncate text-xs" title={row.label}>
            {row.label}
          </span>
          <span className="text-ink mono shrink-0 text-2xs tabular-nums">
            {row.count.toLocaleString()}
            <span className="text-ink-subtle ml-1.5">{(row.share * 100).toFixed(1)}%</span>
          </span>
          <div className="bg-surface-sunken col-span-2 h-1 overflow-hidden rounded-full">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(row.count / peak) * 100}%`,
                backgroundColor: row.color ?? "var(--color-accent)",
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------ unavailability */

/**
 * What a chart shows when it cannot be drawn.
 *
 * Kept as a component rather than an empty chart so "we did not measure this"
 * is stated in words, with the reason the API gave.
 */
export function Unavailable({ reason, children }: { reason: string; children?: ReactNode }) {
  return (
    <div className="border-line-subtle bg-surface-sunken rounded-sm border border-dashed p-3">
      <p className="text-ink-muted text-2xs font-semibold tracking-wide uppercase">
        Unable to determine
      </p>
      <p className="text-ink-subtle mt-1 text-xs leading-relaxed">{reason}</p>
      {children}
    </div>
  );
}

function formatValue(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
