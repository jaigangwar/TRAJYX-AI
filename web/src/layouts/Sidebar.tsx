/** Primary navigation rail. Collapsible to icons for map- and video-heavy pages. */

import { NavLink } from "react-router-dom";

import { groupedNavForRole } from "@/app/navigation";
import { TrajyxMark, TrajyxWordmark } from "@/components/brand/Logo";
import { Icon } from "@/components/ui/Icon";
import { cn } from "@/lib/cn";
import type { Role } from "@shared/domain";

interface SidebarProps {
  role: Role | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export function Sidebar({ role, collapsed, onToggleCollapsed }: SidebarProps) {
  const groups = groupedNavForRole(role);

  return (
    <nav
      aria-label="Main navigation"
      className={cn(
        "border-line bg-surface flex shrink-0 flex-col border-r transition-[width] duration-150",
        collapsed ? "w-[52px]" : "w-[196px]",
      )}
    >
      <div
        className={cn(
          "border-line flex h-11 shrink-0 items-center border-b",
          collapsed ? "justify-center px-0" : "px-3",
        )}
      >
        {collapsed ? (
          <TrajyxMark size={20} className="text-ink" title="TRAJYX" />
        ) : (
          <TrajyxWordmark />
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto py-2">
        {groups.map(({ group, items }) => (
          <div key={group} className="mb-3">
            {!collapsed ? (
              <h3 className="text-ink-subtle px-3 pt-1 pb-1.5 text-2xs font-semibold tracking-[0.08em] uppercase">
                {group}
              </h3>
            ) : (
              <div className="bg-line-subtle mx-3 mb-2 h-px" aria-hidden="true" />
            )}

            <ul>
              {items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      cn(
                        "relative flex items-center gap-2.5 text-xs transition-colors",
                        collapsed ? "h-8 justify-center px-0" : "h-7.5 px-3",
                        isActive
                          ? "bg-accent-dim text-accent font-medium"
                          : "text-ink-muted hover:bg-surface-hover hover:text-ink",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive ? (
                          <span
                            className="bg-accent absolute top-0 left-0 h-full w-[2px]"
                            aria-hidden="true"
                          />
                        ) : null}
                        <Icon name={item.icon} size={15} className="shrink-0" />
                        {!collapsed ? <span className="truncate">{item.label}</span> : null}
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        className="border-line text-ink-subtle hover:bg-surface-hover hover:text-ink flex h-8 shrink-0 items-center justify-center border-t transition-colors"
      >
        <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size={14} />
      </button>
    </nav>
  );
}
