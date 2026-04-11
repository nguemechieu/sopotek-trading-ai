const apiBaseUrl =
  process.env.NEXT_PUBLIC_SOPOTEK_API_BASE_URL ??
  process.env.SOPOTEK_API_BASE_URL ??
  "http://127.0.0.1:8000";

type TradingSessionPayload = {
  selected_symbols: string[];
};

type TradingSessionResponse = {
  status: string;
  trading_enabled: boolean;
  selected_symbols: string[];
  runtime?: {
    active?: boolean;
    exchange?: string;
    mode?: string;
    selected_symbols?: string[];
  };
};

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const detail = (payload as Record<string, unknown>).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  return fallback;
}

async function requestControl(
  path: "/control/trading/start" | "/control/trading/stop",
  apiToken: string,
  payload: TradingSessionPayload,
): Promise<TradingSessionResponse> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const body = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    throw new Error(extractErrorMessage(body, "Unable to update the trading session."));
  }
  return body as TradingSessionResponse;
}

export async function startTradingSession(apiToken: string, selectedSymbols: string[]) {
  return requestControl("/control/trading/start", apiToken, {
    selected_symbols: selectedSymbols,
  });
}

export async function stopTradingSession(apiToken: string, selectedSymbols: string[]) {
  return requestControl("/control/trading/stop", apiToken, {
    selected_symbols: selectedSymbols,
  });
}
