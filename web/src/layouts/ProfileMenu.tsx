/** Signed-in user menu: identity, role, and sign-out. */

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { ROLE_LABELS } from "@/features/auth/types";
import { cn } from "@/lib/cn";

export function ProfileMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click and on Escape, the two ways a user expects to
  // dismiss a popover.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!user) return null;

  const initials = initialsFor(user.display_name || user.email);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${user.email}`}
        className={cn(
          "flex items-center gap-1.5 rounded-sm px-1 py-0.5 transition-colors",
          open ? "bg-surface-hover" : "hover:bg-surface-hover",
        )}
      >
        <span className="border-accent-line bg-accent-dim text-accent flex size-6 items-center justify-center rounded-sm border text-2xs font-semibold">
          {initials}
        </span>
        <Icon name="chevronDown" size={12} className="text-ink-subtle" />
      </button>

      {open ? (
        <div
          role="menu"
          className="border-line bg-surface-raised absolute right-0 z-50 mt-1 w-56 rounded-sm border shadow-[var(--shadow-popover)]"
        >
          <div className="border-line border-b p-3">
            <p className="text-ink truncate text-xs font-medium">
              {user.display_name || user.email}
            </p>
            {user.display_name ? (
              <p className="text-ink-subtle mt-0.5 truncate text-2xs">{user.email}</p>
            ) : null}
            <p className="text-accent mt-1.5 text-2xs font-semibold tracking-wide uppercase">
              {ROLE_LABELS[user.role]}
            </p>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
            className="text-ink-muted hover:bg-surface-hover hover:text-ink flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors"
          >
            <Icon name="logout" size={14} />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

function initialsFor(label: string): string {
  const trimmed = label.trim();
  if (!trimmed) return "?";

  // A display name gives first+last initials; an email gives the first two
  // characters of the local part, which is more distinctive than one.
  if (trimmed.includes("@")) {
    return trimmed.slice(0, 2).toUpperCase();
  }
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}
