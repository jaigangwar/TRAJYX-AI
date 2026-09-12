/**
 * Dashboard chrome: navigation rail, top bar, and the page outlet.
 *
 * Pages declare their own title through the page-meta context rather than the
 * layout guessing from the route, so a page can show live detail in the header
 * (a camera name, a job id) without the layout knowing about routes.
 */

import { useCallback, useMemo, useState } from "react";
import { Outlet } from "react-router-dom";

import { Sidebar } from "@/layouts/Sidebar";
import { TopBar } from "@/layouts/TopBar";
import { PageMetaContext, type PageMetaValue } from "@/layouts/page-meta-context";
import type { Role } from "@shared/domain";

const SIDEBAR_STORAGE_KEY = "trajyx.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

interface DashboardLayoutProps {
  /** Signed-in user's role. Phase 1 supplies this from the auth context. */
  role: Role | null;
}

export function DashboardLayout({ role }: DashboardLayoutProps) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [meta, setMeta] = useState<PageMetaValue>({ title: "TRAJYX" });

  const toggleCollapsed = useCallback(() => {
    setCollapsed((current) => {
      const next = !current;
      try {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // Layout preference only; safe to lose.
      }
      return next;
    });
  }, []);

  const setPageMeta = useCallback((next: PageMetaValue) => setMeta(next), []);
  const pageMetaValue = useMemo(() => ({ setPageMeta }), [setPageMeta]);

  return (
    <div className="bg-ground flex h-dvh overflow-hidden">
      <Sidebar role={role} collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar title={meta.title} subtitle={meta.subtitle} actions={meta.actions} />

        <PageMetaContext.Provider value={pageMetaValue}>
          <main className="min-h-0 flex-1 overflow-auto">
            <Outlet />
          </main>
        </PageMetaContext.Provider>
      </div>
    </div>
  );
}
