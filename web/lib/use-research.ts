"use client";

import * as React from "react";
import {
  PIPELINE_STAGES,
  type ResearchRequest,
  type ResearchResult,
  type ResearchStreamEvent,
  type StageName,
} from "@/lib/types";
import { streamResearch, ApiError } from "@/lib/api";
import {
  setHorizonActivity,
  pulseHorizon,
  resetHorizon,
} from "@/lib/horizon-store";

export type ResearchPhase = "idle" | "running" | "complete" | "error";

export type StageStatus = "pending" | "active" | "done";

export interface StageState {
  stage: StageName;
  label: string;
  status: StageStatus;
  summary?: string;
  errors: string[];
}

export interface UseResearch {
  phase: ResearchPhase;
  stages: StageState[];
  activeStage: StageName | null;
  result: ResearchResult | null;
  error: string | null;
  query: string;
  elapsedMs: number;
  start: (request: ResearchRequest) => void;
  cancel: () => void;
  retry: () => void;
  reset: () => void;
}

function initialStages(): StageState[] {
  return PIPELINE_STAGES.map(({ stage, label }) => ({
    stage,
    label,
    status: "pending" as StageStatus,
    errors: [],
  }));
}

const STAGE_ORDER = PIPELINE_STAGES.map((s) => s.stage);

export function useResearch(): UseResearch {
  const [phase, setPhase] = React.useState<ResearchPhase>("idle");
  const [stages, setStages] = React.useState<StageState[]>(initialStages);
  const [activeStage, setActiveStage] = React.useState<StageName | null>(null);
  const [result, setResult] = React.useState<ResearchResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [query, setQuery] = React.useState("");
  const [elapsedMs, setElapsedMs] = React.useState(0);

  const abortRef = React.useRef<AbortController | null>(null);
  const timerRef = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = React.useRef<number>(0);
  const lastRequestRef = React.useRef<ResearchRequest | null>(null);

  const stopTimer = React.useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const onEvent = React.useCallback(
    (event: ResearchStreamEvent) => {
      if (event.type === "stage") {
        setStages((prev) => {
          const idx = prev.findIndex((s) => s.stage === event.stage);
          if (idx === -1) return prev;
          const next = [...prev];
          next[idx] = {
            ...next[idx],
            status: "done",
            summary: event.summary || next[idx].summary,
            errors: event.errors ?? [],
          };
          const afterIdx = STAGE_ORDER.indexOf(event.stage as StageName);
          let nextActive: StageName | null = null;
          for (let i = afterIdx + 1; i < next.length; i++) {
            if (next[i].status === "pending") {
              next[i] = { ...next[i], status: "active" };
              nextActive = next[i].stage;
              break;
            }
          }
          setActiveStage(nextActive);
          const done = next.filter((s) => s.status === "done").length;
          setHorizonActivity(0.25 + 0.6 * (done / next.length));
          pulseHorizon(1);
          return next;
        });
      } else if (event.type === "complete") {
        setResult(event.result);
        setPhase("complete");
        setActiveStage(null);
        setStages((prev) =>
          prev.map((s) => ({ ...s, status: "done" as StageStatus }))
        );
        stopTimer();
        pulseHorizon(2);
        setHorizonActivity(0.4);
        // Settle back to idle glow after the reveal.
        setTimeout(() => resetHorizon(), 4000);
      } else if (event.type === "error") {
        setError(event.message || "The research pipeline reported an error.");
        // Don't flip to error phase yet — a "complete" with partial state
        // usually follows and is more useful to show.
      }
    },
    [stopTimer]
  );

  const start = React.useCallback(
    (request: ResearchRequest) => {
      // Reset for a fresh run.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      lastRequestRef.current = request;

      setQuery(request.query);
      setResult(null);
      setError(null);
      setElapsedMs(0);
      setPhase("running");

      const fresh = initialStages();
      fresh[0] = { ...fresh[0], status: "active" };
      setStages(fresh);
      setActiveStage(fresh[0].stage);

      setHorizonActivity(0.3);
      pulseHorizon(1.5);

      startedAtRef.current = Date.now();
      stopTimer();
      timerRef.current = setInterval(() => {
        setElapsedMs(Date.now() - startedAtRef.current);
      }, 100);

      streamResearch(request, { onEvent, signal: controller.signal })
        .then(() => {
          // If the stream closed without a complete event, don't leave the
          // UI stuck on "running".
          setPhase((p) => (p === "running" ? "complete" : p));
          stopTimer();
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return; // user-initiated cancel
          stopTimer();
          setActiveStage(null);
          resetHorizon();
          const message =
            err instanceof ApiError
              ? err.status === undefined
                ? "Couldn't reach the research backend. Is the API running?"
                : err.message
              : err instanceof Error
                ? err.message
                : "Something went wrong while researching.";
          setError(message);
          setPhase("error");
        });
    },
    [onEvent, stopTimer]
  );

  const cancel = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopTimer();
    setActiveStage(null);
    resetHorizon();
    setPhase((p) => (p === "running" ? "idle" : p));
  }, [stopTimer]);

  const retry = React.useCallback(() => {
    if (lastRequestRef.current) start(lastRequestRef.current);
  }, [start]);

  const reset = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopTimer();
    setPhase("idle");
    setStages(initialStages());
    setActiveStage(null);
    setResult(null);
    setError(null);
    setQuery("");
    setElapsedMs(0);
    resetHorizon();
  }, [stopTimer]);

  React.useEffect(() => {
    return () => {
      abortRef.current?.abort();
      stopTimer();
    };
  }, [stopTimer]);

  return {
    phase,
    stages,
    activeStage,
    result,
    error,
    query,
    elapsedMs,
    start,
    cancel,
    retry,
    reset,
  };
}
