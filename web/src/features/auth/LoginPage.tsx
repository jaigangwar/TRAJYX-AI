/**
 * Sign-in.
 *
 * Presented as an operations-console login: a single panel, the product
 * identity, and honest reporting of what backend the deployment is running.
 * No marketing copy, no illustration, no gradient.
 */

import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { defaultRouteForRole } from "@/app/navigation";
import { TrajyxMark } from "@/components/brand/Logo";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { isStaff } from "@/features/auth/types";
import { useHealth } from "@/features/system/api";
import { ApiError } from "@/lib/api-client";

export function LoginPage() {
  const { status, role, signIn, signInError, isSigningIn } = useAuth();
  const { data: health } = useHealth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);

  useEffect(() => {
    document.title = "Sign in · TRAJYX";
  }, []);

  // Already signed in: go where this role belongs.
  if (status === "authenticated" && role) {
    const intended = (location.state as { from?: string } | null)?.from;
    const destination = intended && isStaff(role) ? intended : defaultRouteForRole(role);
    return <Navigate to={destination} replace />;
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await signIn(email.trim(), password, remember);
      // Destination is decided by the redirect above once status flips.
      navigate(location.pathname, { replace: true, state: location.state });
    } catch {
      // Rendered from signInError; nothing to do here.
    }
  };

  return (
    <div className="bg-ground flex min-h-dvh items-center justify-center p-4">
      <div className="w-full max-w-[380px]">
        <div className="mb-6 flex flex-col items-center text-center">
          <TrajyxMark size={44} className="text-ink" title="TRAJYX" />
          <h1 className="text-ink mt-3 text-[19px] font-semibold tracking-[0.16em]">TRAJYX</h1>
          <p className="text-ink-subtle mt-1 text-2xs tracking-[0.06em] uppercase">
            Predictive Road Safety &amp; Traffic Intelligence
          </p>
        </div>

        <form onSubmit={handleSubmit} className="panel p-5">
          <h2 className="text-ink mb-4 text-sm font-semibold">Sign in</h2>

          {signInError ? <SignInError error={signInError} /> : null}

          <div className="space-y-3">
            <div>
              <label htmlFor="email" className="field-label">
                Email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                required
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="border-line bg-surface-sunken text-ink focus:border-accent h-8 w-full rounded-sm border px-2.5 text-xs outline-none"
              />
            </div>

            <div>
              <label htmlFor="password" className="field-label">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="border-line bg-surface-sunken text-ink focus:border-accent h-8 w-full rounded-sm border px-2.5 text-xs outline-none"
              />
            </div>

            <label className="text-ink-muted flex cursor-pointer items-center gap-2 text-xs select-none">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                className="accent-accent size-3.5"
              />
              Keep me signed in on this device
            </label>
          </div>

          <Button
            type="submit"
            variant="primary"
            className="mt-4 h-8 w-full"
            loading={isSigningIn}
            disabled={!email || !password}
          >
            Sign in
          </Button>
        </form>

        {health ? <DeploymentNotice health={health} /> : null}
      </div>
    </div>
  );
}

function SignInError({ error }: { error: unknown }) {
  const isApiError = error instanceof ApiError;
  const message = isApiError
    ? error.message
    : "Sign-in failed. Check that the TRAJYX API is reachable.";

  return (
    <div
      role="alert"
      className="border-risk-critical/40 bg-risk-critical-dim mb-4 flex items-start gap-2 rounded-sm border p-2.5"
    >
      <Icon name="alert" size={14} className="text-risk-critical mt-px shrink-0" />
      <p className="text-risk-critical text-xs">{message}</p>
    </div>
  );
}

/**
 * States which backend the deployment is using, and — when no account exists
 * yet — how to create the first administrator. An empty deployment with no
 * visible way in is a dead end.
 */
function DeploymentNotice({ health }: { health: NonNullable<ReturnType<typeof useHealth>["data"]> }) {
  const localAuth = health.capabilities.auth_backend === "local";

  return (
    <div className="mt-4 space-y-3">
      <div className="flex items-center justify-center gap-1.5">
        {health.capabilities.demo_mode ? <Badge tone="accent">Demo mode</Badge> : null}
        <Badge tone={localAuth ? "neutral" : "info"}>
          {localAuth ? "Local auth" : "Firebase auth"}
        </Badge>
        {health.environment !== "production" ? (
          <Badge tone="neutral">{health.environment}</Badge>
        ) : null}
      </div>

      {localAuth ? (
        <p className="text-ink-subtle text-center text-2xs leading-relaxed">
          This deployment uses local development accounts. Create the first administrator with{" "}
          <code className="mono text-ink-muted">python scripts/seed_admin.py</code>.
        </p>
      ) : null}
    </div>
  );
}
