type StatusPillProps = {
  value: string;
};

export function StatusPill({ value }: StatusPillProps) {
  const normalized = value.toLowerCase();
  const positiveStates = new Set([
    "enabled",
    "filled",
    "working",
    "online",
    "healthy",
    "connected",
    "armed",
    "high",
    "active",
    "verified",
    "ready",
    "configured",
    "live",
    "positive",
    "assisted",
  ]);
  const cautionStates = new Set([
    "paused",
    "pending",
    "watching",
    "paper",
    "idle",
    "medium",
    "admin",
    "trader",
    "viewer",
    "free",
    "pro",
    "elite",
    "preview",
    "warning",
    "info",
    "standby",
    "manual",
    "paper",
    "watching",
  ]);
  const neutralStates = new Set(["demo", "viewer", "trader", "admin"]);
  const tone =
    positiveStates.has(normalized)
      ? "border-lime-400/28 bg-lime-400/10 text-lime-100"
      : cautionStates.has(normalized)
        ? "border-amber-400/28 bg-amber-400/10 text-amber-100"
        : neutralStates.has(normalized)
          ? "border-sky-300/24 bg-sky-300/10 text-sky-100"
          : "border-rose-400/28 bg-rose-400/10 text-rose-100";

  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] uppercase tracking-[0.24em] ${tone}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-90" />
      {value}
    </span>
  );
}
