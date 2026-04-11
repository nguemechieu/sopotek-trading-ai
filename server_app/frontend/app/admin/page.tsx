import Link from "next/link";
import { redirect } from "next/navigation";

import { AdminUserManagementPanel } from "@/components/admin/admin-user-management";
import { MetricCard } from "@/components/panels/metric-card";
import { SectionCard } from "@/components/panels/section-card";
import { StatusPill } from "@/components/panels/status-pill";
import { formatCompactNumber } from "@/lib/format";
import { loadLicenseAdminOverview } from "@/lib/license-admin";
import { requireServerSession } from "@/lib/server-session";

const adminSections = [
  {
    title: "Workspace Control",
    href: "/dashboard",
    detail: "Configure broker routing, account bindings, risk budgets, and signed-in workspace defaults.",
    badge: "enabled",
  },
  {
    title: "Strategy Operations",
    href: "/strategies",
    detail: "Enable, pause, and review strategy allocations, assignments, and live trading posture.",
    badge: "enabled",
  },
  {
    title: "Orders & Execution",
    href: "/orders",
    detail: "Inspect fills, open orders, lifecycle events, and operator-facing execution logs.",
    badge: "enabled",
  },
  {
    title: "Risk Controls",
    href: "/risk",
    detail: "Adjust desk-level drawdown, exposure, and alert handling across the platform.",
    badge: "enabled",
  },
  {
    title: "Terminal Oversight",
    href: "/terminal",
    detail: "Access the integrated terminal for guided trading, execution, and runtime operator workflows.",
    badge: "enabled",
  },
  {
    title: "Market Monitoring",
    href: "/market",
    detail: "Watch live price structure, watchlists, and market-state surfaces the trading desk depends on.",
    badge: "active",
  },
  {
    title: "License Administration",
    href: "/admin/licenses",
    detail: "Issue, suspend, and review desktop and web entitlements from the shared license ledger.",
    badge: "admin",
  },
  {
    title: "User Administration",
    href: "/admin/users",
    detail: "Create admin users, promote operators, and manage access state from a dedicated control page.",
    badge: "admin",
  },
];

export default async function AdminPage() {
  const session = await requireServerSession();
  if (session.user.role !== "admin") {
    redirect("/dashboard");
  }

  const overview = await loadLicenseAdminOverview(session.accessToken);
  const activeLicenses = overview.items.filter((item) => item.status === "active").length;
  const suspendedLicenses = overview.items.filter((item) => item.status === "suspended").length;
  const suspiciousLicenses = overview.items.filter((item) => item.suspicious_events > 0).length;
  const totalDevices = overview.items.reduce((sum, item) => sum + item.active_devices, 0);
  const verifiedUsers = overview.users.filter((item) => item.email_verified).length;
  const adminUsers = overview.users.filter((item) => item.role === "admin").length;

  return (
    <div className="space-y-6">
      <SectionCard
        eyebrow="Admin Control Center"
        title="Run the platform from one place, with direct control over workspace access, trading surfaces, and entitlements."
        rightSlot={<StatusPill value="admin" />}
      >
        <div className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-[24px] border border-white/10 bg-black/10 p-5">
            <p className="text-xs uppercase tracking-[0.3em] text-mist/45">Admin Reach</p>
            <p className="mt-3 text-2xl font-semibold text-sand">
              {session.user.full_name || session.user.username}
            </p>
            <p className="mt-3 text-sm leading-6 text-mist/68">
              Admin operators can manage every surface already exposed through the shared web platform:
              workspace configuration, strategies, orders, risk controls, the integrated terminal, license entitlements, and user access.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-mist">
                {session.user.email_verified ? "verified operator" : "verification pending"}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-mist">
                {adminUsers} admin accounts
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-mist">
                {formatCompactNumber(overview.users.length)} total users
              </span>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-[24px] border border-lime-400/20 bg-lime-400/10 p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-lime-100/70">Admin Priority</p>
              <p className="mt-3 text-lg font-semibold text-lime-50">Keep operators, licenses, and trading controls aligned.</p>
              <p className="mt-3 text-sm leading-6 text-lime-100/75">
                Use this page as the entry point, then jump into the exact desk workflow that needs action.
              </p>
            </div>
            <div className="rounded-[24px] border border-amber-300/20 bg-amber-300/10 p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-amber-100/70">Latest Snapshot</p>
              <p className="mt-3 text-lg font-semibold text-amber-50">
                {new Date(overview.generated_at).toLocaleString()}
              </p>
              <p className="mt-3 text-sm leading-6 text-amber-100/75">
                License and user telemetry shown below is sourced from the live backend overview.
              </p>
            </div>
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Users" value={formatCompactNumber(overview.users.length)} hint={`${verifiedUsers} verified`} />
        <MetricCard label="Active Licenses" value={formatCompactNumber(activeLicenses)} hint={`${suspendedLicenses} suspended`} tone={activeLicenses >= suspendedLicenses ? "good" : "warn"} />
        <MetricCard label="Bound Devices" value={formatCompactNumber(totalDevices)} hint="Desktop validations currently attached" />
        <MetricCard label="Suspicious Usage" value={formatCompactNumber(suspiciousLicenses)} hint="Licenses with suspicious event counts" tone={suspiciousLicenses > 0 ? "warn" : "good"} />
      </div>

      <SectionCard
        eyebrow="Management Surfaces"
        title="Admins can manage every major platform area from these entry points."
        rightSlot={<StatusPill value="enabled" />}
      >
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {adminSections.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-[24px] border border-white/10 bg-white/5 p-5 transition hover:border-amber-300/40 hover:bg-amber-300/8"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-lg font-semibold text-sand">{item.title}</p>
                  <p className="mt-3 text-sm leading-6 text-mist/66">{item.detail}</p>
                </div>
                <StatusPill value={item.badge} />
              </div>
              <p className="mt-4 text-xs uppercase tracking-[0.26em] text-mist/40">{item.href}</p>
            </Link>
          ))}
        </div>
      </SectionCard>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SectionCard
          eyebrow="Entitlements"
          title="License health across desktop and web access."
          rightSlot={<StatusPill value={suspiciousLicenses > 0 ? "watching" : "healthy"} />}
        >
          <div className="space-y-3">
            {overview.items.slice(0, 5).map((license) => (
              <div key={license.id} className="rounded-[22px] border border-white/10 bg-black/10 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-lg font-semibold text-sand">{license.user_full_name || license.user_username}</p>
                    <p className="mt-1 text-sm text-mist/60">{license.user_email}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusPill value={license.plan} />
                    <StatusPill value={license.status} />
                  </div>
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-3 text-sm">
                  <div>
                    <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Devices</p>
                    <p className="mt-1 font-semibold text-mist">
                      {license.active_devices} / {license.max_devices}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Validations</p>
                    <p className="mt-1 font-semibold text-mist">{formatCompactNumber(license.validation_count)}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Suspicious Events</p>
                    <p className="mt-1 font-semibold text-mist">{formatCompactNumber(license.suspicious_events)}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          eyebrow="Operator Accounts"
          title="Which accounts currently hold platform-wide admin responsibility."
          rightSlot={<StatusPill value={adminUsers > 1 ? "active" : "pending"} />}
        >
          <div className="space-y-3">
            {overview.users
              .filter((item) => item.role === "admin")
              .map((user) => (
                <div key={user.id} className="rounded-[22px] border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-lg font-semibold text-sand">{user.full_name || user.username}</p>
                      <p className="mt-1 text-sm text-mist/60">{user.email}</p>
                    </div>
                    <StatusPill value={user.is_active ? "active" : "paused"} />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <StatusPill value={user.role} />
                    <StatusPill value={user.email_verified ? "active" : "pending"} />
                    {user.current_license_plan ? <StatusPill value={user.current_license_plan} /> : null}
                  </div>
                </div>
              ))}
          </div>
        </SectionCard>
      </div>

      <AdminUserManagementPanel initialOverview={overview} />
    </div>
  );
}
