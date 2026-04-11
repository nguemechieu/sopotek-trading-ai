const apiBaseUrl = process.env.NEXT_PUBLIC_SOPOTEK_API_BASE_URL ?? process.env.SOPOTEK_API_BASE_URL ?? "http://127.0.0.1:8000";

export type LicensePlan = "free" | "pro" | "elite";
export type LicenseStatus = "active" | "suspended" | "expired" | "revoked";

export type LicenseAdminDevice = {
  id: string;
  device_hash_masked: string;
  app_version: string;
  last_ip: string | null;
  validation_count: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type LicenseAdminEntry = {
  id: string;
  user_id: string;
  user_email: string;
  user_username: string;
  user_full_name: string | null;
  user_role: string;
  user_is_active: boolean;
  plan: LicensePlan;
  status: LicenseStatus;
  license_key_masked: string;
  max_devices: number;
  active_devices: number;
  features: string[];
  expires_at: string | null;
  suspicious_events: number;
  failed_validation_count: number;
  validation_count: number;
  last_validated_at: string | null;
  last_validated_ip: string | null;
  last_validated_version: string | null;
  subscription_status: string | null;
  stripe_customer_id: string | null;
  created_at: string;
  updated_at: string;
  devices: LicenseAdminDevice[];
};

export type LicenseAdminUser = {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  email_verified: boolean;
  two_factor_enabled: boolean;
  current_license_id: string | null;
  current_license_plan: LicensePlan | null;
  current_license_status: LicenseStatus | null;
  created_at: string;
  updated_at: string;
};

export type LicensePlanOption = {
  plan: LicensePlan;
  label: string;
  billing_interval: string | null;
  max_devices: number;
  features: string[];
  price_id: string | null;
};

export type LicenseAdminOverview = {
  items: LicenseAdminEntry[];
  users: LicenseAdminUser[];
  plans: LicensePlanOption[];
  generated_at: string;
};

export type AdminLicenseIssuePayload = {
  user_id: string;
  plan: LicensePlan;
  status: LicenseStatus;
  max_devices?: number | null;
  expires_at?: string | null;
};

export type AdminLicenseUpdatePayload = {
  plan?: LicensePlan;
  status?: LicenseStatus;
  max_devices?: number | null;
  expires_at?: string | null;
  clear_expires_at?: boolean;
};

export type AdminLicenseIssueResponse = LicenseAdminEntry & {
  license_key: string;
};

export type AdminUserUpdatePayload = {
  role?: "admin" | "trader" | "viewer";
  is_active?: boolean;
  email_verified?: boolean;
  clear_two_factor_secret?: boolean;
};

export type AdminUserCreatePayload = {
  email: string;
  username: string;
  password: string;
  full_name?: string | null;
  role?: "admin" | "trader" | "viewer";
  is_active?: boolean;
  email_verified?: boolean;
};

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const detail = (payload as Record<string, unknown>).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  const message = (payload as Record<string, unknown>).message;
  if (typeof message === "string" && message.trim()) {
    return message;
  }
  return fallback;
}

async function requestJson<T>(path: string, init: RequestInit, fallbackMessage: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    cache: "no-store",
  });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    throw new Error(extractErrorMessage(payload, fallbackMessage));
  }
  return payload as T;
}

export async function loadLicenseAdminOverview(apiToken: string): Promise<LicenseAdminOverview> {
  return requestJson<LicenseAdminOverview>(
    "/api/license/admin/overview",
    {
      headers: {
        Authorization: `Bearer ${apiToken}`,
      },
    },
    "Unable to load the license admin overview.",
  );
}

export async function issueAdminLicense(apiToken: string, payload: AdminLicenseIssuePayload): Promise<AdminLicenseIssueResponse> {
  return requestJson<AdminLicenseIssueResponse>(
    "/api/license/admin/issue",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Unable to issue a license.",
  );
}

export async function updateAdminLicense(
  apiToken: string,
  licenseId: string,
  payload: AdminLicenseUpdatePayload,
): Promise<LicenseAdminEntry> {
  return requestJson<LicenseAdminEntry>(
    `/api/license/admin/${licenseId}`,
    {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Unable to update the license.",
  );
}

export async function updateAdminUser(
  apiToken: string,
  userId: string,
  payload: AdminUserUpdatePayload,
): Promise<LicenseAdminUser> {
  return requestJson<LicenseAdminUser>(
    `/api/admin/users/${userId}`,
    {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Unable to update the user.",
  );
}

export async function createAdminUser(
  apiToken: string,
  payload: AdminUserCreatePayload,
): Promise<LicenseAdminUser> {
  return requestJson<LicenseAdminUser>(
    "/api/admin/users",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Unable to create the user.",
  );
}
