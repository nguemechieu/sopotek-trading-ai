"use client";

import Image from "next/image";

export function BrandLockup({
  title = "Sopotek Trading AI",
  subtitle,
  size = "md",
}: {
  title?: string;
  subtitle?: string;
  size?: "sm" | "md";
}) {
  const imageSize = size === "sm" ? 40 : 52;
  const titleClass = size === "sm" ? "text-[1.35rem]" : "text-[1.8rem]";
  const subtitleClass = size === "sm" ? "text-[11px]" : "text-xs";

  return (
    <div className="flex items-center gap-3">
      <div className="relative overflow-hidden rounded-[20px] border border-white/10 bg-white/[0.04] p-1.5 shadow-[0_18px_42px_rgba(3,10,18,0.36)]">
        <Image
          src="/sopotek-logo.png"
          alt="Sopotek Trading AI logo"
          width={imageSize}
          height={imageSize}
          priority
          className="rounded-[14px]"
        />
      </div>
      <div className="min-w-0">
        <p className={`${subtitleClass} uppercase tracking-[0.34em] text-amber-300/72`}>{subtitle || "Mission Control"}</p>
        <h1 className={`${titleClass} display-headline font-semibold text-sand`}>{title}</h1>
      </div>
    </div>
  );
}
