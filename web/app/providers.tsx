"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import type { ReactNode } from "react";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ErrorMonitor } from "@/components/observability/error-monitor";

/**
 * App-wide client providers.
 * - next-themes drives the .dark class the Emerald Horizon tokens hang off.
 * - AuthProvider exposes the (optional) Supabase session; anonymous when unconfigured.
 * - sonner renders toasts (used for copy/download/save feedback).
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem
      disableTransitionOnChange
    >
      <AuthProvider>
        {/* Optional, dependency-free error monitoring; no-op without a DSN. */}
        <ErrorMonitor />
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast:
                "glass-strong !rounded-xl !border-border !text-foreground !font-sans",
              description: "!text-muted-foreground",
            },
          }}
        />
      </AuthProvider>
    </ThemeProvider>
  );
}
