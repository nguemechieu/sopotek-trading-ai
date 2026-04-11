"use client";

import { FormEvent, useMemo, useState } from "react";

import { SectionCard } from "@/components/panels/section-card";
import { StatusPill } from "@/components/panels/status-pill";
import { readAuthToken } from "@/lib/auth";
import {
  createAdminUser,
  loadLicenseAdminOverview,
  type LicenseAdminOverview,
  type LicenseAdminUser,
  updateAdminUser,
} from "@/lib/license-admin";

const inputClass =
  "w-full rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist outline-none transition focus:border-amber-300/45";
const buttonClass =
  "rounded-full border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-sm text-sand transition hover:border-amber-300/50 hover:bg-amber-300/14 disabled:cursor-not-allowed disabled:opacity-60";
const mutedButtonClass =
  "rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-mist/80 transition hover:border-white/20 hover:text-mist disabled:cursor-not-allowed disabled:opacity-60";

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function normalizeRole(value: string): "admin" | "trader" | "viewer" {
  if (value === "admin" || value === "viewer") {
    return value;
  }
  return "trader";
}

function initialRoleCount(users: LicenseAdminUser[], role: "admin" | "trader" | "viewer"): number {
  return users.filter((item) => item.role === role).length;
}

type UserCardProps = {
  user: LicenseAdminUser;
  isOnlyActiveAdmin: boolean;
  onSaved: () => Promise<void>;
};

function UserManagementCard({ user, isOnlyActiveAdmin, onSaved }: UserCardProps) {
  const [role, setRole] = useState<"admin" | "trader" | "viewer">(normalizeRole(user.role));
  const [isActive, setIsActive] = useState<string>(user.is_active ? "active" : "paused");
  const [emailVerified, setEmailVerified] = useState<string>(user.email_verified ? "verified" : "pending");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setIsSaving(true);
    const token = readAuthToken();
    if (!token) {
      setError("Your session expired. Sign in again.");
      setIsSaving(false);
      return;
    }

    try {
      await updateAdminUser(token, user.id, {
        role,
        is_active: isActive === "active",
        email_verified: emailVerified === "verified",
      });
      setMessage("User settings saved.");
      await onSaved();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Unable to update the user.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleResetTwoFactor() {
    setError(null);
    setMessage(null);
    setIsSaving(true);
    const token = readAuthToken();
    if (!token) {
      setError("Your session expired. Sign in again.");
      setIsSaving(false);
      return;
    }

    try {
      await updateAdminUser(token, user.id, {
        clear_two_factor_secret: true,
      });
      setMessage("Two-factor authentication was reset.");
      await onSaved();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Unable to reset two-factor authentication.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-sand">{user.full_name || user.username}</h3>
            <StatusPill value={user.role} />
            <StatusPill value={user.is_active ? "active" : "paused"} />
            <StatusPill value={user.email_verified ? "verified" : "pending"} />
            {user.current_license_plan ? <StatusPill value={user.current_license_plan} /> : null}
          </div>
          <p className="mt-2 text-sm text-mist/66">{user.email}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Access</p>
            <p className="mt-2 font-semibold text-sand">{user.current_license_status || "unlicensed"}</p>
            <p className="mt-1 text-mist/66">{user.current_license_plan || "free"} plan</p>
          </div>
          <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Two Factor</p>
            <p className="mt-2 font-semibold text-sand">{user.two_factor_enabled ? "Enabled" : "Disabled"}</p>
            <p className="mt-1 text-mist/66">Updated {formatTimestamp(user.updated_at)}</p>
          </div>
        </div>
      </div>

      <form className="mt-5 grid gap-4 xl:grid-cols-[1fr_1fr_1fr_auto_auto]" onSubmit={handleSubmit}>
        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Role</span>
          <select className={inputClass} value={role} onChange={(event) => setRole(event.target.value as "admin" | "trader" | "viewer")}>
            {["admin", "trader", "viewer"].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Account</span>
          <select className={inputClass} value={isActive} onChange={(event) => setIsActive(event.target.value)}>
            <option value="active">active</option>
            <option value="paused">paused</option>
          </select>
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Email</span>
          <select className={inputClass} value={emailVerified} onChange={(event) => setEmailVerified(event.target.value)}>
            <option value="verified">verified</option>
            <option value="pending">pending</option>
          </select>
        </label>

        <div className="flex items-end">
          <button className={buttonClass} disabled={isSaving} type="submit">
            {isSaving ? "Saving..." : "Save User"}
          </button>
        </div>

        <div className="flex items-end">
          <button
            className={mutedButtonClass}
            disabled={isSaving || !user.two_factor_enabled}
            type="button"
            onClick={() => {
              void handleResetTwoFactor();
            }}
          >
            Reset 2FA
          </button>
        </div>
      </form>

      {isOnlyActiveAdmin ? (
        <p className="mt-3 text-sm text-amber-200">
          This is currently the only active admin account, so the backend will reject role removal or account deactivation.
        </p>
      ) : null}
      {message ? <p className="mt-3 text-sm text-lime-300">{message}</p> : null}
      {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
      <p className="mt-3 text-xs uppercase tracking-[0.24em] text-mist/40">
        Created {formatTimestamp(user.created_at)}
      </p>
    </div>
  );
}

function AdminUserCreationPanel({
  overview,
  onCreated,
}: {
  overview: LicenseAdminOverview;
  onCreated: () => Promise<void>;
}) {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "trader" | "viewer">("admin");
  const [isActive, setIsActive] = useState(true);
  const [emailVerified, setEmailVerified] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    setIsCreating(true);

    const token = readAuthToken();
    if (!token) {
      setError("Your session expired. Sign in again.");
      setIsCreating(false);
      return;
    }

    try {
      const created = await createAdminUser(token, {
        email,
        username,
        password,
        full_name: fullName || null,
        role,
        is_active: isActive,
        email_verified: emailVerified,
      });
      setNotice(`Created ${created.role} account for ${created.email}.`);
      setEmail("");
      setUsername("");
      setFullName("");
      setPassword("");
      setRole("admin");
      setIsActive(true);
      setEmailVerified(true);
      await onCreated();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create the user.");
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <SectionCard
      eyebrow="Create Operators"
      title="Create admin users and other operator accounts from the control plane instead of public signup."
      rightSlot={<StatusPill value="admin" />}
    >
      <div className="mb-5 grid gap-4 md:grid-cols-3">
        <div className="rounded-[22px] border border-white/10 bg-black/10 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Admins</p>
          <p className="mt-2 text-2xl font-semibold text-sand">{initialRoleCount(overview.users, "admin")}</p>
        </div>
        <div className="rounded-[22px] border border-white/10 bg-black/10 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Traders</p>
          <p className="mt-2 text-2xl font-semibold text-sand">{initialRoleCount(overview.users, "trader")}</p>
        </div>
        <div className="rounded-[22px] border border-white/10 bg-black/10 p-4">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Viewers</p>
          <p className="mt-2 text-2xl font-semibold text-sand">{initialRoleCount(overview.users, "viewer")}</p>
        </div>
      </div>

      <form className="grid gap-4 xl:grid-cols-3" onSubmit={handleSubmit}>
        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Email</span>
          <input className={inputClass} type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@sopotek.ai" required />
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Username</span>
          <input className={inputClass} value={username} onChange={(event) => setUsername(event.target.value)} placeholder="deskadmin" required />
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Full Name</span>
          <input className={inputClass} value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Desk Administrator" />
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Temporary Password</span>
          <input className={inputClass} type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Minimum 8 characters" required />
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Role</span>
          <select className={inputClass} value={role} onChange={(event) => setRole(normalizeRole(event.target.value))}>
            <option value="admin">admin</option>
            <option value="trader">trader</option>
            <option value="viewer">viewer</option>
          </select>
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex items-center gap-3 rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/80">
            <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} />
            Active on creation
          </label>
          <label className="flex items-center gap-3 rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/80">
            <input type="checkbox" checked={emailVerified} onChange={(event) => setEmailVerified(event.target.checked)} />
            Mark email verified
          </label>
        </div>

        <div className="xl:col-span-3 flex items-center gap-3">
          <button className={buttonClass} disabled={isCreating} type="submit">
            {isCreating ? "Creating..." : "Create User"}
          </button>
          <p className="text-sm text-mist/58">
            New users receive the default workspace plus a free license profile automatically.
          </p>
        </div>
      </form>

      {notice ? <p className="mt-4 text-sm text-lime-300">{notice}</p> : null}
      {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}
    </SectionCard>
  );
}

export function AdminUserManagementPanel({
  initialOverview,
  showCreation = true,
}: {
  initialOverview: LicenseAdminOverview;
  showCreation?: boolean;
}) {
  const [overview, setOverview] = useState<LicenseAdminOverview>(initialOverview);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const onlyActiveAdminId = useMemo(() => {
    const activeAdmins = overview.users.filter((item) => item.role === "admin" && item.is_active);
    return activeAdmins.length === 1 ? activeAdmins[0]?.id ?? null : null;
  }, [overview.users]);

  async function refreshOverview() {
    const token = readAuthToken();
    if (!token) {
      setPanelError("Your session expired. Sign in again.");
      return;
    }
    setIsRefreshing(true);
    try {
      const nextOverview = await loadLicenseAdminOverview(token);
      setOverview(nextOverview);
      setPanelError(null);
    } catch (refreshError) {
      setPanelError(refreshError instanceof Error ? refreshError.message : "Unable to refresh the admin overview.");
    } finally {
      setIsRefreshing(false);
    }
  }

  return (
    <div className="space-y-6">
      {showCreation ? <AdminUserCreationPanel overview={overview} onCreated={refreshOverview} /> : null}

      <SectionCard
        eyebrow="User & Access Control"
        title="Admins can manage every operator account from here, including roles, activation state, verification, and two-factor resets."
        rightSlot={<StatusPill value="admin" />}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="text-sm text-mist/62">
            Snapshot updated {formatTimestamp(overview.generated_at)}
          </p>
          <button
            className={mutedButtonClass}
            disabled={isRefreshing}
            type="button"
            onClick={() => {
              void refreshOverview();
            }}
          >
            {isRefreshing ? "Refreshing..." : "Refresh Users"}
          </button>
        </div>

        <div className="space-y-4">
          {overview.users.map((user) => (
            <UserManagementCard
              key={`${user.id}-${user.updated_at}`}
              user={user}
              isOnlyActiveAdmin={onlyActiveAdminId === user.id}
              onSaved={refreshOverview}
            />
          ))}
        </div>

        {panelError ? <p className="mt-4 text-sm text-rose-300">{panelError}</p> : null}
      </SectionCard>
    </div>
  );
}
