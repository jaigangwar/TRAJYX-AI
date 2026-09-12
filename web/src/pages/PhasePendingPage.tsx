/**
 * Honest placeholder for a section whose functionality has not landed yet.
 *
 * The route exists so navigation, permissions and deep links can be exercised
 * from the start, but the page states plainly that the feature is not built
 * and which phase delivers it. It never shows invented numbers or a mocked
 * chart, because a placeholder that looks finished is worse than no page.
 */

import { NAV_ITEMS } from "@/app/navigation";
import { Icon } from "@/components/ui/Icon";
import { Panel } from "@/components/ui/Panel";
import { usePageHeader } from "@/hooks/usePageHeader";

interface PhasePendingPageProps {
  title: string;
  /** Route path, used to look up the delivering phase from the nav table. */
  path: string;
  /** What this section will do once implemented. */
  summary: string;
  /** Concrete capabilities, listed so the intended scope is reviewable. */
  planned: readonly string[];
}

export function PhasePendingPage({ title, path, summary, planned }: PhasePendingPageProps) {
  const phase = NAV_ITEMS.find((item) => item.path === path)?.deliveredInPhase;

  usePageHeader(title, "Not implemented yet");

  return (
    <div className="p-4">
      <Panel title={title} meta={phase !== undefined ? `Phase ${phase}` : undefined}>
        <div className="max-w-2xl">
          <div className="border-line-strong bg-surface-sunken mb-4 flex items-start gap-2.5 rounded-sm border p-3">
            <Icon name="info" size={15} className="text-ink-subtle mt-px shrink-0" />
            <div>
              <p className="text-ink text-xs font-medium">
                This section is not implemented yet
                {phase !== undefined ? ` — it is delivered in phase ${phase}.` : "."}
              </p>
              <p className="text-ink-muted mt-1 text-xs">
                The route, navigation entry and role permissions are in place so the shell can be
                verified end to end. No placeholder metrics are shown here: TRAJYX does not display
                numbers it has not actually computed.
              </p>
            </div>
          </div>

          <p className="text-ink-muted text-xs">{summary}</p>

          <h3 className="field-label mt-4">Planned capabilities</h3>
          <ul className="space-y-1.5">
            {planned.map((entry) => (
              <li key={entry} className="text-ink-muted flex items-start gap-2 text-xs">
                <span className="bg-ink-subtle mt-1.5 size-1 shrink-0 rounded-full" aria-hidden="true" />
                {entry}
              </li>
            ))}
          </ul>
        </div>
      </Panel>
    </div>
  );
}
