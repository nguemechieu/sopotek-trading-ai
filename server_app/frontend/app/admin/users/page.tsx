import { redirect } from "next/navigation";

import { AdminUserManagementPanel } from "@/components/admin/admin-user-management";
import { loadLicenseAdminOverview } from "@/lib/license-admin";
import { requireServerSession } from "@/lib/server-session";

export default async function AdminUsersPage() {
  const session = await requireServerSession();
  if (session.user.role !== "admin") {
    redirect("/dashboard");
  }

  const overview = await loadLicenseAdminOverview(session.accessToken);
  return <AdminUserManagementPanel initialOverview={overview} />;
}
