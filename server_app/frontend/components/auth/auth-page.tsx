 "use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState, useTransition } from "react";

import { BrandLockup } from "@/components/layout/brand-lockup";
import { CopyrightNotice } from "@/components/layout/copyright-notice";
import {
  clearAuthSession,
  loginUser,
  persistAuthSession,
  registerUser,
  requestPasswordReset,
  resetPassword,
  verifyEmailToken
} from "@/lib/auth";
import type { AuthSession, UserRole } from "@/lib/auth-shared";

type AuthMode = "login" | "register" | "forgot-password" | "reset-password";

type AuthPageProps = {
  mode: AuthMode;
  initialToken?: string;
  initialVerifyToken?: string;
};

type ModeContent = {
  eyebrow: string;
  title: string;
  description: string;
  action: string;
  supportLabel: string;
  supportHref: string;
  supportText: string;
  secondaryLabel: string;
  secondaryHref: string;
  secondaryText: string;
  highlights: { label: string; value: string }[];
};

const contentByMode: Record<AuthMode, ModeContent> = {
  login: {
    eyebrow: "Operator Access",
    title: "Sign in to the Sopotek trading control plane.",
    description: "Validate desk credentials, restore your permissions, and move directly into the control center and integrated trading terminal.",
    action: "Sign In",
    supportLabel: "Need access?",
    supportHref: "/register",
    supportText: "Create a desk account",
    secondaryLabel: "Password issue",
    secondaryHref: "/forgot-password",
    secondaryText: "Reset your credentials",
    highlights: [
      { label: "Realtime control", value: "Kafka-backed command and event flow" },
      { label: "Desk oversight", value: "Portfolio, strategy, and execution views in one workspace" },
      { label: "Layered security", value: "JWT sessions, rate limiting, email verification, and optional 2FA" }
    ]
  },
  register: {
    eyebrow: "Desk Onboarding",
    title: "Create a new operating seat for the platform.",
    description: "Provision a trader or viewer account, accept the desk terms, and move into the same control center the desktop platform uses.",
    action: "Create Account",
    supportLabel: "Already onboarded?",
    supportHref: "/login",
    supportText: "Sign in instead",
    secondaryLabel: "Password support",
    secondaryHref: "/forgot-password",
    secondaryText: "Recover access",
    highlights: [
      { label: "First user wins", value: "The first account is promoted to admin automatically" },
      { label: "Role-aware access", value: "Trader and viewer access starts at account creation" },
      { label: "Workspace ready", value: "A default portfolio and strategy profile are provisioned immediately" }
    ]
  },
  "forgot-password": {
    eyebrow: "Credential Recovery",
    title: "Prepare a secure password reset for your desk account.",
    description: "We generate a short-lived reset token. In non-production environments the reset preview is surfaced immediately so you can keep moving.",
    action: "Send Reset Link",
    supportLabel: "Remembered it?",
    supportHref: "/login",
    supportText: "Go back to sign in",
    secondaryLabel: "Need a new account?",
    secondaryHref: "/register",
    secondaryText: "Create one now",
    highlights: [
      { label: "Short-lived tokens", value: "Reset links expire automatically" },
      { label: "Operator-safe flow", value: "Responses do not reveal whether an email exists" },
      { label: "Dev preview", value: "Local and staging builds can expose the reset link directly" }
    ]
  },
  "reset-password": {
    eyebrow: "Password Reset",
    title: "Set a fresh credential and return to the control center.",
    description: "Paste a reset token or open this page from a reset link. A successful reset signs you back in automatically.",
    action: "Reset Password",
    supportLabel: "Token missing?",
    supportHref: "/forgot-password",
    supportText: "Request a new reset link",
    secondaryLabel: "Back to auth",
    secondaryHref: "/login",
    secondaryText: "Return to sign in",
    highlights: [
      { label: "Instant recovery", value: "Successful resets issue a new platform session" },
      { label: "UTC token control", value: "Expiry is enforced server-side" },
      { label: "Desk continuity", value: "No manual reprovisioning or profile recovery is required" }
    ]
  }
};

function Field({
  id,
  label,
  type = "text",
  value,
  onChange,
  placeholder,
  autoComplete,
  required = true
}: {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="auth-label">{label}</span>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required={required}
        className="auth-input mt-2"
      />
    </label>
  );
}

function HighlightList({ items }: { items: ModeContent["highlights"] }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {items.map((item) => (
        <div key={item.label} className="rounded-[24px] border border-white/10 bg-black/10 px-4 py-4">
          <p className="text-[11px] uppercase tracking-[0.28em] text-mist/45">{item.label}</p>
          <p className="mt-3 text-sm leading-6 text-mist/80">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function buildSuccessMessage(mode: AuthMode, session: AuthSession | null, fallback: string) {
  if (mode === "register" && session) {
    return `Account created for ${session.user.email}. Redirecting to the dashboard to configure the trading account.`;
  }
  if (mode === "login" && session) {
    return `Welcome back, ${session.user.full_name || session.user.username}. Redirecting to the dashboard to configure or review the trading account.`;
  }
  if (mode === "reset-password" && session) {
    return "Password updated and session restored. Redirecting to the dashboard.";
  }
  return fallback;
}

export function AuthPage({ mode, initialToken = "", initialVerifyToken = "" }: AuthPageProps) {
  const router = useRouter();
  const content = contentByMode[mode];
  const [isPending, startTransition] = useTransition();
  const [identifier, setIdentifier] = useState("");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("trader");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [token, setToken] = useState(initialToken);
  const [rememberMe, setRememberMe] = useState(true);
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewToken, setPreviewToken] = useState<string | null>(null);

  useEffect(() => {
    clearAuthSession();
  }, []);

  useEffect(() => {
    if (mode !== "login" || !initialVerifyToken) {
      return;
    }
    startTransition(async () => {
      try {
        const session = await verifyEmailToken(initialVerifyToken);
        persistAuthSession(session);
        setSuccessMessage("Email verified successfully. Redirecting to the dashboard.");
        router.replace("/dashboard");
        router.refresh();
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Unable to verify email.");
      }
    });
  }, [initialVerifyToken, mode, router]);

  function completeSession(session: AuthSession, fallbackMessage: string) {
    persistAuthSession(session);
    setSuccessMessage(buildSuccessMessage(mode, session, fallbackMessage));
    router.replace("/dashboard");
    router.refresh();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);
    setPreviewToken(null);
    setPreviewUrl(null);

    if ((mode === "register" || mode === "reset-password") && password !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    if (mode === "register" && !acceptTerms) {
      setErrorMessage("You must accept the terms to create an account.");
      return;
    }

    startTransition(async () => {
      try {
        if (mode === "login") {
          const session = await loginUser({
            identifier,
            password,
            remember_me: rememberMe,
            otp_code: otpCode || undefined
          });
          completeSession(session, "Signed in successfully.");
          return;
        }

        if (mode === "register") {
          const session = await registerUser({
            email,
            username,
            password,
            full_name: fullName,
            role,
            accept_terms: acceptTerms
          });
          if (session.email_verification_url) {
            setPreviewUrl(session.email_verification_url);
            setPreviewToken(session.email_verification_token ?? null);
          }
          completeSession(session, "Account created successfully.");
          return;
        }

        if (mode === "forgot-password") {
          const response = await requestPasswordReset(email);
          setSuccessMessage(response.message);
          setPreviewUrl(response.reset_url ?? null);
          setPreviewToken(response.reset_token ?? null);
          return;
        }

        const session = await resetPassword({ token, password });
        completeSession(session, "Password reset successfully.");
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to complete the auth flow.";
        setErrorMessage(message);
      }
    });
  }

  return (
    <div className="relative min-h-screen overflow-hidden px-5 py-5 md:px-8 md:py-8">
      <div className="pointer-events-none absolute inset-0 grid-lines opacity-15" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[24rem] bg-[radial-gradient(circle_at_top,rgba(251,146,60,0.22),transparent_58%)]" />
      <div className="pointer-events-none absolute right-0 top-16 h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,rgba(134,239,172,0.14),transparent_68%)] blur-3xl" />

      <div className="relative mx-auto grid min-h-[calc(100vh-2.5rem)] max-w-7xl gap-6 lg:grid-cols-[1.08fr_0.92fr]">
        <section className="flex flex-col justify-between rounded-[34px] border border-white/10 bg-black/10 px-6 py-7 shadow-[0_32px_90px_rgba(2,8,14,0.4)] backdrop-blur-sm md:px-8 md:py-9">
          <div>
            <BrandLockup />
            <div className="mt-6 max-w-2xl space-y-4">
              <p className="text-xs uppercase tracking-[0.3em] text-mist/45">{content.eyebrow}</p>
              <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-sand md:text-6xl md:leading-[1.02]">
                {content.title}
              </h1>
              <p className="max-w-xl text-base leading-7 text-mist/72 md:text-lg">{content.description}</p>
            </div>
          </div>

          <div className="space-y-6">
            <div className="flex flex-wrap gap-3">
              <Link href={content.supportHref} className="rounded-full border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-sm text-sand transition hover:border-amber-300/50 hover:bg-amber-300/14">
                {content.supportText}
              </Link>
              <Link href={content.secondaryHref} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-mist/78 transition hover:border-white/20 hover:text-mist">
                {content.secondaryText}
              </Link>
            </div>
            <HighlightList items={content.highlights} />
          </div>
        </section>

        <section className="panel flex h-full flex-col rounded-[34px] border border-white/12 px-6 py-7 md:px-8 md:py-8">
          <div className="mb-6">
            <p className="text-xs uppercase tracking-[0.3em] text-mist/45">{content.eyebrow}</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-sand">{content.action}</h2>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            {mode === "login" ? (
              <Field
                id="identifier"
                label="Email or Username"
                value={identifier}
                onChange={setIdentifier}
                placeholder="desk@sopotek.ai or fundtrader"
                autoComplete="username"
              />
            ) : null}

            {(mode === "register" || mode === "forgot-password") ? (
              <Field
                id="email"
                label="Email"
                type="email"
                value={email}
                onChange={setEmail}
                placeholder="desk@sopotek.ai"
                autoComplete="email"
              />
            ) : null}

            {mode === "register" ? (
              <>
                <Field
                  id="full-name"
                  label="Full Name"
                  value={fullName}
                  onChange={setFullName}
                  placeholder="Fund Trader"
                  autoComplete="name"
                />
                <Field
                  id="username"
                  label="Username"
                  value={username}
                  onChange={setUsername}
                  placeholder="fundtrader"
                  autoComplete="username"
                />
                <label className="block">
                  <span className="auth-label">Role</span>
                  <select
                    value={role}
                    onChange={(event) => setRole(event.target.value as UserRole)}
                    className="auth-input mt-2"
                  >
                    <option value="trader">Trader</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </label>
              </>
            ) : null}

            {(mode === "login" || mode === "register" || mode === "reset-password") ? (
              <Field
                id="password"
                label={mode === "reset-password" ? "New Password" : "Password"}
                type="password"
                value={password}
                onChange={setPassword}
                placeholder="Minimum 8 characters"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            ) : null}

            {mode === "login" ? (
              <>
                <Field
                  id="otp-code"
                  label="Authenticator Code"
                  value={otpCode}
                  onChange={setOtpCode}
                  placeholder="Optional unless 2FA is enabled"
                  autoComplete="one-time-code"
                  required={false}
                />
                <label className="flex items-center gap-3 rounded-[22px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/78">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                    className="h-4 w-4 rounded border-white/20 bg-white/5"
                  />
                  Keep this desk signed in on this device.
                </label>
              </>
            ) : null}

            {(mode === "register" || mode === "reset-password") ? (
              <Field
                id="confirm-password"
                label="Confirm Password"
                type="password"
                value={confirmPassword}
                onChange={setConfirmPassword}
                placeholder="Repeat the password"
                autoComplete="new-password"
              />
            ) : null}

            {mode === "register" ? (
              <label className="flex items-center gap-3 rounded-[22px] border border-white/10 bg-white/5 px-4 py-3 text-sm text-mist/78">
                <input
                  type="checkbox"
                  checked={acceptTerms}
                  onChange={(event) => setAcceptTerms(event.target.checked)}
                  className="h-4 w-4 rounded border-white/20 bg-white/5"
                />
                I accept the platform terms and understand this workspace may connect to live brokers.
              </label>
            ) : null}

            {mode === "reset-password" ? (
              <Field
                id="reset-token"
                label="Reset Token"
                value={token}
                onChange={setToken}
                placeholder="Paste the reset token or open a reset link"
                autoComplete="off"
              />
            ) : null}

            {errorMessage ? (
              <div className="rounded-[24px] border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                {errorMessage}
              </div>
            ) : null}

            {successMessage ? (
              <div className="rounded-[24px] border border-lime-400/30 bg-lime-400/10 px-4 py-3 text-sm text-lime-100">
                <p>{successMessage}</p>
                {previewUrl ? (
                  <div className="mt-3 space-y-2 text-lime-50/90">
                    <p className="text-xs uppercase tracking-[0.24em] text-lime-200/75">
                      {mode === "forgot-password" ? "Reset Link Preview" : "Verification Link Preview"}
                    </p>
                    <Link href={previewUrl} className="break-all text-sm text-lime-100 underline underline-offset-4">
                      {previewUrl}
                    </Link>
                    {previewToken ? <p className="font-[var(--font-mono)] text-xs text-lime-100/80">{previewToken}</p> : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <button type="submit" disabled={isPending} className="auth-submit">
              {isPending ? "Working..." : content.action}
            </button>
          </form>

          <div className="mt-6 space-y-3 border-t border-white/10 pt-5 text-sm text-mist/70">
            <p>
              {content.supportLabel}{" "}
              <Link href={content.supportHref} className="text-sand underline underline-offset-4">
                {content.supportText}
              </Link>
            </p>
            <p>
              {content.secondaryLabel}{" "}
              <Link href={content.secondaryHref} className="text-sand underline underline-offset-4">
                {content.secondaryText}
              </Link>
            </p>
            <CopyrightNotice />
          </div>
        </section>
      </div>
    </div>
  );
}
