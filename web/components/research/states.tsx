"use client";

import { AlertTriangle, RotateCcw, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function ErrorState({
  message,
  onRetry,
  onNewSearch,
}: {
  message: string;
  onRetry?: () => void;
  onNewSearch?: () => void;
}) {
  return (
    <div className="glass rounded-2xl border border-destructive/30 p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
          <AlertTriangle className="h-5 w-5" />
        </span>
        <div className="flex-1">
          <h3 className="font-display text-lg font-semibold">
            Research didn&apos;t finish
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">{message}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RotateCcw className="h-4 w-4" />
                Try again
              </Button>
            )}
            {onNewSearch && (
              <Button variant="ghost" size="sm" onClick={onNewSearch}>
                <Plus className="h-4 w-4" />
                New research
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ReportSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-2/3" />
      <div className="space-y-2.5">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-[96%]" />
        <Skeleton className="h-4 w-[90%]" />
        <Skeleton className="h-4 w-[93%]" />
      </div>
      <Skeleton className="mt-6 h-6 w-1/3" />
      <div className="space-y-2.5">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-[88%]" />
        <Skeleton className="h-4 w-[92%]" />
      </div>
    </div>
  );
}
