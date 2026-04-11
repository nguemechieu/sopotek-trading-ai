"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { StatusPill } from "@/components/panels/status-pill";
import { readAuthToken } from "@/lib/auth";
import { startTradingSession, stopTradingSession } from "@/lib/trading-session";
import type { UserRole } from "@/lib/auth-shared";

const primaryButtonClass =
  "action-button-primary px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-55";
const mutedButtonClass =
  "action-button-secondary px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-55";

type TradingSessionControlsProps = {
  userRole: UserRole;
  tradingEnabled: boolean;
  credentialsReady: boolean;
  selectedSymbols: string[];
  terminalHref?: string;
  terminalLabel?: string;
  showTerminalLink?: boolean;
};

export function TradingSessionControls({
  userRole,
  tradingEnabled,
  credentialsReady,
  selectedSymbols,
  terminalHref = "/terminal",
  terminalLabel = "Launch Terminal",
  showTerminalLink = true,
}: TradingSessionControlsProps) {
  const router = useRouter();
  const [isPending, setIsPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canControl = userRole === "admin" || userRole === "trader";
  const resolvedSymbols = useMemo(
    () => Array.from(new Set(selectedSymbols.map((symbol) => String(symbol || "").trim().toUpperCase()).filter(Boolean))),
    [selectedSymbols],
  );

  async function handleAction(action: "start" | "stop") {
    setNotice(null);
    setError(null);
    setIsPending(true);

    const token = readAuthToken();
    if (!token) {
      setError("Your session expired. Sign in again.");
      setIsPending(false);
      return;
    }

    try {
      const payload =
        action === "start"
          ? await startTradingSession(token, resolvedSymbols)
          : await stopTradingSession(token, resolvedSymbols);
      const activeSymbols = payload.selected_symbols?.length
        ? payload.selected_symbols.join(", ")
        : "runtime defaults";
      setNotice(
        action === "start"
          ? `Session started. Symbols armed: ${activeSymbols}.`
          : `Session stopped. Symbols retained: ${activeSymbols}.`,
      );
      router.refresh();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Unable to update the trading session.");
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="mt-5 rounded-[24px] border border-white/8 bg-black/10 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-mist/45">Session Controls</p>
          <p className="mt-2 text-sm leading-6 text-mist/68">
            Start the server trading session from here to arm the runtime with this workspace profile and symbol set.
          </p>
        </div>
        <StatusPill value={tradingEnabled ? "active" : "paused"} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.18em] text-mist/74">
          {resolvedSymbols.length ? `${resolvedSymbols.length} symbols ready` : "runtime defaults"}
        </span>
        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.18em] text-mist/74">
          {credentialsReady ? "credentials ready" : "setup required"}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          className={primaryButtonClass}
          disabled={isPending || tradingEnabled || !canControl || !credentialsReady}
          onClick={() => {
            void handleAction("start");
          }}
        >
          {isPending && !tradingEnabled ? "Starting..." : "Start Session"}
        </button>
        <button
          type="button"
          className={mutedButtonClass}
          disabled={isPending || !tradingEnabled || !canControl}
          onClick={() => {
            void handleAction("stop");
          }}
        >
          {isPending && tradingEnabled ? "Stopping..." : "Stop Session"}
        </button>
        {showTerminalLink ? (
          <Link href={terminalHref} className={mutedButtonClass}>
            {terminalLabel}
          </Link>
        ) : null}
      </div>

      {!canControl ? (
        <p className="mt-3 text-sm text-amber-200">
          Viewer accounts can monitor the desk, but only trader or admin accounts can start a session.
        </p>
      ) : null}
      {canControl && !credentialsReady ? (
        <p className="mt-3 text-sm text-amber-200">
          Finish broker or paper workspace setup first, then start the session from this card.
        </p>
      ) : null}
      {notice ? <p className="mt-3 text-sm text-lime-300">{notice}</p> : null}
      {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
    </div>
  );
}
