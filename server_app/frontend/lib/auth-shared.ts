export const AUTH_COOKIE_NAME = "sopotek_platform_token";
export const AUTH_STORAGE_KEY = "sopotek-platform-session";
export const AUTH_CHANGE_EVENT = "sopotek-auth-change";
export const AUTH_ROUTE_PREFIXES = ["/login", "/register", "/forgot-password", "/reset-password"] as const;

export type UserRole = "admin" | "trader" | "viewer";

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  email_verified: boolean;
  two_factor_enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type AuthSession = {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
  expires_at?: string | null;
  refresh_expires_at?: string | null;
  remember_me?: boolean;
  verification_required?: boolean;
  email_verification_token?: string | null;
  email_verification_url?: string | null;
  user: AuthUser;
};

export type ForgotPasswordResponse = {
  message: string;
  reset_token?: string | null;
  reset_url?: string | null;
};
