/**
 * Top bar: where you are, what the system state is, and who you are.
 *
 * The environment/backend chip is deliberately prominent. An operator must
 * never have to guess whether the numbers on screen came from Firebase-backed
 * production data or a local demo store.
 */

import { useTheme } from "@/app/theme-context";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { useHealth } from "@/features/system/api";
import { ProfileMenu } from "@/layouts/ProfileMenu";

interface TopBarProps {
  title: string;
  /** Short sentence under the title describing what the page shows. */
  subtitle?: string;
  /** Page-level controls: time range pickers, refresh, export. */
  actions?: React.ReactNode;
}

export function TopBar({ title, subtitle, actions }: TopBarProps) {
  const { theme, toggleTheme } = useTheme();
  const { data: health } = useHealth();

  return (
    <header
      aria-label="Page header"
      className="border-line bg-surface flex h-11 shrink-0 items-center gap-3 border-b px-4"
    >
      <div className="flex min-w-0 flex-col justify-center">
        <h1 className="text-ink truncate text-[13px] leading-tight font-semibold">{title}</h1>
        {subtitle ? (
          <p className="text-ink-subtle truncate text-2xs leading-tight">{subtitle}</p>
        ) : null}
      </div>

      <div className="flex-1" />

      {actions ? <div className="flex items-center gap-1.5">{actions}</div> : null}

      {health ? <SystemStateChips health={health} /> : null}

      <div className="bg-line h-5 w-px" aria-hidden="true" />

      <button
        type="button"
        onClick={toggleTheme}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        className="text-ink-subtle hover:bg-surface-hover hover:text-ink flex size-7 items-center justify-center rounded-sm transition-colors"
      >
        <Icon name={theme === "dark" ? "sun" : "moon"} size={15} />
      </button>

      <ProfileMenu />
    </header>
  );
}

function SystemStateChips({ health }: { health: NonNullable<ReturnType<typeof useHealth>["data"]> }) {
  const { capabilities, environment } = health;
  const usingLocalData = capabilities.data_backend === "local";

  return (
    <div className="flex items-center gap-1.5">
      {capabilities.demo_mode ? (
        <Badge tone="accent" title="Demo mode is on. Synthetic records are labeled DEMO DATA.">
          Demo mode
        </Badge>
      ) : null}

      {usingLocalData ? (
        <Badge
          tone="neutral"
          title="Operational data is served from the local development store, not Firestore."
        >
          Local store
        </Badge>
      ) : (
        <Badge tone="info" title="Operational data is served from Firestore.">
          Firestore
        </Badge>
      )}

      {environment !== "production" ? <Badge tone="neutral">{environment}</Badge> : null}
    </div>
  );
}
