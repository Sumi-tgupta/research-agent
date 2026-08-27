"use client";

import { Check, Loader2, AlertTriangle, X, Circle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ResearchPhase, StageState } from "@/lib/use-research";

interface AgentTrackerProps {
  stages: StageState[];
  phase: ResearchPhase;
  elapsedMs: number;
  query: string;
  onCancel?: () => void;
  className?: string;
}

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 100) / 10;
  return `${total.toFixed(1)}s`;
}

export function AgentTracker({
  stages,
  phase,
  elapsedMs,
  query,
  onCancel,
  className,
}: AgentTrackerProps) {
  const running = phase === "running";
  const doneCount = stages.filter((s) => s.status === "done").length;
  const progress = Math.round((doneCount / stages.length) * 100);

  return (
    <div className={cn("glass rounded-2xl border border-border/70 p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {running ? "Researching" : phase === "complete" ? "Completed" : "Pipeline"}
          </p>
          <p className="mt-1 line-clamp-2 text-sm font-medium leading-snug">
            {query}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="tabular-nums text-sm text-muted-foreground">
            {formatElapsed(elapsedMs)}
          </span>
          {running && onCancel && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onCancel}
              aria-label="Cancel research"
              className="text-muted-foreground hover:text-destructive"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Progress rail */}
      <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-gradient-to-r from-primary to-aurora transition-[width] duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      <ol className="mt-5 space-y-1">
        {stages.map((stage, i) => {
          const hasError = stage.errors.length > 0;
          const isLast = i === stages.length - 1;
          return (
            <li key={stage.stage} className="relative flex gap-3 pb-3">
              {/* connector */}
              {!isLast && (
                <span
                  className={cn(
                    "absolute left-[13px] top-7 h-[calc(100%-1rem)] w-px",
                    stage.status === "done" ? "bg-primary/40" : "bg-border"
                  )}
                />
              )}
              <StageNode status={stage.status} hasError={hasError} />
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "text-sm font-medium transition-colors",
                      stage.status === "pending" && "text-muted-foreground",
                      stage.status === "active" && "text-foreground",
                      stage.status === "done" && "text-foreground"
                    )}
                  >
                    {stage.label}
                  </span>
                  {stage.status === "active" && (
                    <span className="text-xs text-accent">working…</span>
                  )}
                </div>
                {stage.summary && (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {stage.summary}
                  </p>
                )}
                {hasError && (
                  <p className="mt-1 flex items-start gap-1 text-xs text-destructive/90">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                    <span>{stage.errors.join("; ")}</span>
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StageNode({
  status,
  hasError,
}: {
  status: StageState["status"];
  hasError: boolean;
}) {
  return (
    <span
      className={cn(
        "relative z-10 flex h-[27px] w-[27px] shrink-0 items-center justify-center rounded-full border transition-colors",
        status === "done" &&
          !hasError &&
          "border-primary bg-primary/15 text-primary",
        status === "done" && hasError && "border-destructive/60 bg-destructive/10 text-destructive",
        status === "active" && "border-accent bg-accent/10 text-accent",
        status === "pending" && "border-border bg-background/60 text-muted-foreground"
      )}
    >
      {status === "done" && !hasError && <Check className="h-3.5 w-3.5" />}
      {status === "done" && hasError && <AlertTriangle className="h-3.5 w-3.5" />}
      {status === "active" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {status === "pending" && <Circle className="h-2 w-2 fill-current opacity-50" />}
    </span>
  );
}
