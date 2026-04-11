import { ReactNode } from "react";

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "warn";
  footer?: ReactNode;
};

export function MetricCard({ label, value, hint, tone = "default", footer }: MetricCardProps) {
  const toneClass =
    tone === "good"
      ? "text-lime-200"
      : tone === "warn"
        ? "text-amber-200"
        : "text-sand";

  return (
    <section className="metric-shell rounded-[26px] px-5 py-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">{label}</p>
          {hint ? <p className="mt-3 max-w-[16rem] text-sm leading-6 text-mist/56">{hint}</p> : null}
        </div>
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 font-[var(--font-mono)] text-[10px] uppercase tracking-[0.24em] text-mist/48">
          live desk
        </span>
      </div>
      <p className={`data-value mt-6 text-[2.6rem] font-semibold leading-none ${toneClass}`}>{value}</p>
      {footer ? <div className="mt-5 border-t border-white/8 pt-4 text-sm text-mist/64">{footer}</div> : null}
    </section>
  );
}
