/** Buttons. Four variants, two sizes — enough for an operations console. */

import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANT_CLASS: Record<Variant, string> = {
  primary:
    "border-accent bg-accent text-ink-inverse hover:bg-accent-hover active:bg-accent-press disabled:bg-accent/40",
  secondary: "border-line-strong bg-surface-raised text-ink hover:bg-surface-hover",
  ghost: "border-transparent bg-transparent text-ink-muted hover:bg-surface-hover hover:text-ink",
  danger:
    "border-risk-critical/50 bg-risk-critical-dim text-risk-critical hover:bg-risk-critical hover:text-ink-inverse",
};

const SIZE_CLASS: Record<Size, string> = {
  sm: "h-6 px-2 text-2xs gap-1",
  md: "h-7.5 px-3 text-xs gap-1.5",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Shows a spinner and blocks interaction. Keeps the label for stable width. */
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center rounded-sm border font-medium whitespace-nowrap transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-55",
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

function Spinner() {
  return (
    <svg className="size-3 animate-spin" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
