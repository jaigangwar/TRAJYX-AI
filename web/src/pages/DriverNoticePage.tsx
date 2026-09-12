/**
 * Shown when a driver signs into the dashboard.
 *
 * Their account is valid; this interface simply is not for them. Saying so
 * plainly, and pointing at the app that is, beats a permission error.
 */

import { useEffect } from "react";

import { TrajyxMark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { ROLE_LABELS } from "@/features/auth/types";

export function DriverNoticePage() {
  const { user, signOut } = useAuth();

  useEffect(() => {
    document.title = "Driver account · TRAJYX";
  }, []);

  return (
    <div className="bg-ground flex min-h-dvh items-center justify-center p-4">
      <div className="panel w-full max-w-md p-6 text-center">
        <TrajyxMark size={36} className="text-ink mx-auto" title="TRAJYX" />

        <h1 className="text-ink mt-4 text-base font-semibold">This console is for operators</h1>

        <p className="text-ink-muted mt-2 text-xs leading-relaxed">
          You are signed in as{" "}
          <span className="text-ink font-medium">{user?.email}</span>
          {user ? (
            <>
              {" "}
              with the <span className="text-ink font-medium">{ROLE_LABELS[user.role]}</span> role.
            </>
          ) : (
            "."
          )}{" "}
          The driver safety experience — trip alerts, nearby risk zones and hazard reporting —
          lives in the TRAJYX mobile app.
        </p>

        <div className="border-line-strong bg-surface-sunken mt-4 flex items-start gap-2.5 rounded-sm border p-3 text-left">
          <Icon name="info" size={14} className="text-ink-subtle mt-px shrink-0" />
          <p className="text-ink-muted text-xs">
            Install the TRAJYX Android app and sign in with these same credentials. If you should
            have operator or analyst access instead, ask an administrator to change your role.
          </p>
        </div>

        <Button variant="secondary" className="mt-5 w-full" onClick={signOut}>
          Sign out
        </Button>
      </div>
    </div>
  );
}
