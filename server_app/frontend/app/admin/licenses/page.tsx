import { redirect } from "next/navigation";

import { LicenseAdminConsole } from "@/components/admin/license-admin-console";
import { loadLicenseAdminOverview } from "@/lib/license-admin";
import { requireServerSession } from "@/lib/server-session";

export default async function AdminLicensesPage() {
  const session = await requireServerSession();
  if (session.user.role !== "admin") {
    redirect("/dashboard");
  }

  const overview = await loadLicenseAdminOverview(session.accessToken);

  return <LicenseAdminConsole initialOverview={overview} />;
}
