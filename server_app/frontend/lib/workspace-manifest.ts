"use client";

import { readAuthToken } from "@/lib/auth";
import type { UserRole } from "@/lib/auth-shared";

const apiBaseUrl = process.env.NEXT_PUBLIC_SOPOTEK_API_BASE_URL ?? "http://127.0.0.1:8000";

export type WorkspaceNavigationEntry = {
  id: string;
  href: string;
  label: string;
  detail: string;
  roles: UserRole[];
  required_features: string[];
  visible: boolean;
  writable: boolean;
  status: "enabled" | "preview" | "locked";
};

export type WorkspaceManifest = {
  default_route: string;
  role: UserRole;
  license_plan?: "free" | "pro" | "elite" | null;
  license_status?: "active" | "suspended" | "expired" | "revoked" | null;
  available_features: string[];
  navigation: WorkspaceNavigationEntry[];
  recent_updates: string[];
  platform_version: string;
};

export async function loadWorkspaceManifest(): Promise<WorkspaceManifest> {
  const token = readAuthToken();
  if (!token) {
    throw new Error("Your session expired. Sign in again to load the workspace.");
  }
  const response = await fetch(`${apiBaseUrl}/workspace/manifest`, {
    headers: {
      Authorization: `Bearer ${token}`
    },
    cache: "no-store"
  });
  const payload = (await response.json().catch(() => null)) as { detail?: string } | WorkspaceManifest | null;
  if (!response.ok) {
    throw new Error((payload as { detail?: string } | null)?.detail || "Unable to load workspace manifest.");
  }
  return payload as WorkspaceManifest;
}
