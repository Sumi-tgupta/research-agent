"use client";

import * as React from "react";
import { checkHealth, API_BASE_URL } from "@/lib/api";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Status = "checking" | "online" | "offline";

/** Small ambient indicator of whether the FastAPI backend is reachable. */
export function BackendStatus() {
  const [status, setStatus] = React.useState<Status>("checking");

  React.useEffect(() => {
    let active = true;
    const ping = async () => {
      const ok = await checkHealth();
      if (active) setStatus(ok ? "online" : "offline");
    };
    ping();
    const id = setInterval(ping, 30_000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const meta = {
    checking: { dot: "bg-muted-foreground animate-pulse", label: "Checking backend…" },
    online: { dot: "bg-primary shadow-[0_0_8px_2px_hsl(var(--primary)/0.6)]", label: "Backend online" },
    offline: { dot: "bg-destructive", label: "Backend offline" },
  }[status];

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="flex h-9 w-9 items-center justify-center rounded-md">
            <span className="relative flex h-2.5 w-2.5">
              <span className={cn("h-2.5 w-2.5 rounded-full", meta.dot)} />
            </span>
            <span className="sr-only">{meta.label}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[15rem]">
          <p className="font-medium">{meta.label}</p>
          <p className="mt-0.5 text-muted-foreground">
            {status === "offline"
              ? `Can't reach ${API_BASE_URL}. Start the API, then it'll reconnect automatically.`
              : API_BASE_URL}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
