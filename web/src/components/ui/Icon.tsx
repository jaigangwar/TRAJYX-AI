/**
 * Icon set, hand-drawn on a 16px grid.
 *
 * Bundling a 1000-glyph icon library for eighteen icons is waste, and generic
 * icon packs are a large part of why generated interfaces look alike. These are
 * drawn to read at 14-16px against a dark ground, with a consistent 1.5px
 * stroke and square-ish terminals matching the typography.
 */

import type { IconName } from "@/app/navigation";

const PATHS: Record<IconName | ExtraIcon, string> = {
  /* --- navigation --------------------------------------------------------- */
  overview: "M2 9.5 6 5l3.5 3.5L14 3.5M14 3.5h-3.5M14 3.5V7M2 13.5h12",
  monitor: "M2 3.5h12v8H2zM6 14h4M8 11.5V14M5 7.5l1.8 1.8L9 6.5l2 2",
  simulation: "M8 2 14 5v6l-6 3-6-3V5zM8 2v6m0 0 6-3M8 8l-6-3m6 3v6",
  video: "M2 4h8.5v8H2zM10.5 7l3.5-2v6l-3.5-2z",
  map: "M6 2.5 2 4v9.5l4-1.5 4 1.5 4-1.5V2.5L10 4zM6 2.5V12M10 4v9.5",
  violation: "M8 2 1.5 13.5h13zM8 6.5v3.5M8 11.8v.2",
  nearmiss: "M2 12 7 5M14 12 9 5M8 2.5v2M4.5 3.5 5.5 5M11.5 3.5 10.5 5M3.5 13h3M9.5 13h3",
  incident: "M8 1.5 2 4.5v4c0 3 2.5 5 6 6 3.5-1 6-3 6-6v-4zM8 5.5v3.5M8 11v.3",
  camera: "M2.5 5.5h11v7h-11zM5.5 5.5 6.5 3.5h3l1 2M8 10.5a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6",
  analytics: "M2 14V2M2 14h12M4.5 11.5v-3M7.5 11.5V6M10.5 11.5V8.5M13.5 11.5v-7",
  report: "M3.5 1.5h6L12.5 4.5v10h-9zM9.5 1.5v3h3M5.5 8h5M5.5 10.5h5M5.5 5.5h2",
  model: "M8 2.5 13 5.5v5L8 13.5 3 10.5v-5zM8 2.5v4M8 6.5 3 5.5M8 6.5l5-1M8 6.5v7",
  settings:
    "M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4M8 1.5v1.8M8 12.7v1.8M2.9 4.4l1.6.9M11.5 10.7l1.6.9M2.9 11.6l1.6-.9M11.5 5.3l1.6-.9",

  /* --- chrome and actions ------------------------------------------------- */
  chevronLeft: "M10 3.5 5.5 8l4.5 4.5",
  chevronRight: "M6 3.5 10.5 8 6 12.5",
  chevronDown: "M3.5 6 8 10.5 12.5 6",
  close: "M4 4l8 8M12 4l-8 8",
  search: "M7 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10M10.6 10.6 14 14",
  filter: "M2 4h12M4 8h8M6.5 12h3",
  refresh: "M13.5 8a5.5 5.5 0 1 1-1.9-4.2M13.5 2v3.5H10",
  download: "M8 2v7.5M5 7l3 3 3-3M2.5 13.5h11",
  upload: "M8 10.5V3M5 6l3-3 3 3M2.5 13.5h11",
  alert: "M12 6a4 4 0 1 0-8 0c0 4-1.5 5-1.5 5h11S12 10 12 6M6.5 13.5a1.7 1.7 0 0 0 3 0",
  user: "M8 8a2.6 2.6 0 1 0 0-5.2A2.6 2.6 0 0 0 8 8M3 13.5c0-2.2 2.2-3.8 5-3.8s5 1.6 5 3.8",
  logout: "M6 13.5H3V2.5h3M9.5 11l3-3-3-3M12.5 8H6",
  clock: "M8 14A6 6 0 1 0 8 2a6 6 0 0 0 0 12M8 4.5V8l2.5 1.5",
  play: "M5 3.5 12 8l-7 4.5z",
  pause: "M5 3.5h2.5v9H5zM8.5 3.5H11v9H8.5z",
  pin: "M8 14V9M8 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6",
  sun: "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M8 1.5v1.5M8 13v1.5M2.8 2.8l1 1M12.2 12.2l1 1M1.5 8H3M13 8h1.5M2.8 13.2l1-1M12.2 3.8l1-1",
  moon: "M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5",
  check: "M3 8.5 6.5 12 13 4.5",
  info: "M8 14A6 6 0 1 0 8 2a6 6 0 0 0 0 12M8 7v4M8 5v.2",
};

type ExtraIcon =
  | "chevronLeft"
  | "chevronRight"
  | "chevronDown"
  | "close"
  | "search"
  | "filter"
  | "refresh"
  | "download"
  | "upload"
  | "alert"
  | "user"
  | "logout"
  | "clock"
  | "play"
  | "pause"
  | "pin"
  | "sun"
  | "moon"
  | "check"
  | "info";

export type AnyIconName = IconName | ExtraIcon;

interface IconProps {
  name: AnyIconName;
  size?: number;
  className?: string;
  /** Supply when the icon is the only content of a control. */
  title?: string;
}

export function Icon({ name, size = 16, className, title }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {title ? <title>{title}</title> : null}
      <path d={PATHS[name]} />
    </svg>
  );
}
