import { redirect } from "next/navigation";

import { readServerSession, resolveServerWorkspaceRoute } from "@/lib/server-session";

export default async function HomePage() {
  const session = await readServerSession();
  redirect(session ? await resolveServerWorkspaceRoute(session) : "/login");
}
