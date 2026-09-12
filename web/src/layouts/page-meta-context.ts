/** Page header context, kept out of the layout component file so that module
 *  only exports components and stays eligible for fast refresh. */

import { createContext, useContext } from "react";
import type { ReactNode } from "react";

export interface PageMetaValue {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export interface PageMetaContextValue {
  setPageMeta: (meta: PageMetaValue) => void;
}

export const PageMetaContext = createContext<PageMetaContextValue | null>(null);

/** Pages call this to publish their header content to the dashboard chrome. */
export function usePageMeta(): PageMetaContextValue {
  const context = useContext(PageMetaContext);
  if (!context) throw new Error("usePageMeta must be used inside DashboardLayout.");
  return context;
}
