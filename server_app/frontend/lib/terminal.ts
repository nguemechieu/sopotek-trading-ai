"use client";

import { readAuthToken } from "@/lib/auth";

const apiBaseUrl = process.env.NEXT_PUBLIC_SOPOTEK_API_BASE_URL ?? "http://127.0.0.1:8000";

export type TerminalAssistant = {
  headline: string;
  confidence: string;
  reason: string;
  risk_level: string;
  expected_duration: string;
};

export type TerminalCommandParameterSpec = {
  name: string;
  summary: string;
  required: boolean;
  default?: string | null;
  choices: string[];
};

export type TerminalCommandSpec = {
  command: string;
  summary: string;
  example: string;
  permission: string;
  parameters?: TerminalCommandParameterSpec[];
};

export type TerminalSessionSpec = {
  terminal_id: string;
  label: string;
  summary: string;
  kind: string;
  broker_label: string;
  account_label: string;
  mode: string;
  launch_href: string;
  primary: boolean;
};

export type TerminalResponse = {
  command_id: string;
  terminal_id: string;
  command: string;
  status: string;
  message: string;
  lines: string[];
  suggestions: string[];
  data: Record<string, unknown>;
  assistant?: TerminalAssistant | null;
  timestamp: string;
};

export type TerminalManifest = {
  active_terminal_id: string;
  active_terminal_label: string;
  workspace_key: string;
  broker_label: string;
  account_label: string;
  mode: string;
  terminals: TerminalSessionSpec[];
  commands: TerminalCommandSpec[];
  banners: string[];
  examples: string[];
  desktop_defaults?: Record<string, unknown>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = readAuthToken();
  if (!token) {
    throw new Error("Your session expired. Sign in again to use the terminal.");
  }
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {})
    }
  });
  const payload = (await response.json().catch(() => null)) as { detail?: string } | T | null;
  if (!response.ok) {
    throw new Error((payload as { detail?: string } | null)?.detail || "Terminal request failed.");
  }
  return payload as T;
}

export function loadTerminalManifest(terminalId?: string) {
  const query = terminalId ? `?terminal_id=${encodeURIComponent(terminalId)}` : "";
  return request<TerminalManifest>(`/terminal/manifest${query}`, { cache: "no-store" });
}

export function loadTerminalHistory(limit = 20, terminalId?: string) {
  const terminalQuery = terminalId ? `&terminal_id=${encodeURIComponent(terminalId)}` : "";
  return request<TerminalResponse[]>(`/terminal/history?limit=${limit}${terminalQuery}`, { cache: "no-store" });
}

export function executeTerminalCommand(command: string, terminalId?: string) {
  return request<TerminalResponse>("/terminal/execute", {
    method: "POST",
    body: JSON.stringify({ command, terminal_id: terminalId || null })
  });
}
