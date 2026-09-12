/** Panel: the standard bordered container for a region of a page. */

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface PanelProps {
  /** Uppercase micro-label shown in the header. Omit for a chrome-less panel. */
  title?: string;
  /** Secondary text beside the title, e.g. a count or a time range. */
  meta?: ReactNode;
  /** Controls placed at the right of the header. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Removes body padding, for tables and maps that bleed to the edge. */
  flush?: boolean;
  /** Makes the body scroll instead of the page. Requires a bounded height. */
  scroll?: boolean;
}

export function Panel({ title, meta, actions, children, className, flush, scroll }: PanelProps) {
  return (
    <section className={cn("panel flex min-h-0 flex-col", className)}>
      {title || actions ? (
        <header className="panel-header shrink-0">
          <div className="flex min-w-0 items-baseline gap-2">
            <h2 className="panel-title truncate">{title}</h2>
            {meta ? <span className="text-ink-subtle shrink-0 text-2xs">{meta}</span> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn("min-h-0 flex-1", !flush && "p-3", scroll && "overflow-auto")}>{children}</div>
    </section>
  );
}
