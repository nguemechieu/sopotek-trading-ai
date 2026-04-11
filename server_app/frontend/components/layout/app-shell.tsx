"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { BrandLockup } from "@/components/layout/brand-lockup";
import { CopyrightNotice } from "@/components/layout/copyright-notice";
import { Navigation } from "@/components/layout/navigation";
import { clearAuthSession, readAuthSession } from "@/lib/auth";
import { AUTH_CHANGE_EVENT, AUTH_ROUTE_PREFIXES, type AuthSession } from "@/lib/auth-shared";
import { loadWorkspaceManifest, type WorkspaceManifest, type WorkspaceNavigationEntry } from "@/lib/workspace-manifest";

const fallbackNavigation: WorkspaceNavigationEntry[] = [
  {
    id: "dashboard",
    href: "/dashboard",
    label: "Control Panel",
    detail: "Portfolio, watchlist, AI signals, notifications, and launch parameters.",
    roles: ["admin", "trader", "viewer"],
    required_features: ["workspace"],
    visible: true,
    writable: true,
    status: "enabled"
  }
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);
  const [workspaceManifest, setWorkspaceManifest] = useState<WorkspaceManifest | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const isAuthRoute = AUTH_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  useEffect(() => {
    const syncSession = () => setSession(readAuthSession());
    syncSession();
    window.addEventListener("storage", syncSession);
    window.addEventListener(AUTH_CHANGE_EVENT, syncSession);
    return () => {
      window.removeEventListener("storage", syncSession);
      window.removeEventListener(AUTH_CHANGE_EVENT, syncSession);
    };
  }, []);

  useEffect(() => {
    if (isAuthRoute || !session) {
      setWorkspaceManifest(null);
      setManifestError(null);
      return;
    }
    let active = true;
    loadWorkspaceManifest()
      .then((payload) => {
        if (!active) {
          return;
        }
        setWorkspaceManifest(payload);
        setManifestError(null);
      })
      .catch((error) => {
        if (!active) {
          return;
        }
        setWorkspaceManifest(null);
        setManifestError(error instanceof Error ? error.message : "Unable to load workspace manifest.");
      });
    return () => {
      active = false;
    };
  }, [isAuthRoute, session]);

  useEffect(() => {
    if (isAuthRoute || !workspaceManifest) {
      return;
    }
    const allowedPaths = new Set(workspaceManifest.navigation.filter((item) => item.visible).map((item) => item.href));
    if (!allowedPaths.size || allowedPaths.has(pathname)) {
      return;
    }
    router.replace(workspaceManifest.default_route || "/dashboard");
  }, [isAuthRoute, pathname, router, workspaceManifest]);

  const sessionLabel = session?.user.full_name || session?.user.username || "Session active";
  const navigation = workspaceManifest?.navigation?.length ? workspaceManifest.navigation : fallbackNavigation;
  const pageMeta =
    navigation.find((item) => item.href === pathname) ?? {
      id: "workspace",
      href: pathname,
      label: "Sopotek Platform",
      detail: "Institutional multi-asset trading control plane.",
      roles: ["admin", "trader", "viewer"],
      required_features: ["workspace"],
      visible: true,
      writable: false,
      status: "enabled" as const
    };
  const visibleNavigation = navigation.filter((item) => item.visible);
  const featureCount = workspaceManifest?.available_features?.length ?? 0;
  const workspaceStatus = manifestError ? "degraded" : workspaceManifest ? "live" : "standby";

  if (isAuthRoute) {
    return <>{children}</>;
  }

  function handleSignOut() {
    clearAuthSession();
    setSession(null);
    setWorkspaceManifest(null);
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="relative min-h-screen overflow-hidden px-3 py-3 md:px-5 md:py-5 xl:px-6">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top,rgba(214,164,108,0.08),transparent_40%),radial-gradient(circle_at_85%_10%,rgba(115,197,231,0.08),transparent_24%)]" />

      <div className="mx-auto grid max-w-[1820px] gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="panel flex min-h-[calc(100vh-1.5rem)] flex-col rounded-[32px] px-5 py-5 xl:sticky xl:top-5 xl:max-h-[calc(100vh-2.5rem)]">
          <div className="border-b border-white/8 pb-5">
            <BrandLockup size="sm" subtitle="Institutional Desktop" />
            <h1 className="display-headline mt-4 text-[2.15rem] font-semibold leading-none text-sand">Server Desk</h1>
            <p className="mt-3 max-w-xs text-sm leading-6 text-mist/62">
              Trading posture, command execution, and operator context in one desktop frame.
            </p>
          </div>

          <div className="mt-5 rounded-[24px] border border-white/8 bg-white/[0.03] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="eyebrow">Operator Session</p>
                <p className="mt-3 text-lg font-semibold text-sand">{sessionLabel}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.24em] text-mist/44">
                  {workspaceManifest?.role || session?.user.role || "guest"}
                </p>
              </div>
              <StatusBadge state={workspaceStatus} label={manifestError ? "degraded" : "connected"} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <DesktopStat label="Routes" value={String(visibleNavigation.length)} />
              <DesktopStat label="Features" value={String(featureCount)} />
              <DesktopStat label="Version" value={workspaceManifest?.platform_version || "fallback"} />
              <DesktopStat
                label="License"
                value={workspaceManifest?.license_plan || workspaceManifest?.license_status || "workspace"}
              />
            </div>
          </div>

          <div className="mt-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="eyebrow">Navigation</p>
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[10px] uppercase tracking-[0.24em] text-mist/45">
                role aware
              </span>
            </div>
            <Navigation items={navigation} />
          </div>

          <div className="mt-6 rounded-[24px] border border-white/8 bg-black/10 p-4">
            <p className="eyebrow">Workspace Feed</p>
            <div className="mt-4 space-y-3 text-sm text-mist/64">
              {(workspaceManifest?.recent_updates?.slice(0, 3) || [
                "Manifest-backed navigation stays in sync with your workspace role.",
                "Dashboard, market, risk, and terminal now share one desktop shell.",
                "Use the terminal route for assisted execution and runtime inspection.",
              ]).map((item) => (
                <div key={item} className="rounded-[18px] border border-white/8 bg-white/[0.03] px-3 py-3">
                  {item}
                </div>
              ))}
            </div>
          </div>

          <div className="mt-auto border-t border-white/8 pt-5">
            {session ? (
              <button type="button" onClick={handleSignOut} className="action-button-secondary w-full">
                Sign out
              </button>
            ) : (
              <div className="flex gap-3">
                <Link href="/login" className="action-button-primary flex-1">
                  Sign in
                </Link>
                <Link href="/register" className="action-button-secondary flex-1">
                  Register
                </Link>
              </div>
            )}
            <CopyrightNotice className="mt-4" />
          </div>
        </aside>

        <div className="min-w-0 space-y-4">
          <header className="panel rounded-[30px] px-5 py-5 md:px-6 md:py-6">
            <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
              <div>
                <p className="eyebrow">Workspace Desktop</p>
                <h2 className="display-headline mt-3 text-[clamp(2.35rem,3vw,4.1rem)] font-semibold leading-[0.94] text-sand">
                  {pageMeta.label}
                </h2>
                <p className="mt-4 max-w-3xl text-sm leading-7 text-mist/66">{pageMeta.detail}</p>

                <div className="mt-5 flex flex-wrap gap-2">
                  <StatusBadge state={workspaceStatus} label={manifestError ? "degraded" : "workspace live"} />
                  <StatusBadge
                    state={pageMeta.writable ? "active" : "standby"}
                    label={pageMeta.writable ? "write enabled" : "read only"}
                  />
                  <StatusBadge
                    state={session?.user.email_verified ? "active" : "warning"}
                    label={session?.user.email_verified ? "verified identity" : "verify email"}
                  />
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <HeaderTile
                  eyebrow="Operator"
                  title={sessionLabel}
                  detail={`Role ${workspaceManifest?.role || session?.user.role || "guest"} on ${pageMeta.status} route`}
                />
                <HeaderTile
                  eyebrow="Page Access"
                  title={pageMeta.writable ? "Interactive surface" : "Observation surface"}
                  detail={pageMeta.writable ? "Trade, configure, and launch actions are available." : "Monitoring only until a writable role signs in."}
                />
                <HeaderTile
                  eyebrow="Runtime"
                  title="FastAPI + terminal + live state"
                  detail="Shared command semantics across dashboard, market, risk, orders, and terminal."
                />
                <HeaderTile
                  eyebrow="Platform"
                  title={workspaceManifest?.license_plan || "Workspace Desktop"}
                  detail={workspaceManifest?.license_status || "Manifest-linked workspace routing is active."}
                />
              </div>
            </div>

            {manifestError ? (
              <div className="mt-5 rounded-[20px] border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                {manifestError}
              </div>
            ) : null}
          </header>

          <main className="space-y-4">{children}</main>
        </div>
      </div>
    </div>
  );
}

function DesktopStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[18px] border border-white/8 bg-black/10 px-3 py-3">
      <p className="text-[10px] uppercase tracking-[0.24em] text-mist/42">{label}</p>
      <p className="mt-2 text-sm font-semibold text-sand">{value}</p>
    </div>
  );
}

function HeaderTile({
  eyebrow,
  title,
  detail,
}: {
  eyebrow: string;
  title: string;
  detail: string;
}) {
  return (
    <div className="rounded-[24px] border border-white/8 bg-white/[0.03] px-4 py-4">
      <p className="eyebrow !tracking-[0.24em]">{eyebrow}</p>
      <p className="mt-3 text-lg font-semibold text-sand">{title}</p>
      <p className="mt-2 text-sm leading-6 text-mist/58">{detail}</p>
    </div>
  );
}

function StatusBadge({
  state,
  label,
}: {
  state: "active" | "live" | "standby" | "warning" | "degraded" | string;
  label?: string;
}) {
  const normalized = String(state || "").toLowerCase();
  const tone =
    normalized === "active" || normalized === "live"
      ? "border-lime-400/28 bg-lime-400/10 text-lime-100"
      : normalized === "warning" || normalized === "standby"
        ? "border-amber-400/28 bg-amber-400/10 text-amber-100"
        : normalized === "connected" || normalized === "viewer" || normalized === "trader" || normalized === "admin"
          ? "border-sky-300/24 bg-sky-300/10 text-sky-100"
          : "border-rose-400/28 bg-rose-400/10 text-rose-100";

  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] uppercase tracking-[0.24em] ${tone}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-90" />
      {label || state}
    </span>
  );
}
