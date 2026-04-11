import { AuthPage } from "@/components/auth/auth-page";
import { redirectIfAuthenticated } from "@/lib/server-session";

export default async function LoginPage({
  searchParams
}: {
  searchParams: Promise<{ verify_token?: string }>;
}) {
  await redirectIfAuthenticated();
  const resolvedSearchParams = await searchParams;
  return <AuthPage mode="login" initialVerifyToken={resolvedSearchParams.verify_token ?? ""} />;
}
