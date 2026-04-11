import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  applicationName: "Sopotek Trading AI",
  title: "Sopotek Trading AI Platform",
  description: "Professional multi-user trading control plane backed by FastAPI, Kafka, and realtime market streams.",
  icons: {
    icon: [
      { url: "/favicon.ico", type: "image/x-icon" },
      { url: "/sopotek-logo.png", type: "image/png" },
    ],
    shortcut: "/favicon.ico",
    apple: "/sopotek-logo.png",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-ink font-[var(--font-sans)] text-mist antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
