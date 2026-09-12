/**
 * Loading, empty and error states.
 *
 * The UX contract for TRAJYX is that no data region is ever blank: a panel is
 * always either loading, showing data, explaining that there is none, or
 * explaining what failed. These components are the only sanctioned way to
 * render those states, which keeps the wording and density consistent.
 */

import type { ReactNode } from "react";

import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/cn";

/* ------------------------------------------------------------------ loading -- */

interface SkeletonProps {
  className?: string;
}

/** A single shimmer-free placeholder bar. Motion is avoided: it reads as noise
 *  on a dense operations screen and animating dozens of rows costs frames. */
export function Skeleton({ className }: SkeletonProps) {
  return <div className={cn("bg-line-subtle animate-pulse rounded-xs", className)} aria-hidden="true" />;
}

interface LoadingStateProps {
  /** Short description of what is loading, announced to screen readers. */
  label?: string;
  /** `rows` renders table-shaped placeholders; `block` a single region. */
  variant?: "rows" | "block";
  rows?: number;
  className?: string;
}

export function LoadingState({
  label = "Loading",
  variant = "block",
  rows = 5,
  className,
}: LoadingStateProps) {
  return (
    <div className={cn("p-3", className)} role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}</span>
      {variant === "rows" ? (
        <div className="space-y-2">
          {Array.from({ length: rows }, (_, index) => (
            <div key={index} className="flex items-center gap-3">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 flex-1" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          <Skeleton className="h-3 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- empty -- */

interface EmptyStateProps {
  /** What is missing, phrased concretely: "No risk events in this time range." */
  message: string;
  /** Optional follow-up telling the operator what would produce data. */
  hint?: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ message, hint, icon, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      {icon ? <div className="text-ink-subtle mb-3">{icon}</div> : null}
      <p className="text-ink-muted text-sm">{message}</p>
      {hint ? <p className="text-ink-subtle mt-1.5 max-w-sm text-xs">{hint}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/* -------------------------------------------------------------------- error -- */

interface ErrorStateProps {
  /** The caught value. `ApiError` is unwrapped for its code and request id. */
  error: unknown;
  /** Context prefix, e.g. "Could not load cameras". */
  title?: string;
  onRetry?: () => void;
  className?: string;
}

function describe(error: unknown): { message: string; code?: string; requestId?: string; retryable: boolean } {
  if (error instanceof ApiError) {
    return {
      message: error.message,
      code: error.code,
      requestId: error.requestId,
      retryable: error.isRetryable,
    };
  }
  if (error instanceof Error) {
    return { message: error.message, retryable: false };
  }
  return { message: "An unexpected error occurred.", retryable: false };
}

export function ErrorState({ error, title = "Something went wrong", onRetry, className }: ErrorStateProps) {
  const { message, code, requestId, retryable } = describe(error);

  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <div className="border-risk-critical/40 bg-risk-critical-dim mb-3 rounded-sm border px-2 py-0.5">
        <span className="text-risk-critical text-2xs font-semibold tracking-wider uppercase">
          {code ?? "Error"}
        </span>
      </div>
      <p className="text-ink text-sm font-medium">{title}</p>
      <p className="text-ink-muted mt-1 max-w-md text-xs">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="border-line-strong bg-surface-raised hover:bg-surface-hover text-ink mt-4 rounded-sm border px-3 py-1.5 text-xs font-medium transition-colors"
        >
          {retryable ? "Retry" : "Try again"}
        </button>
      ) : null}
      {requestId ? (
        <p className="text-ink-subtle mono mt-3 text-2xs">
          Request {requestId}
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------ async wrapper -- */

interface AsyncBoundaryProps<T> {
  isLoading: boolean;
  error: unknown;
  data: T | undefined;
  /** Called with loaded data. Returning `null` is treated as "render nothing". */
  children: (data: T) => ReactNode;
  /** Predicate for emptiness; defaults to empty-array detection. */
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
  emptyHint?: string;
  errorTitle?: string;
  onRetry?: () => void;
  loadingVariant?: "rows" | "block";
  loadingRows?: number;
  loadingLabel?: string;
}

/**
 * Renders exactly one of loading / error / empty / content.
 *
 * Using this instead of inline ternaries is what makes the four-state rule
 * actually hold across dozens of panels.
 */
export function AsyncBoundary<T>({
  isLoading,
  error,
  data,
  children,
  isEmpty,
  emptyMessage = "No data available.",
  emptyHint,
  errorTitle,
  onRetry,
  loadingVariant = "block",
  loadingRows,
  loadingLabel,
}: AsyncBoundaryProps<T>) {
  if (isLoading && data === undefined) {
    return <LoadingState variant={loadingVariant} rows={loadingRows} label={loadingLabel} />;
  }
  if (error) {
    return <ErrorState error={error} title={errorTitle} onRetry={onRetry} />;
  }
  if (data === undefined) {
    return <EmptyState message={emptyMessage} hint={emptyHint} />;
  }

  const empty = isEmpty ? isEmpty(data) : Array.isArray(data) && data.length === 0;
  if (empty) {
    return <EmptyState message={emptyMessage} hint={emptyHint} />;
  }
  return <>{children(data)}</>;
}
