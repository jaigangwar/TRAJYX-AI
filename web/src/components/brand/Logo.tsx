/**
 * TRAJYX identity, drawn as inline SVG so it stays crisp at every size and
 * inherits theme colours without shipping a raster asset.
 *
 * The mark is a road receding to a vanishing point with a trajectory arc
 * lifting off it — the product's core idea (observed road behaviour becomes a
 * predicted path) in one glyph. The raster brand files in assets/brand are the
 * canonical marks for app stores and documents; this is the in-product version.
 */

interface MarkProps {
  size?: number;
  className?: string;
  /** Decorative marks are hidden from assistive tech; standalone marks get a label. */
  title?: string;
}

export function TrajyxMark({ size = 22, className, title }: MarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {title ? <title>{title}</title> : null}

      {/* Road surface: a trapezoid narrowing toward the horizon. */}
      <path d="M6 29 L13.2 7 h5.6 L26 29 Z" fill="currentColor" opacity="0.16" />

      {/* Road edges. */}
      <path
        d="M6 29 L13.2 7 M26 29 L18.8 7"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.5"
      />

      {/* Centre line, dashes shortening with distance to read as perspective. */}
      <path
        d="M16 27.5 V24 M16 21.5 V18.8 M16 16.8 V14.7 M16 13 V11.4 M16 10 V8.9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.42"
      />

      {/* Predicted trajectory lifting off the road — the accent element. */}
      <path
        d="M10.5 26.5 C13.5 19.5 17.5 14 24.5 9.5"
        stroke="var(--color-accent)"
        strokeWidth="2.1"
        strokeLinecap="round"
        fill="none"
      />

      {/* Leading vertex of the trajectory. */}
      <circle cx="24.8" cy="9.3" r="2.5" fill="var(--color-accent)" />
    </svg>
  );
}

interface WordmarkProps {
  /** `full` adds the descriptor line beneath the name. */
  variant?: "compact" | "full";
  className?: string;
}

export function TrajyxWordmark({ variant = "compact", className }: WordmarkProps) {
  return (
    <span className={className}>
      <span className="flex items-center gap-2">
        <TrajyxMark size={variant === "full" ? 30 : 22} className="text-ink shrink-0" />
        <span className="flex flex-col leading-none">
          <span className="text-ink text-[15px] font-semibold tracking-[0.14em]">TRAJYX</span>
          {variant === "full" ? (
            <span className="text-ink-subtle mt-1 text-2xs tracking-[0.08em] uppercase">
              Predictive Road Safety
            </span>
          ) : null}
        </span>
      </span>
    </span>
  );
}
