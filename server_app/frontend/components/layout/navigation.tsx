"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { WorkspaceNavigationEntry } from "@/lib/workspace-manifest";

export function Navigation({ items }: { items: WorkspaceNavigationEntry[] }) {
  const pathname = usePathname();

  return (
    <nav className="space-y-2">
      {items.filter((item) => item.visible).map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`group relative block overflow-hidden rounded-[20px] border px-4 py-3.5 transition ${
              active
                ? "border-[rgba(214,164,108,0.34)] bg-[linear-gradient(135deg,rgba(214,164,108,0.14),rgba(115,197,231,0.08))] text-sand shadow-[0_16px_40px_rgba(5,10,18,0.24)]"
                : "border-white/8 bg-white/[0.025] text-mist/74 hover:border-white/16 hover:bg-white/[0.05] hover:text-mist"
            }`}
          >
            <span
              className={`absolute inset-y-3 left-0 w-[3px] rounded-r-full transition ${
                active ? "bg-[rgba(214,164,108,0.9)]" : "bg-transparent group-hover:bg-[rgba(214,164,108,0.45)]"
              }`}
            />
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold tracking-tight">{item.label}</p>
              <span
                className={`rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-[0.24em] ${
                  active
                    ? "border-[rgba(214,164,108,0.28)] bg-[rgba(214,164,108,0.1)] text-amber-100"
                    : "border-white/10 bg-white/[0.04] text-mist/42"
                }`}
              >
                {item.status}
              </span>
            </div>
            <p className="mt-1.5 pr-6 text-xs leading-5 text-mist/58">{item.detail}</p>
          </Link>
        );
      })}
    </nav>
  );
}
