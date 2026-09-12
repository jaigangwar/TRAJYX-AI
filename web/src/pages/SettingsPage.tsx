/** Settings: user administration plus deployment state. */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Icon } from "@/components/ui/Icon";
import { Panel } from "@/components/ui/Panel";
import { ErrorState } from "@/components/ui/StateBlock";
import { useAuth } from "@/features/auth/auth-context";
import { ROLE_LABELS, userSchema, type User } from "@/features/auth/types";
import { useHealth } from "@/features/system/api";
import { usePageHeader } from "@/hooks/usePageHeader";
import { api } from "@/lib/api-client";
import { formatTimestamp } from "@/lib/format";
import { ALERT_DEFAULTS, ROLE_VALUES, type Role } from "@shared/domain";

const usersPage = z.object({
  items: z.array(userSchema),
  next_cursor: z.string().nullable().optional(),
});

function useUsers() {
  return useQuery({
    queryKey: ["users"],
    queryFn: ({ signal }) => api.get("/users", { query: { limit: 200 }, schema: usersPage, signal }),
  });
}

export function SettingsPage() {
  const users = useUsers();
  const health = useHealth();
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);

  const setRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) =>
      api.patch(`/users/${id}/role`, { body: { role }, schema: userSchema }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch(`/users/${id}/status`, { body: { status }, schema: userSchema }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  usePageHeader(
    "Settings",
    "Users, roles and deployment configuration",
    <Button
      size="sm"
      variant="primary"
      icon={<Icon name="user" size={13} />}
      onClick={() => setCreating(true)}
    >
      Add user
    </Button>,
  );

  const columns: Column<User>[] = [
    {
      key: "email",
      header: "Account",
      sortValue: (row) => row.email,
      cell: (row) => (
        <span>
          <span className="text-ink font-medium">{row.display_name || row.email}</span>
          {row.display_name ? (
            <span className="text-ink-subtle ml-1.5 text-2xs">{row.email}</span>
          ) : null}
          {row.id === me?.id ? (
            <Badge tone="accent" className="ml-1.5">
              you
            </Badge>
          ) : null}
        </span>
      ),
    },
    {
      key: "role",
      header: "Role",
      width: "160px",
      sortValue: (row) => row.role,
      cell: (row) => (
        <select
          value={row.role}
          disabled={setRole.isPending}
          onChange={(event) =>
            setRole.mutate({ id: row.id, role: event.target.value as Role })
          }
          className="border-line bg-surface-sunken text-ink h-6 rounded-sm border px-1.5 text-xs"
        >
          {ROLE_VALUES.map((role) => (
            <option key={role} value={role}>
              {ROLE_LABELS[role]}
            </option>
          ))}
        </select>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "100px",
      sortValue: (row) => row.status,
      cell: (row) => (
        <Badge tone={row.status === "active" ? "low" : "offline"}>{row.status}</Badge>
      ),
    },
    {
      key: "last_login",
      header: "Last sign-in",
      width: "130px",
      sortValue: (row) => row.last_login_at ?? null,
      cell: (row) => formatTimestamp(row.last_login_at),
    },
    {
      key: "actions",
      header: "",
      width: "100px",
      align: "right",
      cell: (row) =>
        row.id === me?.id ? null : (
          <Button
            size="sm"
            variant={row.status === "active" ? "secondary" : "primary"}
            loading={setStatus.isPending}
            onClick={() =>
              setStatus.mutate({
                id: row.id,
                status: row.status === "active" ? "suspended" : "active",
              })
            }
          >
            {row.status === "active" ? "Suspend" : "Reinstate"}
          </Button>
        ),
    },
  ];

  return (
    <div className="space-y-3 p-4">
      {setRole.error ? <ErrorState error={setRole.error} title="Could not change the role" /> : null}
      {setStatus.error ? (
        <ErrorState error={setStatus.error} title="Could not change the status" />
      ) : null}

      <Panel title="Users" meta={users.data ? `${users.data.items.length}` : undefined} flush>
        <DataTable
          columns={columns}
          rows={users.data?.items}
          rowKey={(row) => row.id}
          isLoading={users.isLoading}
          error={users.error}
          onRetry={() => void users.refetch()}
          emptyMessage="No users found."
          defaultSort="email"
          defaultDescending={false}
        />
      </Panel>

      {creating ? <CreateUser onClose={() => setCreating(false)} /> : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="Deployment">
          {health.data ? (
            <dl className="space-y-2">
              <Row label="Environment" value={health.data.environment} />
              <Row label="API version" value={health.data.version} mono />
              <Row label="Contract" value={health.data.contract_version} mono />
              <Row label="Data backend" value={health.data.capabilities.data_backend} />
              <Row label="Auth backend" value={health.data.capabilities.auth_backend} />
              <Row label="Object storage" value={health.data.capabilities.storage_backend} />
              <Row label="Demo mode" value={health.data.capabilities.demo_mode ? "enabled" : "disabled"} />
            </dl>
          ) : (
            <p className="text-ink-subtle text-xs">Loading…</p>
          )}
          <p className="text-ink-subtle mt-3 text-2xs leading-relaxed">
            Backends are selected by environment variable. See{" "}
            <code className="mono">backend/.env.example</code>. Editing them from the interface is
            deliberately not supported: a running service must not be able to switch its own data
            store.
          </p>
        </Panel>

        <Panel title="Driver alert thresholds" meta="defaults">
          <p className="text-ink-muted mb-3 text-xs">
            The contract defaults the driver app uses. Per-deployment tuning arrives with the alert
            engine in phase 14; these values are shown read-only until then.
          </p>
          <dl className="space-y-2">
            <Row label="Level 1 minimum risk" value={String(ALERT_DEFAULTS.level_1_min_risk)} />
            <Row label="Level 2 minimum risk" value={String(ALERT_DEFAULTS.level_2_min_risk)} />
            <Row label="Level 3 minimum risk" value={String(ALERT_DEFAULTS.level_3_min_risk)} />
            <Row
              label="Approach distance"
              value={`${ALERT_DEFAULTS.approach_distance_m.LEVEL_1} / ${ALERT_DEFAULTS.approach_distance_m.LEVEL_2} / ${ALERT_DEFAULTS.approach_distance_m.LEVEL_3} m`}
            />
            <Row label="Bearing tolerance" value={`${ALERT_DEFAULTS.bearing_tolerance_deg}°`} />
            <Row
              label="Cooldown"
              value={`${ALERT_DEFAULTS.cooldown_seconds.LEVEL_1} / ${ALERT_DEFAULTS.cooldown_seconds.LEVEL_2} / ${ALERT_DEFAULTS.cooldown_seconds.LEVEL_3} s`}
            />
          </dl>
        </Panel>
      </div>
    </div>
  );
}

function CreateUser({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<Role>("TRAFFIC_OPERATOR");

  const create = useMutation({
    mutationFn: () =>
      api.post("/users", {
        body: { email, password, display_name: displayName || null, role },
        schema: userSchema,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
  });

  return (
    <Panel title="Add user">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
        className="space-y-3"
      >
        {create.error ? <ErrorState error={create.error} title="Could not create the user" /> : null}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <label className="block">
            <span className="field-label">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none"
            />
          </label>
          <label className="block">
            <span className="field-label">Password</span>
            <input
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none"
            />
          </label>
          <label className="block">
            <span className="field-label">Name</span>
            <input
              type="text"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none"
            />
          </label>
          <label className="block">
            <span className="field-label">Role</span>
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
              className="border-line bg-surface-sunken text-ink focus:border-accent h-7 w-full rounded-sm border px-2 text-xs outline-none"
            >
              {ROLE_VALUES.map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="text-ink-subtle text-2xs">
          At least 10 characters, combining two of: lowercase, uppercase, digits, symbols.
        </p>

        <div className="flex gap-2">
          <Button type="submit" variant="primary" loading={create.isPending}>
            Create user
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-subtle text-2xs">{label}</dt>
      <dd className={`text-ink text-xs font-medium ${mono ? "mono" : ""}`}>{value}</dd>
    </div>
  );
}
