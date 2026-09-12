/**
 * Top-level error boundary.
 *
 * A render failure in one panel must not blank the whole console, and an
 * operator needs something actionable rather than a white screen.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

import { TrajyxMark } from "@/components/brand/Logo";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class AppErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the component stack: it is the only way to find which panel failed.
    console.error("TRAJYX render error", error, info.componentStack);
  }

  private readonly handleReload = () => {
    window.location.reload();
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="bg-ground flex h-dvh flex-col items-center justify-center gap-4 px-6">
        <TrajyxMark size={32} className="text-ink-subtle" title="TRAJYX" />
        <div className="max-w-lg text-center">
          <p className="text-ink text-base font-semibold">The interface hit an unexpected error</p>
          <p className="text-ink-muted mt-1.5 text-xs">
            The dashboard stopped rendering to avoid showing incorrect information. Reloading
            usually clears it; the details below help diagnose the cause.
          </p>
        </div>
        <pre className="border-line bg-surface-sunken text-ink-muted mono max-h-40 max-w-lg overflow-auto rounded-sm border p-3 text-2xs whitespace-pre-wrap">
          {error.message}
        </pre>
        <button
          type="button"
          onClick={this.handleReload}
          className="border-accent bg-accent text-ink-inverse hover:bg-accent-hover rounded-sm border px-3 py-1.5 text-xs font-medium transition-colors"
        >
          Reload dashboard
        </button>
      </div>
    );
  }
}
