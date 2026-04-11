"use client";

import { FormEvent, useState, useTransition } from "react";

import { SectionCard } from "@/components/panels/section-card";
import { StatusPill } from "@/components/panels/status-pill";
import { readAuthToken } from "@/lib/auth";
import {
  issueAdminLicense,
  loadLicenseAdminOverview,
  type LicenseAdminEntry,
  type LicenseAdminOverview,
  type LicensePlan,
  type LicensePlanOption,
  type LicenseStatus,
  updateAdminLicense,
} from "@/lib/license-admin";

const inputClass =
  "w-full rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist outline-none transition placeholder:text-mist/35 focus:border-amber-300/45";
const buttonClass =
  "rounded-full border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-sm text-sand transition hover:border-amber-300/50 hover:bg-amber-300/14 disabled:cursor-not-allowed disabled:opacity-60";
const mutedButtonClass =
  "rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-mist/80 transition hover:border-white/20 hover:text-mist disabled:cursor-not-allowed disabled:opacity-60";

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Not set";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function toDatetimeLocalValue(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

type LicenseRowProps = {
  license: LicenseAdminEntry;
  plans: LicensePlanOption[];
  onLicenseUpdated: () => Promise<void>;
};

function LicenseRow({ license, plans, onLicenseUpdated }: LicenseRowProps) {
  const [plan, setPlan] = useState<LicensePlan>(license.plan);
  const [status, setStatus] = useState<LicenseStatus>(license.status);
  const [maxDevices, setMaxDevices] = useState<string>(String(license.max_devices));
  const [expiresAt, setExpiresAt] = useState<string>(toDatetimeLocalValue(license.expires_at));
  const [clearExpiresAt, setClearExpiresAt] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    const token = readAuthToken();
    if (!token) {
      setError("Your session expired. Sign in again.");
      return;
    }

    try {
      await updateAdminLicense(token, license.id, {
        plan,
        status,
        max_devices: maxDevices.trim() ? Number(maxDevices) : null,
        expires_at: clearExpiresAt ? null : expiresAt ? new Date(expiresAt).toISOString() : null,
        clear_expires_at: clearExpiresAt,
      });
      setMessage("License settings saved.");
      startTransition(() => {
        void onLicenseUpdated();
      });
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Unable to save the license.");
    }
  }

  return (
    <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-xl font-semibold text-sand">
              {license.user_full_name || license.user_username}
            </h3>
            <StatusPill value={license.plan} />
            <StatusPill value={license.status} />
          </div>
          <p className="mt-2 text-sm text-mist/68">
            {license.user_email} | {license.license_key_masked}
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Validation</p>
            <p className="mt-2 font-semibold text-sand">
              {license.active_devices}/{license.max_devices} devices
            </p>
            <p className="mt-1 text-mist/66">{license.validation_count} checks</p>
          </div>
          <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
            <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Risk Flags</p>
            <p className="mt-2 font-semibold text-sand">{license.suspicious_events} suspicious events</p>
            <p className="mt-1 text-mist/66">{license.failed_validation_count} failed validations</p>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Last Validated</p>
          <p className="mt-2 text-mist">{formatTimestamp(license.last_validated_at)}</p>
        </div>
        <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Client Version</p>
          <p className="mt-2 text-mist">{license.last_validated_version || "Unknown"}</p>
        </div>
        <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Expires</p>
          <p className="mt-2 text-mist">{formatTimestamp(license.expires_at)}</p>
        </div>
        <div className="rounded-[18px] border border-white/10 bg-white/5 px-4 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Subscription</p>
          <p className="mt-2 text-mist">{license.subscription_status || "internal"}</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {license.features.map((feature) => (
          <span key={feature} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.2em] text-mist/72">
            {feature}
          </span>
        ))}
      </div>

      <form className="mt-5 grid gap-4 lg:grid-cols-[1fr_1fr_1fr_1fr_auto]" onSubmit={handleSubmit}>
        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Plan</span>
          <select className={inputClass} value={plan} onChange={(event) => setPlan(event.target.value as LicensePlan)}>
            {plans.map((option) => (
              <option key={option.plan} value={option.plan}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Status</span>
          <select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value as LicenseStatus)}>
            {["active", "suspended", "expired", "revoked"].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Max Devices</span>
          <input
            className={inputClass}
            inputMode="numeric"
            min={1}
            max={100}
            type="number"
            value={maxDevices}
            onChange={(event) => setMaxDevices(event.target.value)}
          />
        </label>

        <label className="text-sm text-mist/68">
          <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Expires At</span>
          <input
            className={inputClass}
            type="datetime-local"
            value={expiresAt}
            disabled={clearExpiresAt}
            onChange={(event) => setExpiresAt(event.target.value)}
          />
          <span className="mt-2 flex items-center gap-2 text-xs text-mist/55">
            <input
              checked={clearExpiresAt}
              type="checkbox"
              onChange={(event) => setClearExpiresAt(event.target.checked)}
            />
            Clear expiry
          </span>
        </label>

        <div className="flex items-end">
          <button className={buttonClass} disabled={isPending} type="submit">
            {isPending ? "Saving..." : "Save License"}
          </button>
        </div>
      </form>

      {message ? <p className="mt-3 text-sm text-lime-300">{message}</p> : null}
      {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}

      <div className="mt-5 rounded-[22px] border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Bound Devices</p>
        <div className="mt-3 space-y-3">
          {license.devices.length ? (
            license.devices.map((device) => (
              <div key={device.id} className="rounded-[18px] border border-white/10 bg-black/10 px-4 py-3 text-sm text-mist/72">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-[var(--font-mono)] text-sand">{device.device_hash_masked}</p>
                  <StatusPill value={device.is_active ? "active" : "revoked"} />
                </div>
                <p className="mt-2">{device.app_version} | {device.validation_count} validations</p>
                <p className="mt-1 text-mist/55">
                  IP {device.last_ip || "unknown"} | Updated {formatTimestamp(device.updated_at)}
                </p>
              </div>
            ))
          ) : (
            <p className="text-sm text-mist/55">No devices have validated against this license yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function LicenseAdminConsole({ initialOverview }: { initialOverview: LicenseAdminOverview }) {
  const [overview, setOverview] = useState<LicenseAdminOverview>(initialOverview);
  const [selectedUserId, setSelectedUserId] = useState<string>(initialOverview.users[0]?.id || "");
  const [plan, setPlan] = useState<LicensePlan>(initialOverview.plans[0]?.plan || "free");
  const [status, setStatus] = useState<LicenseStatus>("active");
  const [maxDevices, setMaxDevices] = useState<string>("");
  const [expiresAt, setExpiresAt] = useState<string>("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latestLicenseKey, setLatestLicenseKey] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function refreshOverview() {
    const token = readAuthToken();
    if (!token) {
      setError("Your session expired. Sign in again.");
      return;
    }
    const nextOverview = await loadLicenseAdminOverview(token);
    startTransition(() => {
      setOverview(nextOverview);
      if (!selectedUserId && nextOverview.users[0]?.id) {
        setSelectedUserId(nextOverview.users[0].id);
      }
    });
  }

  async function handleIssueLicense(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setError(null);
    setLatestLicenseKey(null);
    const token = readAuthToken();
    if (!token) {
      setError("Your session expired. Sign in again.");
      return;
    }
    try {
      const issued = await issueAdminLicense(token, {
        user_id: selectedUserId,
        plan,
        status,
        max_devices: maxDevices.trim() ? Number(maxDevices) : null,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      });
      setLatestLicenseKey(issued.license_key);
      setNotice(`Issued ${issued.plan.toUpperCase()} license for ${issued.user_email}.`);
      await refreshOverview();
    } catch (issueError) {
      setError(issueError instanceof Error ? issueError.message : "Unable to issue the license.");
    }
  }

  const activeLicenses = overview.items.filter((item) => item.status === "active").length;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-[24px] border border-white/10 bg-white/5 p-5">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Issued Licenses</p>
          <p className="mt-3 text-3xl font-semibold text-sand">{overview.items.length}</p>
        </div>
        <div className="rounded-[24px] border border-white/10 bg-white/5 p-5">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Active Licenses</p>
          <p className="mt-3 text-3xl font-semibold text-sand">{activeLicenses}</p>
        </div>
        <div className="rounded-[24px] border border-white/10 bg-white/5 p-5">
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Registered Users</p>
          <p className="mt-3 text-3xl font-semibold text-sand">{overview.users.length}</p>
        </div>
      </div>

      <SectionCard
        eyebrow="License Issuance"
        title="Bind desktop verification and web entitlements to one admin-managed license ledger."
        rightSlot={<StatusPill value="admin" />}
      >
        <form className="grid gap-4 xl:grid-cols-[1.35fr_0.85fr_0.85fr_0.7fr_0.95fr_auto]" onSubmit={handleIssueLicense}>
          <label className="text-sm text-mist/68">
            <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">User</span>
            <select
              className={inputClass}
              value={selectedUserId}
              onChange={(event) => setSelectedUserId(event.target.value)}
            >
              {overview.users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name || user.username} | {user.email}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm text-mist/68">
            <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Plan</span>
            <select className={inputClass} value={plan} onChange={(event) => setPlan(event.target.value as LicensePlan)}>
              {overview.plans.map((option) => (
                <option key={option.plan} value={option.plan}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm text-mist/68">
            <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Status</span>
            <select className={inputClass} value={status} onChange={(event) => setStatus(event.target.value as LicenseStatus)}>
              {["active", "suspended", "expired", "revoked"].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm text-mist/68">
            <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Max Devices</span>
            <input
              className={inputClass}
              inputMode="numeric"
              min={1}
              max={100}
              placeholder="Plan default"
              type="number"
              value={maxDevices}
              onChange={(event) => setMaxDevices(event.target.value)}
            />
          </label>

          <label className="text-sm text-mist/68">
            <span className="mb-2 block text-xs uppercase tracking-[0.24em] text-mist/45">Expires At</span>
            <input
              className={inputClass}
              type="datetime-local"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
          </label>

          <div className="flex items-end gap-3">
            <button className={buttonClass} disabled={isPending || !selectedUserId} type="submit">
              Issue / Reissue
            </button>
            <button
              className={mutedButtonClass}
              disabled={isPending}
              type="button"
              onClick={() => {
                startTransition(() => {
                  void refreshOverview();
                });
              }}
            >
              Refresh
            </button>
          </div>
        </form>

        {latestLicenseKey ? (
          <div className="mt-4 rounded-[22px] border border-lime-400/25 bg-lime-400/10 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-lime-100/70">Issued Key</p>
            <p className="mt-2 font-[var(--font-mono)] text-sm text-lime-50">{latestLicenseKey}</p>
            <p className="mt-2 text-sm text-lime-100/80">
              Copy this key into the desktop license dialog. It is only shown in full immediately after issuance.
            </p>
          </div>
        ) : null}
        {notice ? <p className="mt-4 text-sm text-lime-300">{notice}</p> : null}
        {error ? <p className="mt-4 text-sm text-rose-300">{error}</p> : null}
      </SectionCard>

      <SectionCard
        eyebrow="License Ledger"
        title="Audit, rotate, and control the entitlements the desktop and platform clients are allowed to use."
        rightSlot={<p className="text-sm text-mist/55">Updated {formatTimestamp(overview.generated_at)}</p>}
      >
        <div className="space-y-4">
          {overview.items.length ? (
            overview.items.map((license) => (
              <LicenseRow
                key={`${license.id}-${license.updated_at}`}
                license={license}
                plans={overview.plans}
                onLicenseUpdated={refreshOverview}
              />
            ))
          ) : (
            <div className="rounded-[22px] border border-white/10 bg-black/10 p-4 text-sm text-mist/66">
              No licenses exist yet. Issue one above to bind a user to desktop verification and platform access.
            </div>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
