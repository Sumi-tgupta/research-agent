"use client";

import { useEffect } from "react";
import { initClientErrorMonitoring } from "@/lib/observability";

/**
 * Mounts the optional, dependency-free client error monitor and renders
 * nothing. A no-op unless NEXT_PUBLIC_SENTRY_DSN is set (see
 * lib/observability.ts). Kept as its own client component so app/providers.tsx
 * stays declarative.
 */
export function ErrorMonitor() {
  useEffect(() => {
    initClientErrorMonitoring();
  }, []);
  return null;
}
