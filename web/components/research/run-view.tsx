"use client";

import * as React from "react";
import { Repeat2 } from "lucide-react";
import { AgentTracker } from "./agent-tracker";
import { FollowUps } from "./follow-ups";
import { ResultActions } from "./result-actions";
import { ErrorState } from "./states";
import { ResultTabs, PlanCard } from "./result-tabs";
import type { ResearchPhase, StageState } from "@/lib/use-research";
import type { ResearchResult, ResearchRequest } from "@/lib/types";

interface RunViewProps {
  phase: ResearchPhase;
  stages: StageState[];
  elapsedMs: number;
  query: string;
  result: ResearchResult | null;
  error: string | null;
  onCancel: () => void;
  onNewSearch: () => void;
  onRetry: () => void;
  onFollowUp: (request: ResearchRequest) => void;
}

export function RunView({
  phase,
  stages,
  elapsedMs,
  query,
  result,
  error,
  onCancel,
  onNewSearch,
  onRetry,
  onFollowUp,
}: RunViewProps) {
  const complete = phase === "complete" && !!result;

  return (
    <div className="container grid gap-6 pb-24 pt-8 lg:grid-cols-12">
      {/* Left rail: tracker + plan + actions */}
      <aside className="lg:col-span-4 xl:col-span-3">
        <div className="lg:sticky lg:top-24 space-y-4">
          <AgentTracker
            stages={stages}
            phase={phase}
            elapsedMs={elapsedMs}
            query={query}
            onCancel={onCancel}
          />

          {complete && result && (
            <>
              <ResultActions result={result} onNewSearch={onNewSearch} />
              {result.revision_count > 0 && (
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Repeat2 className="h-3.5 w-3.5" />
                  Revised {result.revision_count} time
                  {result.revision_count === 1 ? "" : "s"} before approval
                </p>
              )}
            </>
          )}

          {result && result.plan.sub_questions.length > 0 && (
            <PlanCard
              subQuestions={result.plan.sub_questions.map((s) => s.question)}
            />
          )}
        </div>
      </aside>

      {/* Main column */}
      <div className="lg:col-span-8 xl:col-span-9 space-y-6">
        {phase === "error" && error ? (
          <ErrorState
            message={error}
            onRetry={onRetry}
            onNewSearch={onNewSearch}
          />
        ) : (
          <>
            {result && result.errors.length > 0 && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">
                  Some steps reported issues:{" "}
                </span>
                {result.errors.join("; ")}
              </div>
            )}

            <ResultTabs result={result} running={phase === "running"} />

            {complete && result && (
              <FollowUps
                query={result.query}
                subQuestions={result.plan.sub_questions}
                onFollowUp={(q) =>
                  onFollowUp({
                    query: q,
                    num_sub_questions: 4,
                    max_results_per_subquestion: 5,
                    citation_style: "apa",
                  })
                }
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
