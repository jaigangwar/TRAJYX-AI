import { Link } from "react-router-dom";

import { TrajyxMark } from "@/components/brand/Logo";

export function NotFoundPage() {
  return (
    <div className="bg-ground flex h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <TrajyxMark size={36} className="text-ink-subtle" title="TRAJYX" />
      <div>
        <p className="text-ink text-lg font-semibold">Page not found</p>
        <p className="text-ink-muted mt-1 text-xs">
          The requested route does not exist in this build.
        </p>
      </div>
      <Link
        to="/overview"
        className="border-line-strong bg-surface-raised hover:bg-surface-hover text-ink rounded-sm border px-3 py-1.5 text-xs font-medium transition-colors"
      >
        Back to overview
      </Link>
    </div>
  );
}
