/** Publishes a page's header content to the dashboard chrome. */

import { useEffect } from "react";
import type { ReactNode } from "react";

import { usePageMeta } from "@/layouts/page-meta-context";

export function usePageHeader(title: string, subtitle?: string, actions?: ReactNode): void {
  const { setPageMeta } = usePageMeta();

  useEffect(() => {
    setPageMeta({ title, subtitle, actions });
    document.title = `${title} · TRAJYX`;
  }, [title, subtitle, actions, setPageMeta]);
}
