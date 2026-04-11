import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AUTH_COOKIE_NAME, type AuthUser } from "@/lib/auth-shared";

const apiBaseUrl = process.env.SOPOTEK_API_BASE_URL ?? process.env.NEXT_PUBLIC_SOPOTEK_API_BASE_URL ?? "http://127.0.0.1:8000";
const fallbackWorkspaceRoute = "/dashboard";

export type ServerSession = {
  accessToken: string;
  user: AuthUser;
};

type ServerWorkspaceManifest = {
  default_route?: string;
  navigation?: Array<{
    href: string;
    visible: boolean;
  }>;
};

async function fetchCurrentUser(token: string): Promise<AuthUser | null> {
  try {
    const response = await fetch(`${apiBaseUrl}/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`
      },
      cache: "no-store"
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as AuthUser;
  } catch {
    return null;
  }
}

async function fetchWorkspaceManifest(token: string): Promise<ServerWorkspaceManifest | null> {
  try {
    const response = await fetch(`${apiBaseUrl}/workspace/manifest`, {
      headers: {
        Authorization: `Bearer ${token}`
      },
      cache: "no-store"
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as ServerWorkspaceManifest;
  } catch {
    return null;
  }
}

export async function readServerSession(): Promise<ServerSession | null> {
  const cookieStore = await cookies();
  const accessToken = cookieStore.get(AUTH_COOKIE_NAME)?.value?.trim();
  if (!accessToken) {
    return null;
  }

  const user = await fetchCurrentUser(accessToken);
  if (!user) {
    return null;
  }

  return { accessToken, user };
}

export async function requireServerSession(): Promise<ServerSession> {
  const session = await readServerSession();
  if (!session) {
    redirect("/login");
  }
  return session;
}

export async function resolveServerWorkspaceRoute(session?: ServerSession | null): Promise<string> {
  const resolvedSession = session ?? (await readServerSession());
  if (!resolvedSession) {
    return "/login";
  }

  const manifest = await fetchWorkspaceManifest(resolvedSession.accessToken);
  const visibleRoutes = new Set(
    (manifest?.navigation || [])
      .filter((item) => item.visible && Boolean(item.href))
      .map((item) => item.href)
  );
  const defaultRoute = (manifest?.default_route || "").trim() || fallbackWorkspaceRoute;
  if (!visibleRoutes.size || visibleRoutes.has(defaultRoute)) {
    return defaultRoute;
  }
  return visibleRoutes.has(fallbackWorkspaceRoute) ? fallbackWorkspaceRoute : Array.from(visibleRoutes)[0] || fallbackWorkspaceRoute;
}

export async function redirectIfAuthenticated(): Promise<void> {
  const session = await readServerSession();
  if (session) {
    redirect(await resolveServerWorkspaceRoute(session));
  }
}
